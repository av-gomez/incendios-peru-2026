"""Área quemada en Curahuasi (Abancay, Apurímac) con Sentinel-2 L2A: NBR y dNBR.

Decisiones (se reportan en el README):
- Antes  : 2026-10-05, tile T18LYK, 1.0 % nubes en la escena (misma órbita R039 que la posterior).
- Después: 2026-10-17, tile T18LYK, 0.3 % nubes en la escena.
- NBR = (B08 - B12) / (B08 + B12), a 20 m. dNBR = NBR_antes - NBR_después.
- Máscara SCL: fuera nubes (8, 9, 10), sombra (3), nieve (11), agua (6), sin datos (0, 1).
- Quemado = dNBR >= 0.27 (umbral USGS de severidad moderada-baja), como en el ejemplo del profe.
- Cobertura: ESA WorldCover 2021 (10 m) remuestreada a la grilla de 20 m.
Salida: outputs/dnbr_curahuasi.png, outputs/dnbr_overlay.png, outputs/dnbr_resumen.json
"""
import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import planetary_computer
import pystac_client
from matplotlib.colors import BoundaryNorm, ListedColormap
from odc.stac import load
from rasterio.features import rasterize

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "outputs"
DISTRITO = "CURAHUASI"
FECHA_ANTES, FECHA_DESPUES, TILE = "2026-10-05", "2026-10-17", "18LYK"
ORBITA = 39
OFFSET = 1000
UMBRAL = 0.27
CLASES = [(0.10, 0.27, "Baja"), (0.27, 0.44, "Moderada-baja"),
          (0.44, 0.66, "Moderada-alta"), (0.66, 9.99, "Alta")]
WORLDCOVER = {10: "Bosque", 20: "Arbustal", 30: "Pastizal", 40: "Cultivo", 50: "Urbano",
              60: "Suelo desnudo", 70: "Nieve", 80: "Agua", 90: "Humedal", 95: "Manglar",
              100: "Musgo/liquen"}
PIX_HA = 20 * 20 / 1e4


