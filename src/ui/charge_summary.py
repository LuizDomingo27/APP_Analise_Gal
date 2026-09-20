"""Prévia e downloads resumidos para o recorte da aba de cobranças."""
from datetime import date

import streamlit as st
import pandas as pd

from src.data.cobranca_history import HISTORY_LABELS
from src.config.settings import COLS
from src.services.charge_summary_exporter import build_charge_summary, summary_excel, summary_pdf


def render_summary_exports(df_filtered, excel_col, pdf_col, key):
    raw = df_filtered.rename(columns={label: col for col, label in HISTORY_LABELS.items()})
    if key in ("pagamentos", "devolucoes"):
        raw[COLS["status"]] = "Pago" if key == "pagamentos" else "Devolução"
    preview = st.expander("Resumo por cobrança — visualizar e escolher abrangência")
    all_charges = False
    if key != "divididas":
        with preview:
            all_charges = st.checkbox(
                "Incluir todas as cobranças: pendentes, pagas e devolvidas",
                key=f"{key}_resumo_todas_cobrancas",
                help="Reúne todas as datas e fornecedores, independentemente dos filtros da aba. "
                     "Na cobrança dividida, inclui apenas a parte do fornecedor.",
            )
    frames = [raw]
    if all_charges:
        from src.data.cobranca_history import load_history
        from src.data.payment_history import load_payments
        from src.data.devolucao_history import load_devolucoes

        frames = [load_history()]
        for load, status in ((load_payments, "Pago"), (load_devolucoes, "Devolução")):
            frame = load()
            if frame is not None and not frame.empty:
                frames.append(frame.assign(**{COLS["status"]: status}))
    summary = build_charge_summary(frames)
    scope = "Todas as cobranças, sem filtros." if all_charges else "Filtros atuais desta aba."
    for col, label, extension, mime, generate in (
        (excel_col, "Excel resumo", "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", summary_excel),
        (pdf_col, "PDF resumo", "pdf", "application/pdf", summary_pdf),
    ):
        with col:
            st.download_button(
                label, data=generate(summary) if not summary.empty else b"",
                file_name=f"{key}_resumo_{date.today().isoformat()}.{extension}",
                mime=mime, key=f"{key}_resumo_{extension}", disabled=summary.empty,
                help=f"Uma linha por cobrança. {scope}",
                use_container_width=True,
            )
    with preview:
        st.caption(f"{len(summary)} cobrança(s). {scope}")
        view = summary.copy()
        for name in ("Data cobrança", "Data vencimento", "Data pagamento"):
            view[name] = view[name].map(lambda v: v.strftime("%d/%m/%Y") if pd.notna(v) else "")
        st.dataframe(view, hide_index=True, use_container_width=True)
