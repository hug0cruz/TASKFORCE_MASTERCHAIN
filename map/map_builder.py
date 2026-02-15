import re
import folium
from folium.plugins import MarkerCluster


BLACK_ISSUES = {
    "FALLEN TOWER",
    "FORBIDDEN TOWER",
    "FALLEN MAST",
    "INFRA",
}


def _norm_text(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper()


def build_map(df, user_lat, user_lon, use_cluster=True, route_order=None):
    if route_order is None:
        route_order = []

    mapa = folium.Map(location=[user_lat, user_lon], zoom_start=10, control_scale=True)

    # utilizador
    folium.Marker(
        location=[user_lat, user_lon],
        popup="📍 Tu estás aqui",
        icon=folium.Icon(color="blue", icon="user"),
    ).add_to(mapa)

    layer = MarkerCluster().add_to(mapa) if use_cluster else mapa

    # markers
    for _, row in df.iterrows():
        lat = float(row["Latitudine"])
        lon = float(row["Longitudine"])

        cod = _norm_text(row.get("Cod Site", "SEM_CODIGO"))
        issue_raw = row.get("Issue", "Sem alerta")
        issue_clean = re.sub(r"\s+", " ", str(issue_raw).replace("\n", " ").replace("\r", " ")).strip()
        issue_u = _norm_text(issue_raw)

        tip = _norm_text(row.get("Tip Alarma", ""))
        gw_type = _norm_text(row.get("GW", ""))

        # cor
        if issue_u in BLACK_ISSUES:
            color = "black"
        else:
            if tip == "ONAIR":
                color = "green"
            elif tip == "DOWN":
                color = "red"
            else:
                color = "gray"

        popup_html = f"""
        <div style="min-width:190px;">
          <b style="font-size:14px;">{cod}</b><br>
          <div style="margin-top:6px; padding:4px 8px; display:inline-block;
                      border-radius:6px; background:rgba(0,0,0,0.08);">
            <span style="color:{color}; font-weight:700;">⚑ {issue_clean}</span>
          </div>
          <div style="margin-top:6px; font-size:12px; color:#333;">
            Tip Alarma: {row.get("Tip Alarma", "")}<br>
            Tipo: {row.get("GW", "")}<br>
            Lant: {row.get("Lant", "")}
          </div>
        </div>
        """

        if gw_type == "GW":
            icon_html = f"""
            <div style="text-align:center; line-height:1;">
              <div style="font-size:22px; color:{color};">★</div>
              <div style="font-size:11px; font-weight:700; color:#000; margin-top:2px;">{cod}</div>
            </div>
            """
            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(html=icon_html, icon_size=(40,40), icon_anchor=(20,20) ),
                popup=folium.Popup(popup_html, max_width=320),
            ).add_to(layer)
        else:
            folium.CircleMarker(
                location=[lat, lon],
                radius=7,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=1,
            ).add_to(layer)

            # label afastado
            label_html = f"""
            <div style="
                position: relative;
                left: 10px;
                top: -18px;
                font-size: 11px;
                font-weight: 700;
                color: #000;
                white-space: nowrap;
                text-shadow: 0 0 2px rgba(255,255,255,0.8);
            ">{cod}</div>
            """
            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(html=label_html),
                popup=folium.Popup(popup_html, max_width=320),
            ).add_to(layer)

    # rota (linha)
    if route_order:
        df_idx = df.copy()
        df_idx["Cod Site"] = df_idx["Cod Site"].astype(str).map(_norm_text)
        coords_by_site = {
            r["Cod Site"]: (float(r["Latitudine"]), float(r["Longitudine"]))
            for _, r in df_idx.iterrows()
        }

        route_points = []
        for s in route_order:
            su = _norm_text(s)
            if su in coords_by_site:
                route_points.append(coords_by_site[su])

        if len(route_points) >= 2:
            folium.PolyLine(route_points, color="black", weight=2, opacity=1).add_to(mapa)

    return mapa
