"""Arma outputs/dashboard.html: una sola página autocontenida (datos + imágenes embebidas).

Entrada : todo lo que dejan 01-04 en outputs/, data/distritos.geojson, data/anp_*.geojson
Salida  : outputs/dashboard.html, outputs/mapa_situacion.png
"""
import base64
import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT, SRC = ROOT / "data", ROOT / "outputs", ROOT / "src"


def b64(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def geo(gdf: gpd.GeoDataFrame, tol: float) -> dict:
    g = gdf.copy()
    g["geometry"] = g.geometry.simplify(tol, preserve_topology=True)
    return json.loads(g.to_json(drop_id=True))


def registros(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    for c in df.select_dtypes("number"):
        df[c] = df[c].round(3)
    return df.astype(object).where(df.notna(), None).to_dict("records")


def main() -> None:
    dist = gpd.read_file(DATA / "distritos.geojson")
    deps = dist.dissolve("NOMBDEP").reset_index()[["NOMBDEP", "geometry"]]

    anp = pd.concat([
        gpd.read_file(DATA / "anp_0.geojson")[["anp_nomb", "geometry"]].rename(columns={"anp_nomb": "anp"}),
        gpd.read_file(DATA / "anp_2.geojson")[["acr_nomb", "geometry"]].rename(columns={"acr_nomb": "anp"}),
    ])
    # fuera las reservas marinas: en un mapa de incendios solo distraen
    anp = anp[~anp.anp.str.contains("Dorsal de Nasca|Islas, Islotes|Mar Tropical", na=False)]

    inc = gpd.read_file(OUT / "incendios_contexto.geojson")
    cols = ["incendio_id", "distrito", "provincia", "departamento", "n_focos", "focos_24h",
            "focos_48h", "huella_ha", "frp_total", "poblacion_5km", "anp_cercana", "dist_anp_km",
            "hr_min", "viento_max", "lluvia_3d", "tmax", "estado", "cobertura", "verificar", "inicio",
            "ultimo", "lat", "lon"]

    focos = gpd.read_file(OUT / "focos_limpios.geojson")
    corte = pd.to_datetime(focos.fecha_lima).max()
    f48 = focos[pd.to_datetime(focos.fecha_lima) >= corte - pd.Timedelta(hours=48)]
    por_dia = (pd.to_datetime(focos.fecha_lima).dt.strftime("%Y-%m-%d").value_counts()
               .sort_index().to_dict())

    # coroplético: solo distritos con focos en la semana
    dfocos = pd.read_csv(OUT / "distritos_focos.csv", dtype={"IDDIST": str}, encoding="utf-8-sig")
    dgeo = dist.merge(dfocos[["IDDIST", "focos_7d", "focos_24h"]], on="IDDIST")
    dgeo = dgeo[["IDDIST", "NOMBDIST", "NOMBPROV", "NOMBDEP", "focos_7d", "focos_24h", "geometry"]]

    matriz = pd.read_csv(OUT / "departamentos_dia.csv", encoding="utf-8-sig", index_col=0)
    matriz = matriz.loc[matriz.sum(axis=1).sort_values(ascending=False).index]

    limpio = lambda c: c.replace("_%", "")
    datos = {
        "corte": corte.strftime("%d-%m-%Y %H:%M"),
        "n_focos": int(len(focos)),
        "focos_24h": int((pd.to_datetime(focos.fecha_lima) >= corte - pd.Timedelta(hours=24)).sum()),
        "focos_por_dia": por_dia,
        "incendios": registros(inc[cols]),
        "focos48": f48[["latitude", "longitude"]].round(4).values.tolist(),
        "distritos": registros(dfocos.head(15)),
        "n_distritos": int(len(dfocos)),
        "dist_geo": geo(dgeo, 0.004),
        "matriz": {"deps": matriz.index.tolist(), "dias": matriz.columns.tolist(),
                   "valores": matriz.values.tolist()},
        "historia": pd.read_csv(OUT / "historia_octubre.csv").rename(columns=limpio).to_dict("records"),
        "hist_dep": registros(pd.read_csv(OUT / "historia_departamentos.csv", encoding="utf-8-sig")
                              .rename(columns=limpio)),
        "hist_meta": json.loads((OUT / "historia_meta.json").read_text(encoding="utf-8")),
        "calibracion": pd.read_csv(OUT / "calibracion_inpe_firms.csv").rename(columns=limpio)
        .to_dict("records"),
        "anp": registros(pd.read_csv(OUT / "anp_afectadas.csv", encoding="utf-8-sig")),
        "dnbr": json.loads((OUT / "dnbr_resumen.json").read_text(encoding="utf-8")),
        "departamentos": geo(deps, 0.01),
        "anp_geo": geo(anp, 0.005),
        "overlay": b64(OUT / "dnbr_overlay.png"),
    }
    html = (SRC / "dashboard_template.html").read_text(encoding="utf-8")
    html = (html.replace("/*__LEAFLET_CSS__*/", (DATA / "leaflet.css").read_text(encoding="utf-8"))
            .replace("__FIGURA_DNBR__", b64(OUT / "dnbr_curahuasi.png"))
            .replace("__DATOS__", json.dumps(datos, ensure_ascii=False, default=str)))
    (OUT / "dashboard.html").write_text(html, encoding="utf-8")
    print(f"dashboard.html: {len(html) / 1e6:.1f} MB")

    # mapa estático para el README: focos por distrito (escala log) + incendios activos
    fig, ax = plt.subplots(figsize=(7, 9))
    deps.plot(ax=ax, color="#e9eef0", edgecolor="#b8c5cb", linewidth=0.5)
    dgeo.assign(log=np.log10(dgeo.focos_7d)).plot(ax=ax, column="log", cmap="YlOrRd",
                                                  linewidth=0, legend=True,
                                                  legend_kwds={"label": "focos en 7 días (log10)",
                                                               "shrink": 0.5})
    act = inc[inc.activo_48h & ~inc.verificar]
    ax.scatter(act.lon, act.lat, s=act.huella_ha / 5, facecolors="none", edgecolors="#15232b",
               linewidths=1, label=f"incendios > 100 ha activos en 48 h ({len(act)})")
    for _, r in act.nlargest(6, "huella_ha").iterrows():
        ax.annotate(r.distrito.title(), (r.lon, r.lat), xytext=(6, 4), textcoords="offset points",
                    fontsize=7.5)
    ax.legend(loc="lower left", fontsize=7.5, frameon=False)
    ax.set_title(f"Focos de calor por distrito, 14–21 oct. 2026 · corte {datos['corte']} h",
                 fontsize=10)
    ax.set_axis_off()
    fig.savefig(OUT / "mapa_situacion.png", dpi=130, bbox_inches="tight")


if __name__ == "__main__":
    main()
