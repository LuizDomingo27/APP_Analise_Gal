# -*- coding: utf-8 -*-
"""
Seção de Backup do painel administrativo (dentro de Gerenciar Usuários).

Enquanto o Supabase estiver no plano gratuito não há backup automático, então
esta é a cópia de segurança oficial dos dados: um .zip com um .xlsx por tabela,
gerado sob demanda pelo administrador e baixado na hora — nada é gravado no
servidor.

Três cuidados de implementação, todos deliberados:

  · Geração sob demanda, guardada em session_state. `st.download_button` roda a
    cada rerun da página; se ele recebesse os bytes de uma chamada direta ao
    gerador, o backup inteiro seria remontado a cada clique em qualquer widget
    da página. Aqui o botão "Gerar" produz os bytes uma vez e o download apenas
    os entrega.
  · Gate de administrador redundante. A página já exige admin, mas esta função
    verifica de novo antes de ler qualquer dado: é o backup completo do banco,
    inclusive a tabela de usuários — a checagem não pode depender de quem chama.
  · Falha nunca derruba a página. Banco indisponível vira mensagem amigável;
    erro inesperado na montagem do arquivo vira aviso. O restante da tela de
    usuários continua funcionando.
"""

from __future__ import annotations

import logging
from datetime import datetime

import streamlit as st

from src.auth import session
from src.data.backup import (
    STATUS_AUSENTE,
    STATUS_ERRO,
    STATUS_OK,
    STATUS_VAZIA,
    ResultadoTabela,
    coletar_backup,
)
from src.data.database import DatabaseUnavailableError
from src.services.backup_exporter import build_backup_zip, nome_do_arquivo

logger = logging.getLogger(__name__)

_STATE_KEY = "backup_payload"