def main() -> None:
    focos = gpd.read_file(OUT / "focos_limpios.geojson")
    zona = focos[focos.NOMBDIST == DISTRITO]
    xmin, ymin, xmax, ymax = zona.total_bounds
    bbox = [xmin - 0.02, ymin - 0.02, xmax + 0.02, ymax + 0.02]
    print("bbox:", [round(v, 3) for v in bbox], "| focos en el distrito:", len(zona))

    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    escenas = {}
    for nombre, fecha in [("antes", FECHA_ANTES), ("despues", FECHA_DESPUES)]:
        # todos los tiles de la misma órbita ese día (la zona cae en el borde de T18LYK)
        items = [i for i in cat.search(collections=["sentinel-2-l2a"], bbox=bbox,
                                       datetime=fecha).items()
                 if i.properties["sat:relative_orbit"] == ORBITA]
        it = next(i for i in items if i.properties["s2:mgrs_tile"] == TILE)
        for i in items:
            print(f"{nombre}: {i.id} | nubes escena {i.properties['eo:cloud_cover']:.1f} %")
        ds = load(items, bands=["B04", "B03", "B02", "B08", "B12", "SCL"], bbox=bbox,
                  crs="EPSG:32718", resolution=20, groupby="solar_day", nodata=0,
                  chunks={}).isel(time=0).compute()
        escenas[nombre] = (it, ds)

    def nbr(ds):
        # L2A con baseline >= 04.00 suma +1000 a la reflectancia (BOA_ADD_OFFSET): se resta
        b8 = (ds.B08.astype("float32") - OFFSET).clip(min=0)
        b12 = (ds.B12.astype("float32") - OFFSET).clip(min=0)
        return (b8 - b12) / (b8 + b12 + 1e-6)

    def mala(ds):
        scl = ds.SCL.values
        return np.isin(scl, [0, 1, 3, 6, 8, 9, 10, 11])

    a, d = escenas["antes"][1], escenas["despues"][1]
    mascara = mala(a) | mala(d)
    dnbr = (nbr(a) - nbr(d)).values
    dnbr[mascara] = np.nan
    pct_mask = mascara.mean() * 100
    print(f"píxeles enmascarados en la zona: {pct_mask:.1f} %")
    for nombre, ds in [("antes", a), ("despues", d)]:
        v, c = np.unique(ds.SCL.values, return_counts=True)
        print(f"  SCL {nombre}:", {str(k): round(n / c.sum() * 100, 1) for k, n in zip(v, c)})

    # distritos en la grilla
    dist = gpd.read_file(DATA / "distritos.geojson").to_crs(32718)
    transform = a.odc.geobox.transform
    shape = dnbr.shape
    dist_zona = dist.cx[a.x.min().item():a.x.max().item(), a.y.min().item():a.y.max().item()]
    codigos = rasterize([(g, i + 1) for i, g in enumerate(dist_zona.geometry)], out_shape=shape,
                        transform=transform, fill=0)
    nombres = {i + 1: n for i, n in enumerate(dist_zona.NOMBDIST)}

    # WorldCover
    wc_items = list(cat.search(collections=["esa-worldcover"], bbox=bbox).items())
    wc = load(wc_items, bands=["map"], resampling="mode", like=a, chunks={}) \
        .isel(time=-1)["map"].compute().values

    quemado = dnbr >= UMBRAL
    resumen = {
        "distrito": DISTRITO, "fecha_antes": FECHA_ANTES, "fecha_despues": FECHA_DESPUES,
        "escena_antes": escenas["antes"][0].id, "escena_despues": escenas["despues"][0].id,
        "nubes_antes_%": escenas["antes"][0].properties["eo:cloud_cover"],
        "nubes_despues_%": escenas["despues"][0].properties["eo:cloud_cover"],
        "pixeles_enmascarados_%": round(float(pct_mask), 2), "umbral_dnbr": UMBRAL,
        "bbox": bbox,
        "ha_quemadas_total_zona": round(float(quemado.sum() * PIX_HA)),
        "ha_quemadas_en_distrito": round(float((quemado & (codigos == [k for k, v in nombres.items()
                                                                     if v == DISTRITO][0])).sum()
                                               * PIX_HA)),
        "severidad_ha": {n: round(float(((dnbr >= lo) & (dnbr < hi)).sum() * PIX_HA))
                         for lo, hi, n in CLASES},
        "por_distrito_ha": {nombres[k]: round(float((quemado & (codigos == k)).sum() * PIX_HA))
                            for k in nombres if (quemado & (codigos == k)).sum() > 0},
        "cobertura_ha": {WORLDCOVER.get(int(k), str(k)): round(float((quemado & (wc == k)).sum()
                                                                      * PIX_HA))
                         for k in np.unique(wc[quemado])},
    }
    resumen["por_distrito_ha"] = dict(sorted(resumen["por_distrito_ha"].items(),
                                             key=lambda kv: -kv[1]))
    resumen["cobertura_ha"] = dict(sorted(resumen["cobertura_ha"].items(), key=lambda kv: -kv[1]))
    print(json.dumps(resumen, indent=2, ensure_ascii=False))

    # figura: RGB después + dNBR + focos
    def rgb(ds):
        x = np.dstack([ds.B04.values, ds.B03.values, ds.B02.values]).astype("float32")
        return np.clip((x - OFFSET) / 2500, 0, 1)

    ext = [a.x.min().item(), a.x.max().item(), a.y.min().item(), a.y.max().item()]
    f_utm = zona.to_crs(32718)
    cmap = ListedColormap(["#1a9850", "#fee08b", "#fdae61", "#f46d43", "#a50026"])
    norm = BoundaryNorm([-1, 0.1, 0.27, 0.44, 0.66, 2], cmap.N)
    fig, ax = plt.subplots(1, 3, figsize=(16, 5.6))
    ax[0].imshow(rgb(a), extent=ext)
    ax[0].set_title(f"Antes · {FECHA_ANTES}")
    ax[1].imshow(rgb(d), extent=ext)
    ax[1].set_title(f"Después · {FECHA_DESPUES}")
    im = ax[2].imshow(dnbr, cmap=cmap, norm=norm, extent=ext)
    f_utm.plot(ax=ax[2], color="cyan", markersize=3, label="focos VIIRS 14-21 oct")
    dist_zona.boundary.plot(ax=ax[2], color="black", linewidth=0.6)
    ax[2].legend(loc="lower left", fontsize=8)
    ax[2].set_xlabel(""); ax[2].set_ylabel("")
    ax[2].set_title(f"dNBR · quemado (≥{UMBRAL}): {resumen['ha_quemadas_en_distrito']:,} ha "
                    f"en {DISTRITO.title()}")
    cb = fig.colorbar(im, ax=ax[2], shrink=0.8, ticks=[-0.45, 0.18, 0.35, 0.55, 0.8])
    cb.ax.set_yticklabels(["sin cambio", "baja", "mod-baja", "mod-alta", "alta"])
    for x in ax:
        x.set_xticks([]); x.set_yticks([])
        x.set_xlim(ext[0], ext[1]); x.set_ylim(ext[2], ext[3])
    fig.suptitle("Curahuasi (Abancay, Apurímac) · Sentinel-2 L2A · órbita R039 (franja oeste sin cobertura)", fontsize=12)
    plt.tight_layout()
    fig.savefig(OUT / "dnbr_curahuasi.png", dpi=130)

    # overlay transparente para el mapa web (en WGS84, bounds aproximados del bbox)
    rgba = cmap(norm(np.nan_to_num(dnbr, nan=-1)))
    rgba[..., 3] = np.where(np.nan_to_num(dnbr, nan=-1) >= 0.1, 0.85, 0)
    plt.imsave(OUT / "dnbr_overlay.png", rgba)
    esq = gpd.GeoSeries(gpd.points_from_xy([ext[0], ext[1]], [ext[2], ext[3]]), crs=32718) \
        .to_crs(4326)
    resumen["overlay_bounds"] = [[esq.y[0], esq.x[0]], [esq.y[1], esq.x[1]]]
    (OUT / "dnbr_resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False),
                                           encoding="utf-8")


if __name__ == "__main__":
    main()
