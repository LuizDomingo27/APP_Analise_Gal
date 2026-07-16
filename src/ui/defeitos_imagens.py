# -*- coding: utf-8 -*-
"""
UI da página Imagens de Defeitos — módulo isolado.

Estrutura da página (de cima para baixo):
  1. Cabeçalho
  2. Cadastro de imagens (somente administradores): envia uma imagem e associa
     ao nome de um defeito. Regrava (upsert) se o defeito já tiver imagem.
  3. Consulta por oficina: escolhe a fonte (Histórico permanente ou Base ativa),
     seleciona a oficina e vê uma tabela (só texto) com Ordem Mestre (OM),
     Oficina, Quantidade de peças com defeito e Nome do defeito. Abaixo, um
     frame "Principais Defeitos" traz a imagem dos 3 defeitos mais frequentes
     da oficina (ranking pela SOMA da quantidade; menos de 3 → mostra todos),
     com o #1 destacado como o principal a resolver. As imagens NÃO vão na
     tabela — ficam só nesse frame de prioridades.

Página defensiva: dados ausentes ou falhas de banco viram mensagens amigáveis,
nunca traceback na tela. A fronteira DatabaseUnavailableError é capturada pelo
@page_guard em pages/4_Defeitos_Imagens.py.
"""

import logging

import pandas as pd
import streamlit as st

from src.auth.session import is_admin
from src.config.settings import COLS, COLORS
from src.data.defeitos_imagens import (
    carregar_catalogo,
    excluir_imagem,
    imagem_do_defeito,
    listar_defeitos,
    salvar_imagem,
)
from src.data.historico_defeitos import load_historico
from src.data.loader import load_data_from_disk

logger = logging.getLogger(__name__)

_FONTE_HISTORICO = "Histórico permanente"
_FONTE_ATIVA = "Base ativa (registros atuais)"


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def render_defeitos_imagens_page() -> None:
    _render_header()

    if is_admin():
        _render_cadastro_section()

    _render_consulta_section()


# ══════════════════════════════════════════════════════════════════════════════
# Cabeçalho
# ══════════════════════════════════════════════════════════════════════════════

def _render_header() -> None:
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;border-bottom:1px solid rgba(0,0,0,0.06);margin-bottom:1.4rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;color:{COLORS['text_primary']}">
                    🖼️ Imagens de Defeitos
                </span>
                <span style="font-size:12px;color:{COLORS['text_subtle']};
                             background:rgba(0,229,160,0.18);padding:3px 10px;
                             border-radius:20px;border:1px solid rgba(0,229,160,0.3)">
                    Catálogo Visual
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Cadastro de imagens — administradores
# ══════════════════════════════════════════════════════════════════════════════

def _render_cadastro_section() -> None:
    with st.expander("➕ Cadastrar / substituir imagem de defeito", expanded=False):
        st.markdown(
            f"<p style='font-size:12.5px;color:{COLORS['text_muted']};margin:0 0 12px;line-height:1.6'>"
            "Envie a imagem e informe o <strong>nome do defeito</strong> (o mesmo que "
            "aparece na coluna de defeito dos registros, ex.: <em>Ponto Estourado</em>). "
            "A associação ignora acentos, espaços e o prefixo <em>img</em> do arquivo — "
            "então <em>imgPontoEstourado</em> e <em>Ponto Estourado</em> casam com o mesmo "
            "defeito. Cadastrar de novo o mesmo defeito <strong>substitui</strong> a imagem.</p>",
            unsafe_allow_html=True,
        )

        col_nome, col_arq = st.columns([1, 1])
        with col_nome:
            defeito_nome = st.text_input(
                "Nome do defeito",
                key="img_cad_nome",
                placeholder="Ex.: Ponto Estourado",
            )
        with col_arq:
            uploaded = st.file_uploader(
                "Imagem do defeito",
                type=["png", "jpg", "jpeg", "webp"],
                key="img_cad_uploader",
            )

        disabled = not (defeito_nome and defeito_nome.strip() and uploaded is not None)
        if st.button("💾 Salvar imagem", type="primary", disabled=disabled, key="img_cad_salvar"):
            try:
                with st.spinner("Salvando imagem…"):
                    chave = salvar_imagem(uploaded, defeito_nome)
            except ValueError as exc:
                st.warning(str(exc))
            except Exception as exc:  # noqa: BLE001 — fronteira defensiva local
                logger.exception("Falha ao salvar imagem de defeito")
                st.error(f"⚠️ Não foi possível salvar a imagem: {exc}")
            else:
                st.success(f'✅ Imagem salva para o defeito "{defeito_nome.strip()}" (chave: {chave}).')
                st.rerun()

        _render_catalogo_admin()


