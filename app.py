"""
Análise de Defeitos de Produção — Streamlit App
Roteador / entrypoint: page config, injeção de CSS global, autenticação e
navbar no topo.

A navegação foi migrada da pasta pages/ (sidebar automática) para
st.navigation(position="top"), que renderiza a barra de navegação no topo.
Este arquivo funciona como roteador: envolve todas as páginas com o CSS
global, o portão de login e o cabeçalho de usuário, e então executa a
página atual. O conteúdo de cada tela mora nos scripts de pages/.
"""

import streamlit as st
from src.config.settings import PAGE_CONFIG
from src.auth.session import require_login, render_user_topbar, is_admin
from src.ui.error_boundary import page_guard

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(**PAGE_CONFIG)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Contrato de espaço do cabeçalho ──────────────────────────────────
       O chip do usuário logado (render_user_topbar, em src/auth/session.py) é
       `position: fixed`, então ele NÃO ocupa espaço no fluxo: a navbar não sabe
       que ele existe e centraliza os links por cima dele. Estas duas medidas são
       as duas metades de um mesmo contrato e precisam andar juntas:
         --nv-chip-max     largura máxima do chip (session.py trunca o nome nela);
         --nv-chip-gutter  faixa reservada ao chip à ESQUERDA dos links = margem
                           do chip (1rem) + o chip + um respiro de 12px. O lado
                           direito não leva faixa equivalente: lá o slot da
                           toolbar (Deploy + ⋮) já ocupa quase a mesma largura, e
                           é o que equilibra a centralização.
       Encolhe com a tela (min(..., 30vw)) para que, no celular, o chip não coma
       a faixa inteira do cabeçalho. */
    :root {
        --nv-chip-left: 1rem;
        --nv-chip-max: min(190px, 30vw);
        --nv-chip-gutter: calc(var(--nv-chip-left) + var(--nv-chip-max) + 12px);
    }
    /* Abaixo de 768px não há navbar no topo, mas surge o botão de abrir a
       sidebar no MESMO canto do chip. Sem este recuo os dois se sobrepõem e o
       hambúrguer — única navegação no celular — fica inalcançável sob o chip. */
    @media (max-width: 767.98px) {
        :root { --nv-chip-left: 3.5rem; }
    }

    /* ── Global text default (prevents invisible/black text after blur) ── */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
    .stMarkdown, .stText, p, span, label, div {
        color: #0D1B17;
    }

    /* ── Main area ── */
    [data-testid="stAppViewContainer"] > .main { background: #FAFCFB; }
    [data-testid="stMain"] { background: #FAFCFB; }
    [data-testid="stHeader"] { background: #FAFCFB !important; }
    .main .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1400px; }

    /* ── Sidebar removida (todos os componentes migraram para o corpo) ── */
    /* Só a partir de 768px. Abaixo disso o Streamlit NÃO renderiza a navbar do
       topo: ele move os links da st.navigation para a sidebar e mostra o botão
       de abrir (hambúrguer). Esconder a sidebar em qualquer largura, como era
       antes, deixava o app sem NENHUMA navegação no celular — só dava para ver
       a página em que o usuário já estava. O corte é exatamente onde a navbar
       do topo aparece, então nunca existem as duas ao mesmo tempo. */
    @media (min-width: 768px) {
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"],
        button[kind="headerNoPadding"][data-testid="stBaseButton-headerNoPadding"] {
            display: none !important;
        }
    }

    /* ── Navbar (st.navigation position="top") centralizada ── */
    /* Não depender da classe hash do Emotion (ex.: .e1lpckdq13): ela é regerada
       a cada build do Streamlit, então o seletor morre no deploy se a versão do
       Cloud diferir da local. Aqui casamos qualquer wrapper dos links, em
       qualquer profundidade dentro do header. O combinador descendente impede
       que o próprio header case (o que deslocaria a toolbar); em wrappers de
       link único, centralizar não tem efeito visual. */
    /* `safe center` e não `center`: se ainda assim os links transbordarem, o
       `safe` faz o excedente sobrar só à direita. Com `center` puro ele vazaria
       pelos dois lados e o lado esquerdo cairia sobre o chip do usuário. */
    [data-testid="stHeader"] :has([data-testid="stTopNavLinkContainer"]) {
        justify-content: safe center !important;
    }
    /* A linha dos links (rc-overflow, classe estável da lib de overflow — não é
       hash do Emotion). O escopo a mantém fora da stToolbar, que é flex e também
       contém os links. */
    [data-testid="stHeader"] .rc-overflow:has([data-testid="stTopNavLinkContainer"]) {
        /* `gap: 0` é obrigatório, não estética: o espaçamento entre os links vem
           do padding de cada um (ver stTopNavLink abaixo). A rc-overflow decide o
           que cabe somando a LARGURA DOS ITENS e ignora o gap — com gap ela
           conclui que tudo cabe, não abre o menu "more", e os itens que sobram
           são silenciosamente cortados pela borda do box. Com 6 páginas (admin) e
           gap de 22px isso apagava "Usuários" da barra a partir de ~950px de
           janela, sem deixar rastro. Como padding entra na medição, a lib passa a
           ver o tamanho real e manda o excedente para o "more". */
        gap: 0 !important;
        /* Reserva a faixa do chip à ESQUERDA. É `margin` e não `padding` de
           propósito: a rc-overflow decide quantos links cabem medindo a PRÓPRIA
           largura, e o padding não a reduz — ela acharia que tem a largura cheia,
           deixaria links de fora da caixa e o excedente cairia sobre o chip. A
           margem encolhe o elemento de verdade, então a medição fica correta e o
           que não couber vai para o menu "more" — o responsivo da própria lib. */
        margin-left: var(--nv-chip-gutter) !important;
        padding-left: 0 !important;
        /* Sem margem à direita de propósito. A rc-overflow tem um IRMÃO ali — o
           slot da toolbar (Deploy + ⋮), ~200px — que já faz o papel de faixa
           daquele lado. Espelhar `--nv-chip-gutter` aqui reservaria 218px ALÉM
           dos 200 da toolbar e empurraria os links ~100px para a esquerda: o
           oposto de centralizar.
           O `flex: 1` faz a rc-overflow crescer da faixa do chip até a toolbar em
           vez de encolher no conteúdo (o `0 1 auto` padrão a ancorava à esquerda
           da faixa). Como a faixa do chip (≈218px) e a toolbar (≈216px) têm
           quase a mesma largura, o meio dessa banda cai praticamente no meio da
           tela — e continua caindo se a toolbar mudar de tamanho, porque a banda
           é medida, não fixada. O `safe center` acima então centraliza os links
           dentro dela. */
        flex: 1 1 auto !important;
    }

    /* ── Navbar — estilo "Minimalista" (aprovado) ─────────────────────────── */
    /* Header: fundo branco e um único fio separando do conteúdo. Sem sombra e
       sem o traço de acento verde que havia aqui: no minimalista o verde marca
       só o item ativo, e um header verde competiria com ele. */
    [data-testid="stHeader"] {
        background: #FFFFFF !important;
        border-bottom: 1px solid rgba(13,27,23,0.08) !important;
        box-shadow: none !important;
    }

    /* Cada link do topo (o <a> stTopNavLink) é texto puro: sem fundo e sem raio.
       O padding lateral de 11px é o que separa um link do outro (11+11 = os mesmos
       22px de respiro que um `gap: 22px` daria), mas por ser padding ele entra na
       largura que a rc-overflow mede — ver o `gap: 0` acima. De quebra, a área
       clicável passa a incluir esse respiro. */
    [data-testid="stHeader"] [data-testid="stTopNavLink"] {
        background: transparent !important;
        border-radius: 0 !important;
        padding: 14px 11px !important;
        font-size: 13px !important;
        font-weight: 400 !important;
        color: #6B7A74 !important;
        transition: color 0.16s ease, box-shadow 0.16s ease !important;
    }
    [data-testid="stHeader"] [data-testid="stTopNavLink"] * { color: inherit !important; }

    /* Hover (item inativo): só o texto escurece. */
    [data-testid="stHeader"] [data-testid="stTopNavLink"]:not([aria-current="page"]):hover {
        background: transparent !important;
        color: #0D1B17 !important;
    }

    /* Item ativo: texto escuro + traço verde embaixo.
       O traço é `box-shadow: inset` e NÃO `border-bottom` de propósito: a borda
       somaria 2px à altura do link e o desalinharia dos inativos ao lado. */
    [data-testid="stHeader"] [data-testid="stTopNavLink"][aria-current="page"] {
        background: transparent !important;
        color: #0D1B17 !important;
        font-weight: 500 !important;
        box-shadow: inset 0 -2px 0 0 #00B884 !important;
    }
    [data-testid="stHeader"] [data-testid="stTopNavLink"][aria-current="page"] * {
        color: #0D1B17 !important;
    }

    /* ── Inputs / Select / Multiselect / DateInput / NumberInput / TextArea ── */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    .stTextArea textarea, .stSelectbox [data-baseweb="select"] > div,
    .stMultiSelect [data-baseweb="select"] > div,
    [data-baseweb="input"], [data-baseweb="select"] {
        background: #FFFFFF !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.35) !important;
        border-radius: 8px !important;
    }
    .stTextInput input:hover, .stNumberInput input:hover, .stDateInput input:hover,
    .stSelectbox [data-baseweb="select"] > div:hover,
    .stMultiSelect [data-baseweb="select"] > div:hover {
        border-color:#0D1B17 !important;
        box-shadow: 0 0 0 2px rgba(0,229,160,0.15) !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus, .stDateInput input:focus,
    .stTextArea textarea:focus {
        border-color:#0D1B17 !important;
        box-shadow: 0 0 0 2px rgba(0,229,160,0.25) !important;
        outline: none !important;
    }
    /* Dropdown menu (BaseWeb popover) */
    [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {
        background: #FFFFFF !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.25) !important;
    }
    [data-baseweb="menu"] li, [role="option"] { color: #0D1B17 !important; background: #FFFFFF !important; }
    [data-baseweb="menu"] li:hover, [role="option"]:hover,
    [role="option"][aria-selected="true"] { background: rgba(0,229,160,0.15) !important; color: #0D1B17 !important; }

    /* SVG icons inside inputs (chevrons, calendar, clear) */
    [data-baseweb="select"] svg, [data-baseweb="input"] svg,
    .stDateInput svg { fill: #00B884 !important; color:#0D1B17 !important; }

    /* ── Upload area — discreta ── */
    [data-testid="stSidebar"] [data-testid="stFileUploader"] {
        background: #F2F7F5 !important;
        border: 1px dashed rgba(0,184,132,0.45) !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background: transparent !important;
        padding: 8px !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] span {
        font-size: 11.5px !important;
        color: #4A5752 !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] small {
        font-size: 10px !important;
        color:#4A5752 !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploader"] button {
        font-size: 11px !important;
        padding: 4px 12px !important;
        background: rgba(0,229,160,0.25) !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.45) !important;
        border-radius: 6px !important;
    }

    /* ── Expander ── */
    [data-testid="stExpander"] { background: #FFFFFF !important; border: 1px solid rgba(0,0,0,0.08) !important; border-radius: 10px !important; }
    [data-testid="stExpander"] summary { font-size: 13px !important; color: #0D1B17 !important; }
    [data-testid="stExpander"] summary:hover { color: #00805C !important; }

    /* ── Buttons ── */
    .stButton > button, .stDownloadButton > button {
        background: #FFFFFF !important;
        color: #0D1B17 !important;
        border: 1px solid #00B884 !important;
        border-radius: 8px !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        transition: all 0.18s ease !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        background: rgba(0,229,160,0.20) !important;
        color: #00805C !important;
        border-color:#0D1B17 !important;
        box-shadow: 0 0 0 3px rgba(0,229,160,0.15) !important;
    }
    .stButton > button:focus, .stButton > button:active,
    .stDownloadButton > button:focus, .stDownloadButton > button:active {
        background: rgba(0,229,160,0.28) !important;
        color: #0D1B17 !important;
        border-color:#0D1B17 !important;
        outline: none !important;
        box-shadow: 0 0 0 3px rgba(0,229,160,0.30) !important;
    }

    /* ── Multiselect tags ── */
    [data-baseweb="tag"] {
        background: rgba(0,229,160,0.25) !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.4) !important;
    }
    [data-baseweb="tag"] * { color: #0D1B17 !important; }

    /* ── Slider ── */
    [data-baseweb="slider"] [role="slider"] { background: #00B884 !important; border-color:#0D1B17 !important; }

    /* ── DataFrame / Tables ── */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        background: #FFFFFF !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.20) !important;
        border-radius: 8px;
    }
    [data-testid="stDataFrame"] * { color: #0D1B17 !important; }
    [data-testid="stDataFrame"] thead th {
        background: #F2F7F5 !important;
        color: #0D1B17 !important;
        border-bottom: 1px solid rgba(0,184,132,0.35) !important;
    }
    [data-testid="stDataFrame"] tbody tr:hover td { background: rgba(0,229,160,0.10) !important; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid rgba(0,184,132,0.20); }
    .stTabs [data-baseweb="tab"] { color: #4A5752 !important; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { color: #00805C !important; }
    .stTabs [data-baseweb="tab-highlight"] { background: #00B884 !important; }

    /* ── Alerts ── */
    [data-testid="stAlert"] { color: #0D1B17 !important; }

    /* ── Metric ── */
    [data-testid="stMetricValue"] { color: #0D1B17 !important; }
    [data-testid="stMetricLabel"] { color: #4A5752 !important; }
    [data-testid="stMetricDelta"] { color: #00805C !important; }

    /* ── Divider ── */
    hr { border-color: rgba(0,184,132,0.20) !important; }

    /* ── Links ── */
    a, a:visited { color: #00805C !important; }
    a:hover { color:#0D1B17 !important; }

    /* ── Vega/Altair chart tooltips ── */
    #vg-tooltip-element {
        background: #061210 !important;
        border: 1px solid #00B884 !important;
        border-radius: 12px !important;
        padding: 14px 18px !important;
        box-shadow:
            0 0 0 1px rgba(0,229,160,0.15),
            0 0 28px rgba(0,184,132,0.55),
            0 0 60px rgba(0,184,132,0.20),
            0 8px 28px rgba(0,0,0,0.90) !important;
        font-family: 'Inter', monospace !important;
        min-width: 170px !important;
        pointer-events: none !important;
        z-index: 9999 !important;
    }
    #vg-tooltip-element h2 {
        color: #00E5A0 !important;
        font-size: 10px !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 1.2px !important;
        margin: 0 0 10px 0 !important;
        padding-bottom: 7px !important;
        border-bottom: 1px solid rgba(0,229,160,0.25) !important;
    }
    #vg-tooltip-element table {
        border-spacing: 0 !important;
        border-collapse: collapse !important;
        width: 100% !important;
    }
    #vg-tooltip-element tr {
        border-bottom: 1px solid rgba(0,184,132,0.08) !important;
    }
    #vg-tooltip-element tr:last-child {
        border-bottom: none !important;
    }
    #vg-tooltip-element td {
        padding: 5px 0 !important;
        font-size: 13px !important;
        line-height: 1.4 !important;
    }
    #vg-tooltip-element td.key {
        color: #5FF6C6 !important;
        font-size: 10.5px !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.7px !important;
        padding-right: 20px !important;
        opacity: 0.80 !important;
        white-space: nowrap !important;
    }
    #vg-tooltip-element td.value {
        color: #00FF9C !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        letter-spacing: -0.3px !important;
        text-align: right !important;
        text-shadow: 0 0 10px rgba(0,255,156,0.50) !important;
    }

    /* ── Streamlit help (ⓘ) tooltips ── */
    [data-baseweb="tooltip"] > div {
        background: #061210 !important;
        border: 1px solid #00B884 !important;
        border-radius: 10px !important;
        box-shadow:
            0 0 22px rgba(0,184,132,0.50),
            0 6px 20px rgba(0,0,0,0.80) !important;
        padding: 10px 14px !important;
        max-width: 320px !important;
    }
    [data-baseweb="tooltip"] * {
        color: #00E5A0 !important;
        font-size: 12.5px !important;
        line-height: 1.6 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Router ────────────────────────────────────────────────────────────────────

@page_guard
def main() -> None:
    # ── Portão de autenticação (tela de proteção) ─────────────────────────────
    require_login()

    # ── Usuário logado + sair, no topo (substitui o cartão da sidebar) ────────
    render_user_topbar()

    # ── Páginas disponíveis (navbar no topo) ──────────────────────────────────
    # As páginas restritas a administradores só são registradas para admins,
    # de modo que usuários comuns nem veem o item na navbar.
    # Sem `icon=`: no estilo minimalista o emoji de cada item competia com o
    # traço verde que marca a página ativa. Os títulos também encurtam — sem os
    # ícones a barra fica só com texto, e nomes longos a enchem depressa.
    pages = [
        st.Page("pages/1_Dashboard.py", title="Análise de defeitos", default=True),
        st.Page("pages/2_Historico_Defeitos.py", title="Histórico"),
        st.Page("pages/3_Historico_Cobranca.py", title="Cobranças"),
        st.Page("pages/4_Defeitos_Imagens.py", title="Imagens"),
    ]
    if is_admin():
        pages.append(
            st.Page("pages/5_Editar_Registros.py", title="Registros")
        )
        pages.append(
            st.Page("pages/6_Gerenciar_Usuarios.py", title="Usuários")
        )

    nav = st.navigation(pages, position="top")
    nav.run()


if __name__ == "__main__":
    main()
