from __future__ import annotations

import re
from io import BytesIO
import pandas as pd
import streamlit as st

from utils.geo_utils import compute_distances_km


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.replace("\n", " ", regex=False)
        .str.replace("\r", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    return df


def _pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
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


def _norm_cell(x) -> str:
    s = "" if x is None else str(x)
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


@st.cache_data(show_spinner=False)
def _read_locations(loc_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(BytesIO(loc_bytes))
    df = _normalize_columns(df)

    cod = _pick_col(df, ["Cod Site", "COD SITE", "CODSITE", "SITE", "SITE CODE", "CODE"])
    lat = _pick_col(df, ["Latitudine", "LATITUDINE", "LATITUDE", "LAT"])
    lon = _pick_col(df, ["Longitudine", "LONGITUDINE", "LONGITUDE", "LON", "LNG"])

    if not cod or not lat or not lon:
        raise ValueError(f"Base de localizações inválida. Colunas: {list(df.columns)}")

    df = df.rename(columns={cod: "Cod Site", lat: "Latitudine", lon: "Longitudine"})
    df = df.dropna(subset=["Cod Site", "Latitudine", "Longitudine"])

    df["Cod Site"] = df["Cod Site"].astype(str).str.strip().str.upper()
    df["Latitudine"] = pd.to_numeric(df["Latitudine"], errors="coerce")
    df["Longitudine"] = pd.to_numeric(df["Longitudine"], errors="coerce")
    df = df.dropna(subset=["Latitudine", "Longitudine"])

    return df


@st.cache_data(show_spinner=False)
def _read_alerts(alert_bytes: bytes) -> pd.DataFrame:
    xls = pd.ExcelFile(BytesIO(alert_bytes))

    sheet = None
    for name in xls.sheet_names:
        if str(name).strip().upper() == "TOATE ALERTELE":
            sheet = name
            break
    if sheet is None:
        sheet = xls.sheet_names[0]

    df = pd.read_excel(BytesIO(alert_bytes), sheet_name=sheet)
    df = _normalize_columns(df)

    cod = _pick_col(df, ["Site code", "SITE CODE", "Cod Site", "COD SITE", "SITE", "CODE"])
    issue = _pick_col(df, ["Issue", "ISSUE"])
    tip = _pick_col(df, ["Tip Alarma", "TIP ALARMA", "STATUS", "TYPE"])
    gw = _pick_col(df, ["GW", "GW/NGW", "GW / NGW"])
    comments = _pick_col(df, ["Comments", "COMMENT", "NOTES", "NOTE", "OBS"])
    lant = _pick_col(df, ["Lant", "LANT", "LANT CODE", "LANTCODE"])

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
    df["Issue"] = df["Issue"].apply(_norm_cell)
    df["Tip Alarma"] = df["Tip Alarma"].apply(_norm_cell)
    df["GW"] = df["GW"].apply(_norm_cell)

    if "Comments" in df.columns:
        df["Comments"] = df["Comments"].apply(_norm_cell)
    if "Lant" in df.columns:
        df["Lant"] = df["Lant"].apply(_norm_cell)

    cols = ["Cod Site", "Issue", "Tip Alarma", "GW"]
    if "Comments" in df.columns:
        cols.append("Comments")
    if "Lant" in df.columns:
        cols.append("Lant")

    return df[cols]


@st.cache_data(show_spinner=False)
def prepare_merged_df(loc_bytes: bytes, alert_bytes: bytes, user_lat: float, user_lon: float):
    df_loc = _read_locations(loc_bytes)
    df_alert = _read_alerts(alert_bytes)

    # Só sites que existem no TOATE ALERTELE
    df = df_loc.merge(df_alert, on="Cod Site", how="inner")

    # Distâncias (cacheado via cache_data do caller)
    df["Distância (km)"] = compute_distances_km(user_lat, user_lon, df["Latitudine"].tolist(), df["Longitudine"].tolist())

    df = df.sort_values(by="Distância (km)", ascending=True)

    issues_all = sorted([x for x in df["Issue"].dropna().astype(str).unique().tolist() if str(x).strip()])

    return df, issues_all
