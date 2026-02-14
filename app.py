import re
import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from streamlit_geolocation import streamlit_geolocation
from map.map_builder import build_map


# =====================================================
# CONFIG
# =====================================================
st.set_page_config(layout="wide", page_title="Field Map Tools V4 - Alerts (Fast + Lant)")
st.title("FIELD MAP TOOLS V4 - ALERTS")


# =====================================================
# HELPERS
# =====================================================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.replace("\n", " ", regex=False)
        .str.replace("\r", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    return df


def pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = list(df.columns)
    cols_upper = {c.upper().strip(): c for c in cols}

    for cand in candidates:
        key = cand.upper().strip()
        if key in cols_upper:
            return cols_upper[key]

    for c in cols:
        cu = c.upper().strip()
        for cand in candidates:
            if cand.upper().strip() in cu:
                return c

    return None


def norm_cell(x) -> str:
    s = "" if x is None else str(x)
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# =====================================================
# CACHE (PESADO)
# =====================================================
@st.cache_data(show_spinner=False)
def read_locations_from_bytes(loc_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(loc_bytes)
    df = normalize_columns(df)

    cod = pick_col(df, ["Cod Site", "COD SITE", "CODSITE", "SITE", "SITE CODE", "CODE"])
    lat = pick_col(df, ["Latitudine", "LATITUDINE", "LATITUDE", "LAT"])
    lon = pick_col(df, ["Longitudine", "LONGITUDINE", "LONGITUDE", "LON", "LNG"])

    if not cod or not lat or not lon:
        raise ValueError("Base de localizações inválida.")

    df = df.rename(columns={cod: "Cod Site", lat: "Latitudine", lon: "Longitudine"})
    df = df.dropna(subset=["Cod Site", "Latitudine", "Longitudine"])
    df["Cod Site"] = df["Cod Site"].astype(str).str.strip().str.upper()
    return df


@st.cache_data(show_spinner=False)
def read_alerts_from_bytes(alert_bytes: bytes) -> pd.DataFrame:
    xls = pd.ExcelFile(alert_bytes)

    sheet = None
    for name in xls.sheet_names:
        if str(name).strip().upper() == "TOATE ALERTELE":
            sheet = name
            break
    if sheet is None:
        sheet = xls.sheet_names[0]

    df = pd.read_excel(alert_bytes, sheet_name=sheet)
    df = normalize_columns(df)

    cod = pick_col(df, ["Site code", "SITE CODE", "Cod Site", "COD SITE", "SITE", "CODE"])
    issue = pick_col(df, ["Issue", "ISSUE"])
    tip = pick_col(df, ["Tip Alarma", "TIP ALARMA", "STATUS", "TYPE"])
    gw = pick_col(df, ["GW", "GW/NGW", "GW / NGW"])
    comments = pick_col(df, ["Comments", "COMMENT", "NOTES", "NOTE", "OBS"])
    lant = pick_col(df, ["Lant", "LANT", "LANT CODE", "LANTCODE"])

    if not cod or not issue or not tip or not gw:
        raise ValueError(f"Base de alertas inválida. Colunas: {list(df.columns)}")

    rename_map = {cod: "Cod Site", issue: "Issue", tip: "Tip Alarma", gw: "GW"}
    if comments:
        rename_map[comments] = "Comments"
    if lant:
        rename_map[lant] = "Lant"

    df = df.rename(columns=rename_map)
    df = df.dropna(subset=["Cod Site"])
    df["Cod Site"] = df["Cod Site"].astype(str).str.strip().str.upper()

    df["Issue"] = df["Issue"].apply(norm_cell)
    df["Tip Alarma"] = df["Tip Alarma"].apply(norm_cell)
    df["GW"] = df["GW"].apply(norm_cell)
    if "Comments" in df.columns:
        df["Comments"] = df["Comments"].apply(norm_cell)
    if "Lant" in df.columns:
        df["Lant"] = df["Lant"].apply(norm_cell)

    cols = ["Cod Site", "Issue", "Tip Alarma", "GW"]
    if "Comments" in df.columns:
        cols.append("Comments")
    if "Lant" in df.columns:
        cols.append("Lant")

    return df[cols]


@st.cache_data(show_spinner=False)
def prepare_df(loc_bytes: bytes, alert_bytes: bytes, lat: float, lon: float) -> pd.DataFrame:
    df_loc = read_locations_from_bytes(loc_bytes)
    df_alert = read_alerts_from_bytes(alert_bytes)

    # só sites do TOATE ALERTELE
    df = df_loc.merge(df_alert, on="Cod Site", how="inner")

    df["Distância (km)"] = [
        geodesic((lat, lon), (a, b)).km
        for a, b in zip(df["Latitudine"], df["Longitudine"])
    ]
    return df.sort_values(by="Distância (km)")


@st.cache_data(show_spinner=False)
def render_map_html(df_json: str, lat: float, lon: float, use_cluster: bool, route_key: str) -> str:
    df = pd.read_json(df_json)
    route_order = [] if not route_key else route_key.split("|")
    mapa = build_map(df, lat, lon, use_cluster=use_cluster, route_order=route_order)
    return mapa.get_root().render()


# =====================================================
# GEOLOCATION (FIX: session_state + botão refresh)
# =====================================================
st.sidebar.header("Localização")

if "user_lat" not in st.session_state:
    st.session_state.user_lat = None
if "user_lon" not in st.session_state:
    st.session_state.user_lon = None

manual = st.sidebar.toggle("Inserir localização manualmente", value=False)

if manual:
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
            st.sidebar.warning("Não consegui obter localização. Verifica permissões do browser.")

if st.session_state.user_lat is None or st.session_state.user_lon is None:
    st.info("Permite localização no browser (ou usa modo manual).")
    st.stop()

lat = float(st.session_state.user_lat)
lon = float(st.session_state.user_lon)


# =====================================================
# UPLOAD
# =====================================================
file_loc = st.file_uploader("📍 Base localizações", type=["xlsx"])
file_alert = st.file_uploader("🚨 Base alertas (TOATE ALERTELE)", type=["xlsx"])

if not (file_loc and file_alert):
    st.info("Carrega as duas bases para começar.")
    st.stop()

loc_bytes = file_loc.getvalue()
alert_bytes = file_alert.getvalue()

with st.spinner("A preparar dados (1ª vez pode demorar)..."):
    df_base = prepare_df(loc_bytes, alert_bytes, lat, lon)

issues_all = sorted([i for i in df_base["Issue"].dropna().astype(str).unique() if i.strip()])


# =====================================================
# SESSION DEFAULTS
# =====================================================
if "use_cluster" not in st.session_state:
    st.session_state.use_cluster = False  # cluster OFF por defeito
if "show_comments" not in st.session_state:
    st.session_state.show_comments = False
if "show_table" not in st.session_state:
    st.session_state.show_table = False
if "selected_issues" not in st.session_state:
    st.session_state.selected_issues = issues_all
if "lant_code" not in st.session_state:
    st.session_state.lant_code = ""
if "route_sites" not in st.session_state:
    st.session_state.route_sites = []


# =====================================================
# SIDEBAR: LEGENDA + FORM (APLICAR)
# =====================================================
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
        "Issues",
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
    st.session_state.route_sites = []  # limpa rota quando mexes em filtros


# =====================================================
# FILTRAR DATA
# =====================================================
df = df_base.copy()

if st.session_state.selected_issues:
    df = df[df["Issue"].astype(str).isin(st.session_state.selected_issues)].copy()
else:
    df = df.iloc[0:0].copy()

lant_active = False
lant_val = st.session_state.lant_code.strip()
if lant_val:
    lant_active = True
    if "Lant" not in df.columns:
        st.warning("A coluna 'Lant' não existe no TOATE ALERTELE.")
        df = df.iloc[0:0].copy()
    else:
        df = df[df["Lant"].astype(str).str.strip().str.upper() == lant_val.upper()].copy()


# =====================================================
# CRIAR LIGAÇÕES (CHAIN)
# =====================================================
route_key = ""
if lant_active and not df.empty:
    st.sidebar.header("Ligações (Chain)")

    sites_lant = sorted(df["Cod Site"].astype(str).str.strip().str.upper().unique().tolist())

    route_sites = st.sidebar.multiselect(
        "Seleciona sites pela ordem (1→2→3...)",
        options=sites_lant,
        default=st.session_state.route_sites
    )

    if st.sidebar.button("Aplicar ligações"):
        st.session_state.route_sites = route_sites

    route_key = "|".join(st.session_state.route_sites)


# =====================================================
# MÉTRICAS
# =====================================================
total = len(df)
onair = (df["Tip Alarma"].astype(str).str.strip().str.lower() == "onair").sum()
down = (df["Tip Alarma"].astype(str).str.strip().str.lower() == "down").sum()

c1, c2, c3 = st.columns(3)
c1.metric("Sites no mapa", int(total))
c2.metric("OnAir", int(onair))
c3.metric("Down", int(down))

if lant_active:
    st.caption(f"Filtro Lant ativo: **{lant_val}**")


# =====================================================
# MAPA (CACHE HTML)
# =====================================================
with st.spinner("A renderizar mapa..."):
    df_json = df.to_json()
    html = render_map_html(df_json, lat, lon, st.session_state.use_cluster, route_key)
    st.components.v1.html(html, height=650)


# =====================================================
# TABELA (OPCIONAL)
# =====================================================
if st.session_state.show_table:
    st.subheader("📊 Tabela")
    st.dataframe(df.reset_index(drop=True))


# =====================================================
# COMENTÁRIOS (OPCIONAL)
# =====================================================
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
            st.info("Sem comentários.")
        else:
            st.dataframe(df_comments.reset_index(drop=True))