# (rótulo, cor de texto, cor de fundo) por status — tokens do tema.
_CHIP = {
    STATUS_OK: ("Exportada", "var(--ag-primary-dark)", "rgba(var(--ag-primary-rgb),0.12)"),
    STATUS_VAZIA: ("Vazia", "var(--ag-text-muted)", "rgba(var(--ag-text-subtle-rgb),0.12)"),
    STATUS_AUSENTE: ("Ausente", "var(--ag-warning)", "rgba(var(--ag-warning-rgb),0.14)"),
    STATUS_ERRO: ("Falhou", "var(--ag-danger)", "rgba(var(--ag-danger-rgb),0.12)"),
}


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        /* Mesma largura fixa (500px, centralizada) do card de criar usuário,
           para as duas seções da página ficarem alinhadas. */
        div[class*="st-key-backup_card"] {
            max-width: 500px !important;
            margin-left: auto !important;
            margin-right: auto !important;
            background: linear-gradient(160deg, var(--ag-bg-surface) 0%, var(--ag-bg-surface-alt) 100%) !important;
            border: 1px solid rgba(var(--ag-primary-bright-rgb),0.30) !important;
            border-top: 3px solid var(--ag-primary) !important;
            border-radius: 14px !important;
            padding: 20px 22px 16px !important;
            box-shadow: 0 0 24px rgba(var(--ag-primary-bright-rgb),0.08),
                        0 2px 10px rgba(var(--ag-shadow-rgb),0.04) !important;
        }
        div[class*="st-key-backup_tabelas"] {
            background: var(--ag-bg-surface) !important;
            border: 1px solid rgba(var(--ag-primary-rgb),0.10) !important;
            border-radius: 12px !important;
            padding: 12px 16px !important;
            margin-top: 12px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    st.markdown(
        """
        <p style="font-size:10px;color:var(--ag-primary);font-weight:700;
                  text-transform:uppercase;letter-spacing:0.8px;margin:0 0 8px">
            ✦ Cópia de Segurança
        </p>
        <div style="line-height:1.5">
            <span style="font-size:15px;font-weight:700;color:var(--ag-text-primary)">
                🗄️ Backup completo em Excel
            </span>
            <p style="color:var(--ag-text-muted);font-size:12.5px;margin:4px 0 0">
                Gera um arquivo <b>.zip</b> com uma planilha por tabela do banco, com os tipos
                de dado preservados (datas, valores em R$, quantidades) — pronto para restaurar
                os dados em outro banco. O arquivo é montado na hora e baixado direto para o seu
                computador; nada fica guardado no servidor.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_resumo(resultados: list[dict]) -> None:
    """Lista compacta de tabela · status · registros do último backup gerado."""
    linhas = []
    for r in resultados:
        rotulo, cor, fundo = _CHIP.get(r["status"], _CHIP[STATUS_ERRO])
        registros = f"{r['linhas']:,}".replace(",", ".") if r["linhas"] else "—"
        linhas.append(
            f"""
            <div style="display:flex;align-items:center;gap:10px;padding:5px 0;
                        border-bottom:1px solid rgba(var(--ag-shadow-rgb),0.05)">
                <span style="flex:1;min-width:0;font-size:12.5px;color:var(--ag-text-primary);
                             font-family:ui-monospace,Menlo,Consolas,monospace;
                             white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{r['nome']}</span>
                <span style="font-size:11.5px;color:var(--ag-text-muted);min-width:70px;
                             text-align:right">{registros}</span>
                <span style="font-size:10.5px;font-weight:700;color:{cor};background:{fundo};
                             padding:2px 9px;border-radius:10px;min-width:74px;
                             text-align:center">{rotulo}</span>
            </div>
            """
        )
    st.markdown("".join(linhas), unsafe_allow_html=True)


def _payload(resultados: list[ResultadoTabela], gerado_por: str) -> dict:
    """Monta os bytes do .zip e o resumo que fica em sessão até o download."""
    gerado_em = datetime.now()
    dados = build_backup_zip(resultados, gerado_em, gerado_por)
    return {
        "bytes": dados,
        "arquivo": nome_do_arquivo(gerado_em),
        "gerado_em": gerado_em.strftime("%d/%m/%Y às %H:%M"),
        "tabelas": sum(1 for r in resultados if r.exportavel),
        "linhas": sum(r.linhas for r in resultados),
        "tamanho_kb": len(dados) / 1024,
        "resumo": [
            {"nome": r.nome, "status": r.status, "linhas": r.linhas} for r in resultados
        ],
        "falhas": [r.nome for r in resultados if r.status == STATUS_ERRO],
    }


def _gerar_backup(gerado_por: str) -> dict | None:
    """
    Executa a coleta + montagem do .zip com barra de progresso.
    Retorna o payload ou None (mensagem de erro já exibida ao usuário).
    """
    barra = st.progress(0.0, text="Preparando o backup…")
    try:
        def _passo(feitas: int, total: int, nome: str) -> None:
            barra.progress(feitas / total, text=f"Lendo {nome}  ({feitas}/{total})")

        resultados = coletar_backup(progresso=_passo)

        if not any(r.exportavel for r in resultados):
            detalhe = next((r.erro for r in resultados if r.erro), "")
            st.error(
                "⚠️ Nenhuma tabela pôde ser lida — o backup não foi gerado. "
                + (detalhe or "Tente novamente em instantes.")
            )
            return None

        barra.progress(1.0, text="Montando o arquivo .zip…")
        return _payload(resultados, gerado_por)
    except DatabaseUnavailableError as exc:
        st.error(f"⚠️ {exc}")
        return None
    except Exception:  # noqa: BLE001 — fronteira: nada de traceback cru na UI
        logger.exception("Falha inesperada ao gerar o backup")
        st.warning(
            "⚠️ Não foi possível gerar o backup agora. "
            "Tente novamente; se persistir, contate o suporte."
        )
        return None
    finally:
        barra.empty()


def render_backup_section() -> None:
    """
    Ponto de entrada público — renderiza a seção de backup se, e somente se, o
    usuário da sessão for administrador.
    """
    if not session.is_admin():
        return

    _inject_styles()
    st.markdown("<div style='height:34px'></div>", unsafe_allow_html=True)

    usuario = (session.current_user() or {}).get("username") or "—"
    payload = st.session_state.get(_STATE_KEY)

    with st.container(key="backup_card"):
        _render_header()
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        col_gerar, col_baixar = st.columns(2)
        with col_gerar:
            gerar = st.button(
                "🗄️ Gerar backup agora",
                key="backup_gerar",
                type="primary",
                use_container_width=True,
                help="Lê todas as tabelas e monta o arquivo .zip para download.",
            )

        if gerar:
            payload = _gerar_backup(usuario)
            st.session_state[_STATE_KEY] = payload
            if payload is None:
                st.session_state.pop(_STATE_KEY, None)

        with col_baixar:
            if payload:
                st.download_button(
                    "⬇️ Baixar arquivo (.zip)",
                    data=payload["bytes"],
                    file_name=payload["arquivo"],
                    mime="application/zip",
                    key="backup_download",
                    use_container_width=True,
                )

        if payload:
            tamanho = payload["tamanho_kb"]
            tamanho_txt = (
                f"{tamanho / 1024:.1f} MB" if tamanho >= 1024 else f"{tamanho:.0f} KB"
            )
            registros_txt = f"{payload['linhas']:,}".replace(",", ".")
            st.caption(
                f"Backup de {payload['gerado_em']} · {payload['tabelas']} tabela(s) · "
                f"{registros_txt} registro(s) · {tamanho_txt} · "
                f"arquivo `{payload['arquivo']}`"
            )
            if payload["falhas"]:
                st.warning(
                    "⚠️ Estas tabelas não entraram no backup: "
                    + ", ".join(payload["falhas"])
                    + ". As demais foram exportadas normalmente — veja a aba "
                    "_INFO do arquivo para o detalhe."
                )

            with st.container(key="backup_tabelas"):
                _render_resumo(payload["resumo"])