def _render_catalogo_admin() -> None:
    """Lista os defeitos já cadastrados, com prévia e opção de excluir."""
    try:
        defeitos = listar_defeitos()
    except Exception as exc:  # noqa: BLE001 — fronteira defensiva local
        st.error(f"⚠️ Não foi possível listar as imagens cadastradas: {exc}")
        return

    if not defeitos:
        st.caption("Nenhuma imagem cadastrada ainda.")
        return

    catalogo = carregar_catalogo()
    st.markdown(
        f"<p style='font-size:12px;text-transform:uppercase;letter-spacing:1px;"
        f"color:{COLORS['text_muted']};margin:14px 0 8px'>Imagens cadastradas</p>",
        unsafe_allow_html=True,
    )

    for item in defeitos:
        col_img, col_nome, col_del = st.columns([1, 3, 1])
        data_uri = (catalogo.get(item["chave"]) or {}).get("data_uri")
        with col_img:
            if data_uri:
                st.image(data_uri, width=64)
        with col_nome:
            st.markdown(
                f"<div style='padding-top:6px'><strong>{item['nome']}</strong><br>"
                f"<span style='font-size:11px;color:{COLORS['text_subtle']}'>{item['chave']}</span></div>",
                unsafe_allow_html=True,
            )
        with col_del:
            if st.button("🗑️ Excluir", key=f"img_del_{item['chave']}"):
                try:
                    excluir_imagem(item["chave"])
                except Exception as exc:  # noqa: BLE001 — fronteira defensiva local
                    st.error(f"⚠️ Não foi possível excluir: {exc}")
                else:
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Consulta por oficina
# ══════════════════════════════════════════════════════════════════════════════

def _load_fonte(fonte: str) -> pd.DataFrame | None:
    """Carrega o DataFrame da fonte escolhida (histórico ou base ativa)."""
    if fonte == _FONTE_ATIVA:
        return load_data_from_disk()
    return load_historico()


def _render_consulta_section() -> None:
    st.markdown(
        f"<p style='font-size:11px;text-transform:uppercase;letter-spacing:1px;"
        f"color:{COLORS['text_muted']};margin:1.5rem 0 8px'>🔎 Consulta por oficina</p>",
        unsafe_allow_html=True,
    )

    col_fonte, col_of = st.columns([1, 1])
    with col_fonte:
        fonte = st.radio(
            "Fonte dos dados",
            options=[_FONTE_HISTORICO, _FONTE_ATIVA],
            horizontal=True,
            key="img_consulta_fonte",
        )

    df = _load_fonte(fonte)
    if df is None or df.empty:
        st.info("Nenhum registro disponível nesta fonte ainda.")
        return

    suppliers = sorted(df[COLS["supplier"]].dropna().unique().tolist())
    with col_of:
        oficina = st.selectbox(
            "🏭 Oficina (Fornecedor)",
            options=suppliers,
            key="img_consulta_oficina",
        )

    sel = df[df[COLS["supplier"]] == oficina]
    if sel.empty:
        st.warning("Nenhum registro para esta oficina.")
        return

    # OM + Defeito → soma das peças com defeito
    tabela = (
        sel.groupby([COLS["order"], COLS["supplier"], COLS["defect"]], as_index=False)[
            COLS["quantity"]
        ]
        .sum()
        .rename(
            columns={
                COLS["order"]: "OM",
                COLS["supplier"]: "Oficina",
                COLS["defect"]: "Defeito",
                COLS["quantity"]: "Qtd. Defeitos",
            }
        )
        .sort_values(["OM", "Qtd. Defeitos"], ascending=[True, False])
    )

    # Tabela só texto — as imagens NÃO vão aqui, ficam no frame de prioridades.
    # Mesmo visual das demais tabelas do app (ver src/ui/layout.py::_render_table).
    _render_tabela_estilizada(tabela)

    total_pecas = int(tabela["Qtd. Defeitos"].sum())
    st.caption(
        f"✦ {len(tabela)} combinação(ões) OM × defeito · "
        f"{total_pecas:,} peça(s) com defeito para **{oficina}**."
    )

    _render_principais_defeitos(sel, oficina)


