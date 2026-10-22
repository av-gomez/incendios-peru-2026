"""Contexto de cada incendio: población (raster WorldPop), ANP (SERNANP) y clima (Open-Meteo).
Sin índices compuestos: cada variable se reporta por separado.

Entrada : outputs/incendios.geojson, outputs/focos_limpios.geojson
          data/worldpop_per_2020_1km.tif, data/anp_0.geojson (nacionales), data/anp_2.geojson (regionales)
Salida  : outputs/incendios_contexto.geojson, outputs/anp_afectadas.csv,
          outputs/distritos_focos.csv, outputs/departamentos_dia.csv
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


WORLDCOVER = {10: "Bosque", 20: "Arbustal", 30: "Pastizal", 40: "Cultivo", 50: "Urbano",
              60: "Suelo desnudo", 70: "Nieve", 80: "Agua", 90: "Humedal", 95: "Manglar",
              100: "Musgo/liquen"}


def cobertura_en_punto(inc: gpd.GeoDataFrame) -> list[str]:
    """Clase ESA WorldCover 2021 dominante en 300 x 300 m alrededor del centro de cada incendio."""
    import planetary_computer
    import pystac_client
    import rasterio
    from rasterio.windows import from_bounds

    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    clases = []
    for lat, lon in zip(inc.lat, inc.lon):
        item = next(cat.search(collections=["esa-worldcover"], intersects={
            "type": "Point", "coordinates": [lon, lat]}).items())
        with rasterio.open(item.assets["map"].href) as src:
            win = from_bounds(lon - 0.0015, lat - 0.0015, lon + 0.0015, lat + 0.0015, src.transform)
            v = src.read(1, window=win).ravel()
        v = v[v > 0]
        clases.append(WORLDCOVER.get(int(np.bincount(v).argmax()), "?") if v.size else "?")
    return clases


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

    # actividad reciente: focos en las últimas 24 h por incendio
    corte = pd.to_datetime(focos.fecha_utc).max()
    rec = focos[pd.to_datetime(focos.fecha_utc) >= corte - pd.Timedelta(hours=24)]
    inc["focos_24h"] = inc.incendio_id.map(rec.groupby("incendio_id").size()).fillna(0).astype(int)
    inc["estado"] = np.select([inc.focos_24h > 0, inc.focos_48h > 0],
                              ["Activo: focos en las últimas 24 h", "Activo: focos hace 24–48 h"],
                              "Sin focos en las últimas 48 h")

    # señal débil: solo detecciones diurnas y potencia baja -> posible quema agrícola o falsa
    # detección sobre suelo caliente (frecuente en la costa desértica). Se marca, no se borra.
    por_inc = focos.groupby("incendio_id")
    inc["pct_diurno"] = inc.incendio_id.map(por_inc.daynight.apply(lambda s: (s == "D").mean()))
    inc["frp_mediana"] = inc.incendio_id.map(por_inc.frp.median()).round(1)
    inc["cobertura"] = cobertura_en_punto(inc)
    inc["verificar"] = ((inc.pct_diurno == 1) & (inc.frp_mediana < 10)
                        & inc.cobertura.isin(["Suelo desnudo", "Urbano"]))

    # clima de los próximos 3 días (valores tal cual, sin combinarlos)
    inc = inc.join(clima(inc))
    inc = inc.sort_values(["activo_48h", "huella_ha"], ascending=False).reset_index(drop=True)
    inc.to_file(OUT / "incendios_contexto.geojson", driver="GeoJSON")

    act = inc[inc.activo_48h]
    print(f"\nincendios > {HUELLA_MIN_HA} ha: {len(inc)} | activos 48 h: {len(act)} | "
          f"activos 24 h: {(inc.focos_24h > 0).sum()} | con ANP a <= 5 km: {inc.anp_en_riesgo.sum()} | "
          f"personas a 5 km de incendios activos: {act.poblacion_5km.sum():,.0f}")
    print(act[["distrito", "departamento", "huella_ha", "focos_24h", "focos_48h", "poblacion_5km",
               "anp_cercana", "dist_anp_km", "hr_min", "viento_max", "lluvia_3d"]]
          .to_string(index=False))

    # todos los focos limpios de la semana por distrito y por departamento-día
    dist = (focos.groupby(["IDDIST", "NOMBDIST", "NOMBPROV", "NOMBDEP"])
            .agg(focos_7d=("frp", "size"), frp_total=("frp", "sum"),
                 ultimo=("fecha_lima", "max")).reset_index())
    dist["focos_24h"] = dist.IDDIST.map(rec.groupby("IDDIST").size()).fillna(0).astype(int)
    dist = dist.sort_values("focos_7d", ascending=False)
    dist.to_csv(OUT / "distritos_focos.csv", index=False, encoding="utf-8-sig")
    print(f"\ndistritos con focos en 7 días: {len(dist)}")
    print(dist.head(10).to_string(index=False))

    dia = pd.to_datetime(focos.fecha_lima).dt.strftime("%Y-%m-%d")
    matriz = focos.assign(dia=dia).groupby(["NOMBDEP", "dia"]).size().unstack(fill_value=0)
    matriz.to_csv(OUT / "departamentos_dia.csv", encoding="utf-8-sig")


if __name__ == "__main__":
    main()
