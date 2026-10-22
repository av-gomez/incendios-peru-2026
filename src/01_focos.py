"""Focos VIIRS de los últimos 7 días -> limpieza -> incendios (clusters).

Entrada : data/*_VIIRS_C2_7d.csv (NASA FIRMS, S-NPP / NOAA-20 / NOAA-21)
          data/hist/snpp_*.csv   (archivo FIRMS 2012-2025, columna `type`)
          data/distritos.geojson (INEI, juaneladio/peru-geojson)
Salida  : outputs/focos_limpios.geojson, outputs/incendios.geojson
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "outputs"
OUT.mkdir(exist_ok=True)

SATS = {"SUOMI_VIIRS_C2": "S-NPP", "J1_VIIRS_C2": "NOAA-20", "J2_VIIRS_C2": "NOAA-21"}
EPS_KM = 1.0          # focos a <= 1 km pertenecen al mismo incendio
GAP_H = 48            # ... y a <= 48 h (se parte el cluster si hay un salto mayor)
PIXEL_HA = 0.375 ** 2 * 100   # un píxel VIIRS I-band ~ 375 m x 375 m = 14 ha


def cargar_focos() -> pd.DataFrame:
    partes = []
    for archivo, sat in SATS.items():
        df = pd.read_csv(DATA / f"{archivo}_7d.csv")
        df["sat"] = sat
        partes.append(df)
    df = pd.concat(partes, ignore_index=True)
    df["fecha_utc"] = pd.to_datetime(
        df.acq_date + " " + df.acq_time.astype(str).str.zfill(4), format="%Y-%m-%d %H%M")
    df["fecha_lima"] = df.fecha_utc - pd.Timedelta(hours=5)
    return df


def celdas_fijas() -> set[tuple[int, int]]:
    """Celdas de ~1 km donde FIRMS marcó fuentes fijas (type 2) o volcanes (type 1)."""
    hist = pd.concat(pd.read_csv(p, usecols=["latitude", "longitude", "type"])
                     for p in sorted((DATA / "hist").glob("snpp_*.csv")))
    fijas = hist[hist["type"].isin([1, 2])]
    celdas = set()
    for la, lo in zip((fijas.latitude * 100).round().astype(int),
                      (fijas.longitude * 100).round().astype(int)):
        for dy in (-1, 0, 1):          # incluye celdas vecinas
            for dx in (-1, 0, 1):
                celdas.add((la + dy, lo + dx))
    return celdas


def main() -> None:
    focos = cargar_focos()
    distritos = gpd.read_file(DATA / "distritos.geojson")[
        ["IDDIST", "NOMBDIST", "NOMBPROV", "NOMBDEP", "geometry"]]
    gdf = gpd.GeoDataFrame(focos, geometry=gpd.points_from_xy(focos.longitude, focos.latitude),
                           crs="EPSG:4326")
    gdf = gpd.sjoin(gdf, distritos, predicate="within", how="inner").drop(columns="index_right")
    n_peru = len(gdf)

    # limpieza
    gdf = gdf[gdf.confidence != "low"]
    n_conf = len(gdf)
    fijas = celdas_fijas()
    clave = list(zip((gdf.latitude * 100).round().astype(int),
                     (gdf.longitude * 100).round().astype(int)))
    gdf = gdf[[c not in fijas for c in clave]].copy()
    print(f"focos en Perú: {n_peru:,} | sin confianza baja: {n_conf:,} | "
          f"sin fuentes fijas/volcanes: {len(gdf):,}")
    print("corte de datos (hora Lima):", gdf.fecha_lima.max())
    print(gdf.groupby(gdf.fecha_lima.dt.date).size().to_string())

    # clusters espaciales (haversine) y luego corte temporal
    coords = np.radians(gdf[["latitude", "longitude"]].to_numpy())
    gdf["c_esp"] = DBSCAN(eps=EPS_KM / 6371.0, min_samples=1, metric="haversine",
                          algorithm="ball_tree").fit_predict(coords)
    gdf = gdf.sort_values(["c_esp", "fecha_utc"])
    salto = gdf.groupby("c_esp").fecha_utc.diff() > pd.Timedelta(hours=GAP_H)
    gdf["incendio_id"] = (gdf.c_esp.astype(str) + "_" +
                          salto.groupby(gdf.c_esp).cumsum().astype(str))
    gdf.to_file(OUT / "focos_limpios.geojson", driver="GeoJSON")

    # un registro por incendio
    corte = gdf.fecha_utc.max()
    utm = gdf.to_crs(32718)
    huella = (utm.assign(geometry=utm.buffer(187.5, cap_style="square"))
              .dissolve("incendio_id").geometry.area / 1e4)
    inc = gdf.groupby("incendio_id").agg(
        n_focos=("frp", "size"), frp_total=("frp", "sum"), frp_max=("frp", "max"),
        inicio=("fecha_lima", "min"), ultimo=("fecha_lima", "max"),
        lat=("latitude", "mean"), lon=("longitude", "mean"),
        distrito=("NOMBDIST", lambda s: s.mode().iat[0]),
        provincia=("NOMBPROV", lambda s: s.mode().iat[0]),
        departamento=("NOMBDEP", lambda s: s.mode().iat[0]),
        ubigeo=("IDDIST", lambda s: s.mode().iat[0]),
    )
    inc["huella_ha"] = huella.reindex(inc.index).round(0)
    inc["focos_48h"] = gdf[gdf.fecha_utc >= corte - pd.Timedelta(hours=48)] \
        .groupby("incendio_id").size().reindex(inc.index, fill_value=0)
    inc["activo_48h"] = inc.focos_48h > 0
    inc = gpd.GeoDataFrame(inc.reset_index(), geometry=gpd.points_from_xy(inc.lon, inc.lat),
                           crs="EPSG:4326")
    inc["inicio"] = inc.inicio.dt.strftime("%Y-%m-%d %H:%M")
    inc["ultimo"] = inc.ultimo.dt.strftime("%Y-%m-%d %H:%M")
    inc.to_file(OUT / "incendios.geojson", driver="GeoJSON")

    grandes = inc[inc.huella_ha > 100]
    print(f"\nincendios: {len(inc):,} | huella > 100 ha: {len(grandes)} | "
          f"grandes y activos 48 h: {(grandes.activo_48h).sum()}")
    print(grandes.nlargest(15, "frp_total")[
        ["distrito", "departamento", "n_focos", "huella_ha", "frp_total", "focos_48h"]]
        .to_string(index=False))


if __name__ == "__main__":
    main()
