import streamlit as st
import pandas as pd
from streamlit_folium import folium_static

try:
    from streamlit_geolocation import streamlit_geolocation
except Exception:
    streamlit_geolocation = None

from data.data_loader import prepare_merged_df
from map.map_builder import build_map


def _norm_code(x) -> str:
    """Normaliza códigos tipo Lant vindos do Excel: '12345.0' -> '12345', trim, uppercase."""
    if x is None:
        return ""
    s = str(x).strip()
    if s.endswith(".0") and s.replace(".0", "").isdigit():
        s = s[:-2]
    return s.strip().upper()


def main():
    st.set_page_config(layout="wide", page_title="TaskForce MasterChain (No-JS)")
    st.title("TASKFORCE MASTERCHAIN - ALERTS MAP (No-JS)")

    # -----------------------------
    # SESSION DEFAULTS
    # -----------------------------
    if "use_cluster" not in st.session_state:
        st.session_state.use_cluster = False
    if "show_table" not in st.session_state:
        st.session_state.show_table = False
    if "show_comments" not in st.session_state:
        st.session_state.show_comments = False
    if "selected_issues" not in st.session_state:
        st.session_state.selected_issues = []
    if "lant_code" not in st.session_state:
        st.session_state.lant_code = ""
    if "route_sites" not in st.session_state:
        st.session_state.route_sites = []
    if "user_lat" not in st.session_state:
        st.session_state.user_lat = None
    if "user_lon" not in st.session_state:
        st.session_state.user_lon = None

    # -----------------------------
    # SIDEBAR: LOCALIZAÇÃO
    # -----------------------------
    st.sidebar.header("Localização")
    manual = st.sidebar.toggle("Inserir localização manualmente", value=False)

    if manual or streamlit_geolocation is None:
        if streamlit_geolocation is None:
            st.sidebar.warning("Geolocalização não disponível aqui. Usa modo manual.")
        st.session_state.user_lat = st.sidebar.number_input("Latitude", value=38.722300, format="%.6f")
        st.session_state.user_lon = st.sidebar.number_input("Longitude", value=-9.139300, format="%.6f")
    else:
        if st.sidebar.button("📍 Atualizar localização"):
            loc = streamlit_geolocation() or {}
            lat_tmp = loc.get("latitude")
            lon_tmp = loc.get("longitude")
            if lat_tmp is not None and lon_tmp is not None:
                st.session_state.user_lat = float(lat_tmp)
                st.session_state.user_lon = float(lon_tmp)
            else:
                st.sidebar.warning("Sem localização. Verifica permissões do browser.")

    if st.session_state.user_lat is None or st.session_state.user_lon is None:
        st.info("Permite localização no browser (ou usa modo manual) para continuar.")
        st.stop()

    user_lat = float(st.session_state.user_lat)
    user_lon = float(st.session_state.user_lon)

    # -----------------------------
    # UPLOADS
    # -----------------------------
    st.subheader("Uploads")
    file_loc = st.file_uploader("📍 Base localizações (.xlsx)", type=["xlsx"])
    file_alert = st.file_uploader("🚨 Base alertas (.xlsx) - sheet 'TOATE ALERTELE'", type=["xlsx"])

    if not (file_loc and file_alert):
        st.info("Carrega as duas bases para começar.")
        st.stop()

    loc_bytes = file_loc.getvalue()
    alert_bytes = file_alert.getvalue()

    # -----------------------------
    # LOAD + MERGE
    # -----------------------------
    with st.spinner("A ler e cruzar dados..."):
        df_base, issues_all = prepare_merged_df(loc_bytes, alert_bytes, user_lat, user_lon)

    if df_base.empty:
        st.error("Após cruzamento, não há sites (Cod Site vs Site code). Verifica os ficheiros.")
        st.stop()

    # inicializa issues (uma vez)
    if not st.session_state.selected_issues:
        st.session_state.selected_issues = issues_all

    # -----------------------------
    # SIDEBAR: LEGENDA + FILTROS
    # -----------------------------
    st.sidebar.header("Mapa")
    st.sidebar.markdown("### Legenda")
    st.sidebar.markdown(
        """
<div style="line-height:1.8;">
  <span style="display:inline-block;width:12px;height:12px;background:green;border-radius:50%;margin-right:8px;"></span>
  <b>Verde</b> = OnAir<br>
  <span style="display:inline-block;width:12px;height:12px;background:red;border-radius:50%;margin-right:8px;"></span>
  <b>Vermelho</b> = Down<br>
  <span style="display:inline-block;width:12px;height:12px;background:black;border-radius:50%;margin-right:8px;"></span>
  <b>Preto</b> = Infra Down
</div>
""",
        unsafe_allow_html=True
    )

    st.sidebar.header("Pesquisa / Filtros")
    with st.sidebar.form("filters_form"):
        lant_code = st.text_input("Pesquisar por Lant (opcional)", value=st.session_state.lant_code).strip()

        use_cluster = st.toggle("Agrupar pontos (Cluster)", value=st.session_state.use_cluster)
        show_table = st.toggle("Mostrar tabela", value=st.session_state.show_table)
        show_comments = st.toggle("Mostrar comentários", value=st.session_state.show_comments)

        selected_issues = st.multiselect(
            "Issues (vazio = mostra tudo)",
            options=issues_all,
            default=st.session_state.selected_issues
        )

        apply_btn = st.form_submit_button("Aplicar")

    if apply_btn:
        st.session_state.lant_code = lant_code
        st.session_state.use_cluster = use_cluster
        st.session_state.show_table = show_table
        st.session_state.show_comments = show_comments
        st.session_state.selected_issues = selected_issues
        st.session_state.route_sites = []  # limpa rota ao mexer em filtros

    # -----------------------------
    # APLICAR FILTROS (ORDEM IMPORTA)
    # 1) LANT primeiro (para garantir chain inteira)
    # 2) Issues depois (opcional)
    # -----------------------------
    df = df_base.copy()

    # ---- LANT (FORTE) ----
    lant_val = _norm_code(st.session_state.lant_code)

    if lant_val:
        if "Lant" not in df.columns:
            st.warning("Coluna 'Lant' não encontrada no ficheiro de alertas.")
            df = df.iloc[0:0].copy()
        else:
            # normalizar coluna Lant no DF
            df["Lant"] = df["Lant"].map(_norm_code)
            df_lant = df[df["Lant"] == lant_val].copy()

            if df_lant.empty:
                st.warning(f"Nenhum site encontrado para Lant '{lant_val}'.")
                df = df.iloc[0:0].copy()
            else:
                df = df_lant

    # ---- ISSUES (se vazio -> não filtra) ----
    if st.session_state.selected_issues:
        df = df[df["Issue"].astype(str).isin(st.session_state.selected_issues)].copy()

    # -----------------------------
    # ROTA (SEM JAVA) - aparece se houver sites
    # -----------------------------
    route_order = []
    if not df.empty and lant_val:
        st.sidebar.header("Ligações (Chain)")
        sites_lant = sorted(df["Cod Site"].astype(str).str.strip().str.upper().unique().tolist())

        route_sites = st.sidebar.multiselect(
            "Seleciona sites pela ordem (1→2→3...)",
            options=sites_lant,
            default=st.session_state.route_sites
        )

        if st.sidebar.button("Aplicar ligações"):
            st.session_state.route_sites = route_sites

    valid_sites = set(df["Cod Site"].astype(str).str.upper()) if not df.empty else set()
    route_order = [s for s in st.session_state.route_sites if s.upper() in valid_sites]

    # -----------------------------
    # MÉTRICAS
    # -----------------------------
    total = len(df)
    onair = (df["Tip Alarma"].astype(str).str.strip().str.lower() == "onair").sum() if not df.empty else 0
    down = (df["Tip Alarma"].astype(str).str.strip().str.lower() == "down").sum() if not df.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Sites no mapa", int(total))
    c2.metric("OnAir", int(onair))
    c3.metric("Down", int(down))

    if lant_val:
        st.caption(f"Filtro Lant ativo: **{lant_val}**")

    # -----------------------------
    # MAPA (BLINDADO)
    # -----------------------------
    if df.empty:
        st.warning("Nenhum site corresponde aos filtros aplicados.")
        st.stop()

    try:
        with st.spinner("A renderizar mapa..."):
            mapa = build_map(
                df=df,
                user_lat=user_lat,
                user_lon=user_lon,
                use_cluster=st.session_state.use_cluster,
                route_order=route_order
            )
            folium_static(mapa, width=1600, height=650)
    except Exception as e:
        st.error("Erro ao renderizar o mapa.")
        st.exception(e)

    # -----------------------------
    # TABELA (OPCIONAL)
    # -----------------------------
    if st.session_state.show_table:
        st.subheader("📊 Tabela")
        st.dataframe(df.reset_index(drop=True))

    # -----------------------------
    # COMENTÁRIOS (OPCIONAL)
    # -----------------------------
    if st.session_state.show_comments:
        st.subheader("📝 Comentários (sites visíveis)")
        if "Comments" not in df.columns:
            st.info("Coluna 'Comments' não encontrada.")
        else:
            df_comments = df[["Cod Site", "Issue", "Comments"]].copy()
            df_comments["Comments"] = df_comments["Comments"].astype(str).str.strip()
            df_comments = df_comments[
                df_comments["Comments"].ne("") &
                df_comments["Comments"].str.lower().ne("nan")
            ]
            if df_comments.empty:
                st.info("Sem comentários para os sites visíveis.")
            else:
                st.dataframe(df_comments.reset_index(drop=True))


if __name__ == "__main__":
    main()
