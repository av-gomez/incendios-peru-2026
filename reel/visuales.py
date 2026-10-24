"""Recursos visuales del reel: un fondo de 1080 x 920 px por clave de guion.py.

Se corre con el entorno del proyecto principal (pandas, geopandas, matplotlib):
  cd .. && uv run python reel/visuales.py
"""
import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
OUT = RAIZ / "outputs"
DEST = Path(__file__).resolve().parent / "visuales"
DEST.mkdir(exist_ok=True)

FONDO = "#14110F"
TINTA = "#F3EDE7"
TINTA_2 = "#A89F97"
BARRA = "#5A524C"
ACENTO = "#F26B1D"
ANCHO, ALTO = 1080, 920

plt.rcParams.update({
    "font.family": "Arial", "font.size": 22, "text.color": TINTA,
    "axes.edgecolor": FONDO, "axes.labelcolor": TINTA_2,
    "xtick.color": TINTA_2, "ytick.color": TINTA_2,
    "axes.facecolor": FONDO, "figure.facecolor": FONDO,
})


def figura():
    fig, ax = plt.subplots(figsize=(ANCHO / 100, ALTO / 100), dpi=100)
    fig.subplots_adjust(left=0.1, right=0.95, top=0.86, bottom=0.12)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(TINTA_2)
    ax.tick_params(length=0)
    return fig, ax


def titulo(fig, texto, sub):
    fig.text(0.1, 0.94, texto, fontsize=34, weight="bold", color=TINTA)
    fig.text(0.1, 0.895, sub, fontsize=20, color=TINTA_2)


def guardar(fig, nombre):
    fig.savefig(DEST / f"{nombre}.png", facecolor=FONDO)
    plt.close(fig)
    print("ok", nombre)


def miles(n):
    return f"{n:,.0f}".replace(",", " ")


def barras_dias():
    d = pd.read_csv(OUT / "departamentos_dia.csv", encoding="utf-8-sig").set_index("NOMBDEP").sum()
    # el 21-oct está incompleto (corte 14:19 h)
    d = d.iloc[:-1]
    etiquetas = [f"{c[-2:]}" for c in d.index]
    fig, ax = figura()
    colores = [ACENTO if v == d.max() else BARRA for v in d]
    ax.bar(etiquetas, d.values, color=colores, width=0.78, edgecolor=FONDO, linewidth=2)
    for x, v in enumerate(d.values):
        if v == d.max():
            ax.text(x, v + 40, miles(v), ha="center", fontsize=30, weight="bold", color=TINTA)
    ax.set_yticks([])
    ax.set_xlabel("octubre de 2026")
    titulo(fig, "Focos de calor por día", "Perú, VIIRS (NASA FIRMS), 14 al 20 de octubre")
    guardar(fig, "dias")


def barras_historia():
    h = pd.read_csv(OUT / "historia_octubre.csv")
    fig, ax = figura()
    colores = [ACENTO if a == 2026 else BARRA for a in h["anio"]]
    ax.bar(h["anio"].astype(str).str[-2:], h["focos"], color=colores, width=0.78, edgecolor=FONDO, linewidth=2)
    media = h.loc[h["anio"] < 2026, "focos"].mean()
    ax.axhline(media, color=TINTA_2, lw=2, ls=(0, (4, 4)))
    ax.text(-0.4, media + 250, "media 2012–2025", ha="left", fontsize=20, color=TINTA_2)
    for i, (a, v) in enumerate(zip(h["anio"], h["focos"])):
        if a in (2020, 2026):
            ax.text(i, v + 200, miles(v), ha="center", fontsize=24, weight="bold", color=TINTA)
    ax.set_yticks([])
    ax.set_xlabel("año (20xx)")
    titulo(fig, "Focos del 1 al 20 de octubre", "Perú, sensor S-NPP, 2012–2026")
    guardar(fig, "historia")


def barras_horizontales(nombre, serie, tit, sub, unidad):
    fig, ax = figura()
    fig.subplots_adjust(left=0.34)
    serie = serie.sort_values()
    colores = [ACENTO if v == serie.max() else BARRA for v in serie]
    ax.barh(serie.index, serie.values, color=colores, height=0.72, edgecolor=FONDO, linewidth=2)
    for y, v in enumerate(serie.values):
        ax.text(v + serie.max() * 0.02, y, f"{miles(v)} {unidad}", va="center", fontsize=24, color=TINTA)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(0, serie.max() * 1.35)
    ax.tick_params(axis="y", labelsize=24, labelcolor=TINTA)
    fig.text(0.1, 0.94, tit, fontsize=34, weight="bold", color=TINTA)
    fig.text(0.1, 0.895, sub, fontsize=20, color=TINTA_2)
    guardar(fig, nombre)


def cobertura():
    r = json.loads((OUT / "dnbr_resumen.json").read_text(encoding="utf-8"))
    s = pd.Series(r["cobertura_ha"])
    s = s[s > 5]
    barras_horizontales("cobertura", s, "Qué se quemó en Curahuasi",
                        "Hectáreas por cobertura, ESA WorldCover", "ha")


def exposicion():
    g = gpd.read_file(OUT / "incendios_contexto.geojson")
    g = g[g["activo_48h"] & ~g["verificar"]]
    s = g.groupby(g["distrito"].str.title())["poblacion_5km"].sum().nlargest(6)
    barras_horizontales("exposicion", s, "Quién vive cerca del fuego",
                        "Personas a menos de 5 km de un incendio activo", "")


def encajar(origen, nombre, recorte=None):
    """Pone una imagen existente sobre el fondo, centrada y sin deformarla."""
    img = Image.open(origen).convert("RGB")
    if recorte:
        img = img.crop(recorte)
    img.thumbnail((ANCHO - 40, ALTO - 40))
    lienzo = Image.new("RGB", (ANCHO, ALTO), FONDO)
    lienzo.paste(img, ((ANCHO - img.width) // 2, (ALTO - img.height) // 2))
    lienzo.save(DEST / f"{nombre}.png")
    print("ok", nombre)


def antes_despues():
    """Antes y después de Sentinel-2 en Curahuasi, sin la franja oeste sin datos."""
    from PIL import ImageDraw, ImageFont
    img = Image.open(OUT / "dnbr_curahuasi.png").convert("RGB")
    paneles = [("Antes · 5 oct", img.crop((300, 172, 662, 448))),
               ("Después · 17 oct", img.crop((967, 172, 1329, 448)))]
    lienzo = Image.new("RGB", (ANCHO, ALTO), FONDO)
    dibujo = ImageDraw.Draw(lienzo)
    negrita = ImageFont.truetype("arialbd.ttf", 34)
    normal = ImageFont.truetype("arial.ttf", 22)
    dibujo.text((60, 40), "Curahuasi desde Sentinel-2", font=negrita, fill=TINTA)
    dibujo.text((60, 88), "La mancha oscura es el área quemada", font=normal, fill=TINTA_2)
    for i, (rotulo, panel) in enumerate(paneles):
        panel = panel.resize((470, int(470 * panel.height / panel.width)))
        x = 60 + i * 490
        lienzo.paste(panel, (x, 230))
        dibujo.text((x, 190), rotulo, font=normal, fill=TINTA)
    lienzo.save(DEST / "dnbr.png")
    print("ok dnbr")


if __name__ == "__main__":
    barras_dias()
    barras_historia()
    cobertura()
    exposicion()
    encajar(OUT / "mapa_situacion.png", "mapa")
    antes_despues()
    Image.new("RGB", (ANCHO, ALTO), FONDO).save(DEST / "titulo.png")
