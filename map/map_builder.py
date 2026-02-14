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
    """
    - Clique em ponto/estrela para construir rota (JS no Leaflet)
    - Opcional: route_order (Python) desenha uma linha fixa adicional
    """
    if route_order is None:
        route_order = []

    mapa = folium.Map(
        location=[user_lat, user_lon],
        zoom_start=10,
        control_scale=True
    )
    map_var = mapa.get_name()

    # Utilizador
    folium.Marker(
        location=[user_lat, user_lon],
        popup="📍 Tu estás aqui",
        icon=folium.Icon(color="blue", icon="user")
    ).add_to(mapa)

    layer = MarkerCluster().add_to(mapa) if use_cluster else mapa

    # Guardar info dos markers para ligar clicks via JS
    markers_js = []  # list of dicts: {var, code, lat, lon}

    # --- markers ---
    for _, row in df.iterrows():
        lat = float(row["Latitudine"])
        lon = float(row["Longitudine"])

        cod = _norm_text(row.get("Cod Site", ""))
        issue_raw = row.get("Issue", "Sem alerta")
        issue_clean = re.sub(r"\s+", " ", str(issue_raw).replace("\n", " ").replace("\r", " ")).strip()
        issue_u = _norm_text(issue_raw)

        tip = _norm_text(row.get("Tip Alarma", ""))
        gw_type = _norm_text(row.get("GW", ""))

        # cor (sem glow)
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

        # GW -> estrela + código
        if gw_type == "GW":
            icon_html = f"""
            <div style="text-align:center; line-height:1;">
              <div style="font-size:22px; color:{color};">★</div>
              <div style="font-size:11px; font-weight:700; color:#000; margin-top:2px;">{cod}</div>
            </div>
            """
            m = folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(html=icon_html),
                popup=folium.Popup(popup_html, max_width=320)
            )
            m.add_to(layer)
            markers_js.append({"var": m.get_name(), "code": cod, "lat": lat, "lon": lon})

        # NGW -> bolinha + label afastado
        else:
            c = folium.CircleMarker(
                location=[lat, lon],
                radius=7,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=1
            )
            c.add_to(layer)
            markers_js.append({"var": c.get_name(), "code": cod, "lat": lat, "lon": lon})

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
                popup=folium.Popup(popup_html, max_width=320)
            ).add_to(layer)

    # --- linha (rota fixa do Python) ---
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
            folium.PolyLine(
                locations=route_points,
                weight=4,
                opacity=0.9,
            ).add_to(mapa)

    # --- JS Interativo: selecionar pontos e desenhar linha ---
    # Montar array JS com os markers
    markers_array_js = ",\n".join(
        [f'{{varName: "{m["var"]}", code: "{m["code"]}", lat: {m["lat"]}, lon: {m["lon"]}}}' for m in markers_js]
    )

    js = f"""
    <script>
    (function() {{
      // evita duplicar se o Streamlit rerun re-injetar
      if (window.__routeTool_{map_var}) return;
      window.__routeTool_{map_var} = true;

      var map = {map_var};
      var selecting = false;
      var selectedCodes = [];
      var selectedLatLngs = [];
      var poly = null;

      function updatePanel() {{
        var listEl = document.getElementById("routeList_{map_var}");
        var countEl = document.getElementById("routeCount_{map_var}");
        if (!listEl || !countEl) return;

        countEl.textContent = selectedCodes.length.toString();
        listEl.textContent = selectedCodes.join(" → ");
      }}

      function ensurePolyline() {{
        if (!poly) {{
          poly = L.polyline([], {{ weight: 4, opacity: 0.9 }}).addTo(map);
        }}
      }}

      function addPoint(code, lat, lon) {{
        if (!selecting) return;

        selectedCodes.push(code);
        selectedLatLngs.push([lat, lon]);

        ensurePolyline();
        poly.setLatLngs(selectedLatLngs);
        updatePanel();
      }}

      function clearRoute() {{
        selectedCodes = [];
        selectedLatLngs = [];
        if (poly) poly.setLatLngs([]);
        updatePanel();
      }}

      async function copyRoute() {{
        var text = selectedCodes.join(" ");
        if (!text) return;

        try {{
          await navigator.clipboard.writeText(text);
          alert("Copiado: " + text);
        }} catch (e) {{
          // fallback tosco mas funciona
          prompt("Copia manualmente:", text);
        }}
      }}

      // Control UI
      var RouteControl = L.Control.extend({{
        onAdd: function(map) {{
          var div = L.DomUtil.create('div', 'route-control');
          div.style.background = 'rgba(255,255,255,0.92)';
          div.style.padding = '10px';
          div.style.border = '2px solid #000';
          div.style.borderRadius = '10px';
          div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.2)';
          div.style.minWidth = '220px';
          div.style.fontFamily = 'system-ui, -apple-system, Segoe UI, Roboto, Arial';
          div.innerHTML = `
            <div style="font-weight:800; margin-bottom:6px;">Criar Ch
             (Clique nos pontos)</div>
            <button id="toggleSelect_{map_var}" style="width:100%; padding:6px; font-weight:700; cursor:pointer;">
              Modo Seleção: OFF
            </button>
            <div style="margin-top:8px; font-size:12px;">
              Selecionados: <b id="routeCount_{map_var}">0</b>
            </div>
            <div id="routeList_{map_var}" style="margin-top:6px; font-size:12px; max-height:70px; overflow:auto;"></div>
            <div style="display:flex; gap:6px; margin-top:8px;">
              <button id="clearRoute_{map_var}" style="flex:1; padding:6px; font-weight:700; cursor:pointer;">Limpar</button>
              <button id="copyRoute_{map_var}" style="flex:1; padding:6px; font-weight:700; cursor:pointer;">Copiar</button>
            </div>
          `;

          // Evitar o mapa apanhar clicks no painel
          L.DomEvent.disableClickPropagation(div);
          L.DomEvent.disableScrollPropagation(div);

          return div;
        }},
        onRemove: function(map) {{}}
      }});

      map.addControl(new RouteControl({{ position: 'topright' }}));

      // Wire UI
      setTimeout(function() {{
        var toggleBtn = document.getElementById("toggleSelect_{map_var}");
        var clearBtn = document.getElementById("clearRoute_{map_var}");
        var copyBtn = document.getElementById("copyRoute_{map_var}");

        if (toggleBtn) {{
          toggleBtn.addEventListener("click", function() {{
            selecting = !selecting;
            toggleBtn.textContent = "Modo Seleção: " + (selecting ? "ON" : "OFF");
            toggleBtn.style.background = selecting ? "#d1ffd6" : "";
          }});
        }}
        if (clearBtn) clearBtn.addEventListener("click", clearRoute);
        if (copyBtn) copyBtn.addEventListener("click", copyRoute);

        updatePanel();
      }}, 0);

      // Bind clicks nos markers do Folium
      var markers = [
        {markers_array_js}
      ];

      markers.forEach(function(m) {{
        try {{
          var obj = window[m.varName];
          if (obj && obj.on) {{
            obj.on('click', function() {{
              addPoint(m.code, m.lat, m.lon);
            }});
          }}
        }} catch(e) {{}}
      }});

    }})();
    </script>
    """

    mapa.get_root().html.add_child(folium.Element(js))

    return mapa
