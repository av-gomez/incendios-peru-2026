"""Contexto de cada incendio: población (raster WorldPop), ANP (SERNANP) y clima (Open-Meteo).
Termina con el índice de prioridad 0-100.

Entrada : outputs/incendios.geojson, outputs/focos_limpios.geojson
          data/worldpop_per_2020_1km.tif, data/anp_0.geojson (nacionales), data/anp_2.geojson (regionales)
Salida  : outputs/incendios_prioridad.geojson, outputs/anp_afectadas.csv, outputs/distritos_ranking.csv
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from rasterstats import zonal_stats

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "outputs"
UTM = 32718
RADIO_M = 5_000
HUELLA_MIN_HA = 100          # igual que el monitor del profe: incendios con huella > 100 ha

PESOS = {"frp": 0.35, "activo": 0.20, "poblacion": 0.20, "anp": 0.10, "clima": 0.15}


def cargar_anp() -> gpd.GeoDataFrame:
    nac = gpd.read_file(DATA / "anp_0.geojson")[["anp_nomb", "anp_cate", "geometry"]]
    nac = nac.rename(columns={"anp_nomb": "anp", "anp_cate": "categoria"})
    reg = gpd.read_file(DATA / "anp_2.geojson")[["acr_nomb", "geometry"]]
    reg = reg.rename(columns={"acr_nomb": "anp"}).assign(categoria="Área de Conservación Regional")
    return pd.concat([nac, reg], ignore_index=True).to_crs(UTM)


def clima(inc: gpd.GeoDataFrame) -> pd.DataFrame:
    """Pronóstico de los próximos 3 días por incendio (una sola llamada, coordenadas en lote)."""
    filas = []
    for i in range(0, len(inc), 50):
        lote = inc.iloc[i:i + 50]
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": ",".join(f"{v:.4f}" for v in lote.lat),
            "longitude": ",".join(f"{v:.4f}" for v in lote.lon),
            "daily": "relative_humidity_2m_min,wind_speed_10m_max,precipitation_sum,temperature_2m_max",
            "forecast_days": 3, "timezone": "America/Lima"}, timeout=60)
        r.raise_for_status()
        datos = r.json()
        datos = datos if isinstance(datos, list) else [datos]
        for idx, d in zip(lote.index, datos):
            dd = d["daily"]
            filas.append({"idx": idx,
                          "hr_min": float(np.min(dd["relative_humidity_2m_min"])),
                          "viento_max": float(np.max(dd["wind_speed_10m_max"])),
                          "lluvia_3d": float(np.sum(dd["precipitation_sum"])),
                          "tmax": float(np.max(dd["temperature_2m_max"]))})
    return pd.DataFrame(filas).set_index("idx")


def pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True).fillna(0)


def main() -> None:
    inc = gpd.read_file(OUT / "incendios.geojson")
    inc = inc[inc.huella_ha > HUELLA_MIN_HA].reset_index(drop=True)

    # población a 5 km: buffer en metros (UTM) y zonal_stats sobre el raster WorldPop
    buf = inc.to_crs(UTM).buffer(RADIO_M).to_crs(4326)
    zs = zonal_stats(buf, DATA / "worldpop_per_2020_1km.tif", stats=["sum"],
                     nodata=-99999, all_touched=False)
    inc["poblacion_5km"] = [round(z["sum"] or 0) for z in zs]

    # áreas naturales protegidas: dentro o a menos de 5 km
    anp = cargar_anp()
    inc_utm = inc.to_crs(UTM)
    cerca = gpd.sjoin_nearest(inc_utm[["incendio_id", "geometry"]], anp, how="left",
                              distance_col="dist_anp_m")
    cerca = cerca.drop_duplicates("incendio_id").set_index("incendio_id")
    inc["anp_cercana"] = inc.incendio_id.map(cerca.anp)
    inc["dist_anp_km"] = (inc.incendio_id.map(cerca.dist_anp_m) / 1000).round(1)
    inc["anp_en_riesgo"] = inc.dist_anp_km <= 5

    # ANP con focos en los 7 días (todos los focos limpios, no solo incendios grandes)
    focos = gpd.read_file(OUT / "focos_limpios.geojson").to_crs(UTM)
    anp_buf = anp.copy()
    anp_buf["geometry"] = anp.buffer(0)
    en_anp = gpd.sjoin(focos[["frp", "geometry"]], anp_buf, predicate="within")
    tabla_anp = (en_anp.groupby(["anp", "categoria"]).agg(focos=("frp", "size"),
                                                         frp_total=("frp", "sum"))
                 .sort_values("focos", ascending=False).reset_index())
    tabla_anp.to_csv(OUT / "anp_afectadas.csv", index=False, encoding="utf-8-sig")
    print(f"ANP con focos dentro en 7 días: {len(tabla_anp)}")
    print(tabla_anp.head(10).to_string(index=False))

    # clima de los próximos 3 días
    cl = clima(inc)
    inc = inc.join(cl)
    # riesgo de propagación: seco, ventoso, sin lluvia (cada uno en percentiles)
    inc["riesgo_clima"] = ((1 - pct_rank(inc.hr_min)) + pct_rank(inc.viento_max)
                           + (inc.lluvia_3d < 1).astype(float)) / 3

    # índice de prioridad 0-100
    comp = pd.DataFrame({
        "frp": pct_rank(np.log1p(inc.frp_total)),
        "activo": pct_rank(inc.focos_48h) * (inc.focos_48h > 0),
        "poblacion": pct_rank(np.log1p(inc.poblacion_5km)),
        "anp": inc.anp_en_riesgo.astype(float),
        "clima": inc.riesgo_clima,
    })
    inc["prioridad"] = (sum(comp[k] * w for k, w in PESOS.items()) * 100).round(1)
    inc["nivel"] = pd.cut(inc.prioridad, [-1, 40, 60, 75, 101],
                          labels=["Baja", "Media", "Alta", "Crítica"]).astype(str)
    inc = inc.sort_values("prioridad", ascending=False)
    inc.to_file(OUT / "incendios_prioridad.geojson", driver="GeoJSON")

    print(f"\nincendios > {HUELLA_MIN_HA} ha: {len(inc)} | activos 48 h: {inc.activo_48h.sum()} | "
          f"con ANP a <= 5 km: {inc.anp_en_riesgo.sum()} | "
          f"personas a 5 km (suma): {inc.poblacion_5km.sum():,.0f}")
    print(inc.head(15)[["distrito", "departamento", "huella_ha", "focos_48h", "poblacion_5km",
                        "anp_cercana", "dist_anp_km", "hr_min", "viento_max", "prioridad",
                        "nivel"]].to_string(index=False))

    # ranking de distritos (todos los incendios grandes)
    dist = (inc.groupby(["ubigeo", "distrito", "provincia", "departamento"])
            .agg(incendios=("incendio_id", "size"), huella_ha=("huella_ha", "sum"),
                 frp_total=("frp_total", "sum"), focos_48h=("focos_48h", "sum"),
                 poblacion_5km=("poblacion_5km", "max"), prioridad_max=("prioridad", "max"))
            .sort_values("prioridad_max", ascending=False).reset_index())
    dist.to_csv(OUT / "distritos_ranking.csv", index=False, encoding="utf-8-sig")
    print("\nTop 10 distritos")
    print(dist.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
