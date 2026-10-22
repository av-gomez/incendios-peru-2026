"""¿Es 2026 un año récord? Focos S-NPP del 1 al 21 de octubre, 2012-2026, por departamento.

2012-2025: archivo anual FIRMS (viirs-snpp, Perú), solo `type == 0` (vegetación).
2026     : INPE Queimadas, mensual de octubre, satélite NPP-375 (el mismo sensor S-NPP).
           Se calibra contra FIRMS 7d S-NPP en los días que se traslapan.
Salida   : outputs/historia_octubre.csv, outputs/historia_departamentos.csv
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "outputs"
DIA_FIN = 21


def a_departamento(df: pd.DataFrame, lat: str, lon: str, dist: gpd.GeoDataFrame) -> pd.DataFrame:
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon], df[lat]), crs="EPSG:4326")
    return gpd.sjoin(g, dist, predicate="within", how="inner")


def main() -> None:
    dist = gpd.read_file(DATA / "distritos.geojson")[["NOMBDEP", "geometry"]]

    # 2012-2025
    filas = []
    for p in sorted((DATA / "hist").glob("snpp_*.csv")):
        h = pd.read_csv(p, usecols=["latitude", "longitude", "acq_date", "type"])
        h["acq_date"] = pd.to_datetime(h.acq_date)
        h = h[(h["type"] == 0) & (h.acq_date.dt.month == 10) & (h.acq_date.dt.day <= DIA_FIN)]
        h = a_departamento(h, "latitude", "longitude", dist)
        h["anio"] = h.acq_date.dt.year
        filas.append(h[["anio", "NOMBDEP"]])

    # 2026 desde INPE
    inpe = pd.read_csv(DATA / "inpe_202610.csv")
    inpe = inpe[(inpe.pais == "Peru") & (inpe.satelite == "NPP-375")].copy()
    inpe["fecha"] = pd.to_datetime(inpe.data_hora_gmt) - pd.Timedelta(hours=5)
    corte_inpe = inpe.fecha.max()
    inpe = inpe[inpe.fecha.dt.day <= DIA_FIN]
    inpe = a_departamento(inpe, "lat", "lon", dist)
    inpe["anio"] = 2026
    filas.append(inpe[["anio", "NOMBDEP"]])

    # calibración INPE vs FIRMS S-NPP en los días comunes
    firms = pd.read_csv(DATA / "SUOMI_VIIRS_C2_7d.csv")
    firms["fecha"] = pd.to_datetime(firms.acq_date + " " + firms.acq_time.astype(str).str.zfill(4),
                                    format="%Y-%m-%d %H%M") - pd.Timedelta(hours=5)
    firms = a_departamento(firms, "latitude", "longitude", dist)
    dias = sorted(set(firms.fecha.dt.date) & set(inpe.fecha.dt.date))[1:-1]  # días completos
    c_f = firms[firms.fecha.dt.date.isin(dias)].groupby(firms.fecha.dt.date).size()
    c_i = inpe[inpe.fecha.dt.date.isin(dias)].groupby(inpe.fecha.dt.date).size()
    cal = pd.DataFrame({"FIRMS_SNPP": c_f, "INPE_NPP375": c_i})
    cal["dif_%"] = ((cal.INPE_NPP375 / cal.FIRMS_SNPP - 1) * 100).round(1)
    print(f"INPE último dato (Lima): {corte_inpe}")
    print("Calibración INPE vs FIRMS (S-NPP, Perú):")
    print(cal.to_string())

    todo = pd.concat(filas)
    serie = todo.groupby("anio").size().rename("focos").reset_index()
    base = serie[serie.anio < 2026].focos
    serie["vs_promedio_%"] = ((serie.focos / base.mean() - 1) * 100).round(0)
    serie.to_csv(OUT / "historia_octubre.csv", index=False)
    print(f"\nFocos S-NPP 1-{DIA_FIN} de octubre:")
    print(serie.to_string(index=False))

    tab = todo.groupby(["NOMBDEP", "anio"]).size().unstack(fill_value=0)
    hist = tab.drop(columns=2026)
    dep = pd.DataFrame({
        "focos_2026": tab[2026],
        "promedio_2012_2025": hist.mean(axis=1).round(0),
        "maximo_previo": hist.max(axis=1),
        "anio_maximo_previo": hist.idxmax(axis=1),
    })
    dep["vs_promedio_%"] = ((dep.focos_2026 / dep.promedio_2012_2025.clip(lower=1) - 1) * 100).round(0)
    dep["record"] = dep.focos_2026 > dep.maximo_previo
    dep = dep.sort_values("focos_2026", ascending=False)
    dep.to_csv(OUT / "historia_departamentos.csv", encoding="utf-8-sig")
    print("\nPor departamento:")
    print(dep.to_string())


if __name__ == "__main__":
    main()
