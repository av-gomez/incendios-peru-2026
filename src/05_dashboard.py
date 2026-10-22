"""Arma outputs/dashboard.html: una sola página autocontenida (datos + imágenes embebidas).

Entrada : todo lo que dejan 01-04 en outputs/, data/distritos.geojson, data/anp_*.geojson
Salida  : outputs/dashboard.html
"""
import base64
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT, SRC = ROOT / "data", ROOT / "outputs", ROOT / "src"


def b64(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def geo(gdf: gpd.GeoDataFrame, tol: float) -> dict:
    g = gdf.copy()
    g["geometry"] = g.geometry.simplify(tol, preserve_topology=True)
    return json.loads(g.to_json(drop_id=True))


def main() -> None:
    dist = gpd.read_file(DATA / "distritos.geojson")
    deps = dist.dissolve("NOMBDEP").reset_index()[["NOMBDEP", "geometry"]]

    anp = pd.concat([
        gpd.read_file(DATA / "anp_0.geojson")[["anp_nomb", "geometry"]].rename(columns={"anp_nomb": "anp"}),
        gpd.read_file(DATA / "anp_2.geojson")[["acr_nomb", "geometry"]].rename(columns={"acr_nomb": "anp"}),
    ])
    # fuera las reservas marinas: en un mapa de incendios solo distraen
    anp = anp[~anp.anp.str.contains("Dorsal de Nasca|Islas, Islotes|Mar Tropical", na=False)]

    inc = gpd.read_file(OUT / "incendios_prioridad.geojson")
    cols = ["incendio_id", "distrito", "provincia", "departamento", "n_focos", "focos_48h",
            "huella_ha", "frp_total", "poblacion_5km", "anp_cercana", "dist_anp_km", "hr_min",
            "viento_max", "lluvia_3d", "prioridad", "nivel", "rango", "p_top10", "rango_p05",
            "rango_p95", "inicio", "ultimo", "lat", "lon"]
    inc_rec = inc[cols].round(3).astype(object).where(inc[cols].notna(), None).to_dict("records")

    focos = gpd.read_file(OUT / "focos_limpios.geojson")
    corte = pd.to_datetime(focos.fecha_lima).max()
    f48 = focos[pd.to_datetime(focos.fecha_lima) >= corte - pd.Timedelta(hours=48)]
    focos_48 = f48[["latitude", "longitude", "frp"]].round(4).values.tolist()
    por_dia = (pd.to_datetime(focos.fecha_lima).dt.strftime("%Y-%m-%d").value_counts()
               .sort_index().to_dict())

    limpio = lambda c: c.replace("_%", "")
    hist = pd.read_csv(OUT / "historia_octubre.csv").rename(columns=limpio).to_dict("records")
    hdep = (pd.read_csv(OUT / "historia_departamentos.csv", encoding="utf-8-sig")
            .rename(columns=limpio).to_dict("records"))
    anp_af = pd.read_csv(OUT / "anp_afectadas.csv", encoding="utf-8-sig").to_dict("records")
    dnbr = json.loads((OUT / "dnbr_resumen.json").read_text(encoding="utf-8"))

    datos = {
        "corte": corte.strftime("%d-%m-%Y %H:%M"),
        "n_focos": int(len(focos)), "focos_por_dia": por_dia,
        "incendios": inc_rec, "focos48": focos_48,
        "historia": hist, "hist_dep": hdep, "anp": anp_af, "dnbr": dnbr,
        "sensibilidad": pd.read_csv(OUT / "sensibilidad_pesos.csv", encoding="utf-8-sig")
        .to_dict("records"),
        "calibracion": pd.read_csv(OUT / "calibracion_inpe_firms.csv").rename(columns=limpio)
        .to_dict("records"),
        "departamentos": geo(deps, 0.01), "anp_geo": geo(anp, 0.005),
        "overlay": b64(OUT / "dnbr_overlay.png"),
    }
    html = (SRC / "dashboard_template.html").read_text(encoding="utf-8")
    html = (html.replace("/*__LEAFLET_CSS__*/", (DATA / "leaflet.css").read_text(encoding="utf-8"))
            .replace("__FIGURA_DNBR__", b64(OUT / "dnbr_curahuasi.png"))
            .replace("__DATOS__", json.dumps(datos, ensure_ascii=False, default=str)))
    (OUT / "dashboard.html").write_text(html, encoding="utf-8")

    # mapa estático para el README
    import matplotlib.pyplot as plt
    colores = {"Seguimiento": "#8f8a84", "Prioridad 2": "#e07b2c", "Prioridad 1": "#a3260f"}
    fig, ax = plt.subplots(figsize=(7, 9))
    deps.plot(ax=ax, color="#e8e3dd", edgecolor="#b9afa5", linewidth=0.5)
    gpd.GeoSeries(anp.geometry, crs=4326).plot(ax=ax, color="#3f8f5a", alpha=0.25, linewidth=0)
    ax.scatter(f48.longitude, f48.latitude, s=1, c="#d4a017", label="focos últimas 48 h")
    for nivel, c in colores.items():
        s = inc[inc.nivel == nivel]
        ax.scatter(s.lon, s.lat, s=s.huella_ha / 6, c=c, edgecolors="k", linewidths=0.4,
                   label=f"{nivel} ({len(s)})")
    for _, r in inc.head(10).iterrows():
        ax.annotate(f"{r.rango}. {r.distrito.title()}", (r.lon, r.lat), xytext=(6, 4),
                    textcoords="offset points", fontsize=7.5)
    ax.legend(loc="lower left", fontsize=7.5, frameon=False)
    ax.set_title(f"Incendios > 100 ha (7 días) · corte {datos['corte']} h Lima", fontsize=10)
    ax.set_axis_off()
    fig.savefig(OUT / "mapa_prioridad.png", dpi=130, bbox_inches="tight")
    print(f"dashboard.html: {len(html) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