# ══════════════════════════════════════════════════════════════════════════════
# Tabela estilizada (mesmo visual de src/ui/layout.py::_render_table)
# ══════════════════════════════════════════════════════════════════════════════

def _render_tabela_estilizada(tabela: pd.DataFrame) -> None:
    """
    Renderiza OM × Oficina × Qtd. × Defeito com o mesmo design das outras tabelas
    do app: cabeçalho verde (#00805C) com texto branco maiúsculo, linhas zebradas,
    borda arredondada com brilho verde, scrollbar custom e realce ao passar o mouse.
    """
    thr_qty = float(tabela["Qtd. Defeitos"].quantile(0.75)) if len(tabela) else 0.0

    TH = (
        "padding:11px 14px;text-align:center;font-weight:600;"
        "font-size:10px;color:#FFFFFF;text-transform:uppercase;letter-spacing:0.9px;"
        "background:#00805C;border-bottom:1px solid rgba(0,229,160,0.35);"
        "white-space:nowrap;position:sticky;top:0;z-index:1;"
    )
    TH_L = TH + "text-align:left;"

    headers = [
        ("OM (Ordem Mestre)", False),
        ("Oficina", True),
        ("Qtd. Defeitos", False),
        ("Defeito", True),
    ]
    head_html = "".join(
        f'<th style="{TH_L if is_left else TH}">✦ {label}</th>'
        for label, is_left in headers
    )

    rows_html = ""
    for i, (_, row) in enumerate(tabela.iterrows()):
        row_bg = (
            "background:rgba(0,229,160,0.07);"
            if i % 2 == 1
            else "background:#F2F7F5;"
        )
        base_td = (
            "padding:9px 14px;font-size:12.5px;color:#0D1B17;"
            "border-bottom:1px solid rgba(0,229,160,0.12);"
        )
        try:
            qtd = int(row["Qtd. Defeitos"])
            qtd_txt = f"{qtd:,}"
        except (ValueError, TypeError):
            qtd, qtd_txt = 0, "—"
        peso = "font-weight:600;" if qtd > thr_qty else ""

        rows_html += (
            "<tr>"
            f'<td style="{base_td}text-align:center;color:#4A5752;{row_bg}">{row["OM"]}</td>'
            f'<td style="{base_td}text-align:left;{row_bg}">{row["Oficina"]}</td>'
            f'<td style="{base_td}text-align:center;{peso}{row_bg}">{qtd_txt}</td>'
            f'<td style="{base_td}text-align:left;{row_bg}">{row["Defeito"]}</td>'
            "</tr>"
        )

    table_html = f"""
    <style>
      .di-table-wrap::-webkit-scrollbar {{ width:6px; height:6px; }}
      .di-table-wrap::-webkit-scrollbar-track {{ background:#FFFFFF; border-radius:3px; }}
      .di-table-wrap::-webkit-scrollbar-thumb {{ background:rgba(0,229,160,0.45); border-radius:3px; }}
      .di-table-wrap::-webkit-scrollbar-thumb:hover {{ background:rgba(0,229,160,0.70); }}
      .di-table-wrap tr:hover td {{ background:rgba(0,229,160,0.14)!important; transition:background 0.15s; }}
    </style>
    <div class="di-table-wrap" style="
        max-height:460px; overflow:auto; border-radius:12px;
        border:1px solid rgba(0,229,160,0.32);
        border-top:2px solid #00B884;
        background:#F2F7F5;
        box-shadow:0 0 22px rgba(0,229,160,0.10);
    ">
      <table style="width:100%;border-collapse:collapse;min-width:560px;">
        <thead><tr>{head_html}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Frame "Principais Defeitos" — imagens dos 3 defeitos mais frequentes
# ══════════════════════════════════════════════════════════════════════════════

_MEDALHAS = ["🥇", "🥈", "🥉"]


def _render_principais_defeitos(sel: pd.DataFrame, oficina: str) -> None:
    """
    Mostra a imagem dos 3 defeitos mais frequentes da oficina, ranqueados pela
    SOMA da quantidade (menos de 3 tipos → mostra todos). O #1 é destacado como
    o principal defeito a resolver. As imagens saem daqui, não da tabela.
    """
    por_defeito = (
        sel.groupby(COLS["defect"])[COLS["quantity"]]
        .sum()
        .sort_values(ascending=False)
    )
    por_defeito = por_defeito[por_defeito > 0]
    if por_defeito.empty:
        return

    total = int(por_defeito.sum())
    top = por_defeito.head(3)

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:10px;margin:2rem 0 0.3rem">
            <span style="font-size:18px">🎯</span>
            <span style="font-size:15px;font-weight:600;color:{COLORS['text_primary']}">
                Principais Defeitos — prioridade de correção
            </span>
            <div style="flex:1;height:1px;background:rgba(0,0,0,0.07);margin-left:6px"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p style='font-size:12.5px;color:{COLORS['text_muted']};margin:0 0 14px;line-height:1.6'>"
        f"Os {len(top)} defeito(s) mais frequentes de <strong>{oficina}</strong>, pela soma da "
        "quantidade de peças. Comece pelo <strong>1º</strong> — é o que mais impacta.</p>",
        unsafe_allow_html=True,
    )

    catalogo = carregar_catalogo()
    cols = st.columns(len(top))

    for i, (defeito, qtd) in enumerate(top.items()):
        qtd = int(qtd)
        pct = (qtd / total * 100) if total else 0
        medalha = _MEDALHAS[i] if i < len(_MEDALHAS) else f"{i + 1}º"
        destaque = i == 0
        with cols[i]:
            borda = (
                "border:2px solid rgba(0,184,132,0.55);box-shadow:0 0 16px rgba(0,229,160,0.18)"
                if destaque
                else "border:1px solid rgba(0,0,0,0.08)"
            )
            st.markdown(
                f"""
                <div style="{borda};border-radius:12px;padding:10px 12px 4px;margin-bottom:6px">
                    <div style="display:flex;align-items:baseline;gap:8px">
                        <span style="font-size:20px">{medalha}</span>
                        <span style="font-size:14px;font-weight:700;color:{COLORS['text_primary']}">{defeito}</span>
                    </div>
                    <div style="font-size:12px;color:{COLORS['text_muted']};margin-top:2px">
                        {qtd:,} peça(s) · {pct:.0f}% do total
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            data_uri = imagem_do_defeito(defeito, catalogo)
            if data_uri:
                st.image(data_uri, use_container_width=True)
            else:
                st.info(
                    f"Sem imagem cadastrada para “{defeito}”. "
                    "Um administrador pode cadastrá-la na seção acima."
                )

            if destaque:
                st.markdown(
                    f"<p style='font-size:12px;color:#00805C;font-weight:600;margin:6px 0 0'>"
                    "⚠️ Principal defeito a resolver.</p>",
                    unsafe_allow_html=True,
                )
