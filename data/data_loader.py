import pandas as pd
import streamlit as st


@st.cache_data
def load_and_merge(location_file, alerts_file):

    df_loc = pd.read_excel(location_file)

    required_loc_cols = ["Latitudine", "Longitudine", "Cod Site"]
    if not all(col in df_loc.columns for col in required_loc_cols):
        raise ValueError("Base de localizações inválida.")

    df_loc = df_loc.dropna(subset=required_loc_cols)
    df_loc["Cod Site"] = (
        df_loc["Cod Site"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df_alert = pd.read_excel(
        alerts_file,
        sheet_name="TOATE ALERTELE"
    )

    required_alert_cols = ["Cod Site", "Issue", "Tip Alarma", "GW"]
    if not all(col in df_alert.columns for col in required_alert_cols):
        raise ValueError("Base de alertas inválida.")

    df_alert["Cod Site"] = (
        df_alert["Cod Site"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df = df_loc.merge(
        df_alert[["Cod Site", "Issue", "Tip Alarma", "GW"]],
        on="Cod Site",
        how="left"
    )

    return df
