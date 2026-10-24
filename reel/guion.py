"""Paso 1: del texto largo al guion del reel (guion.json).

Uso:
  python guion.py --texto ../README.md --solo-prompt > prompt.txt
  # pegar prompt.txt en chat.qwen.ai (o chat.deepseek.com) y guardar la respuesta
  python guion.py --texto ../README.md --respuesta respuesta_qwen.txt --salida salidas/guion.json

El modelo devuelve JSON. Cada escena tiene "frase" (se dice, con números en
palabras), "cifra" y "etiqueta" (se ven en pantalla) y "visual" (fondo).
Toda cifra que no aparece tal cual en el texto queda marcada con ¡¡.
"""
import argparse
import json
import re
import sys
from pathlib import Path

VISUALES = {
    "mapa": "Mapa de focos de calor por distrito e incendios activos",
    "dias": "Barras de focos de calor por día, 14 al 20 de octubre",
    "historia": "Barras de focos del 1 al 20 de octubre, 2012-2026",
    "dnbr": "Imágenes Sentinel-2 de Curahuasi antes y después del fuego",
    "cobertura": "Barras de hectáreas quemadas en Curahuasi por cobertura",
    "exposicion": "Barras de personas a menos de 5 km de un incendio activo",
    "titulo": "Fondo liso para la escena de apertura o cierre",
}

PROMPT = """Eres guionista de reels de divulgación. Convierte el TEXTO en un reel vertical de 40 a 55 segundos.

Reglas:
1. Exactamente 6 escenas. Cada "frase" tiene entre 14 y 24 palabras y se lee en voz alta.
2. En "frase" escribe TODOS los números en palabras ("dos mil cuatrocientos noventa y seis", "setenta y cuatro por ciento").
3. "cifra" es UN número que aparece TAL CUAL en el TEXTO (por ejemplo "2 496", "+74 %", "1 946 ha"). No calcules ni redondees.
4. "etiqueta" explica la cifra en 2 a 6 palabras.
5. "visual" es una de estas claves: {visuales}.
6. No inventes nada que no diga el TEXTO: ni causas, ni lugares, ni relaciones entre datos. No digas "en tiempo real".
7. La escena 1 engancha con la pregunta central; la 6 cierra con una limitación honesta del método.
8. Además escribe tres posts para acompañar el reel: "x" (máx. 260 caracteres), "linkedin" (80 a 150 palabras) y "facebook" (40 a 90 palabras). Sin hashtags inventados de más de 3.

Responde SOLO con JSON válido, sin texto antes ni después, con esta forma:
{{"titulo": "...", "escenas": [{{"frase": "...", "cifra": "...", "etiqueta": "...", "visual": "..."}}], "posts": {{"x": "...", "linkedin": "...", "facebook": "..."}}}}

TEXTO:
\"\"\"
{texto}
\"\"\"
"""


def leer_texto(ruta):
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        texto = "\n".join(p.extract_text() or "" for p in PdfReader(ruta).pages)
    else:
        texto = ruta.read_text(encoding="utf-8")
    # Markdown: quitar imágenes, URLs y bloques de código, que no aportan al guion
    texto = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", texto)
    texto = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", texto)
    texto = re.sub(r"```.*?```", "", texto, flags=re.S)
    texto = re.sub(r"https?://\S+", "", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def solo_digitos(s):
    return re.sub(r"[^\d]", "", s)


def cifra_en_texto(cifra, texto):
    """La cifra cuenta como verificada si sus dígitos aparecen como número en el texto."""
    dig = solo_digitos(cifra)
    if not dig:
        return True
    numeros = {solo_digitos(m) for m in re.findall(r"\d[\d\s.,  ]*\d|\d", texto)}
    return dig in numeros


def extraer_json(respuesta):
    respuesta = re.sub(r"<think>.*?</think>", "", respuesta, flags=re.S)
    inicio, fin = respuesta.find("{"), respuesta.rfind("}")
    if inicio < 0 or fin < 0:
        sys.exit("No encontré JSON en la respuesta.")
    return json.loads(respuesta[inicio:fin + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texto", required=True)
    ap.add_argument("--solo-prompt", action="store_true")
    ap.add_argument("--respuesta")
    ap.add_argument("--salida", default="salidas/guion.json")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    texto = leer_texto(args.texto)
    if args.solo_prompt:
        visuales = ", ".join(f'"{k}" ({v})' for k, v in VISUALES.items())
        sys.stdout.reconfigure(encoding="utf-8")
        print(PROMPT.format(visuales=visuales, texto=texto))
        return
    if not args.respuesta:
        sys.exit("Falta --respuesta (o usa --solo-prompt).")

    guion = extraer_json(Path(args.respuesta).read_text(encoding="utf-8"))
    alertas = 0
    for i, esc in enumerate(guion["escenas"], 1):
        if not cifra_en_texto(esc["cifra"], texto):
            esc["cifra"] = "¡¡" + esc["cifra"]
            alertas += 1
            print(f"¡¡ Escena {i}: la cifra {esc['cifra'][2:]!r} no aparece en el texto.")
        if esc.get("visual") not in VISUALES:
            print(f"Escena {i}: visual {esc.get('visual')!r} no existe; uso 'titulo'.")
            esc["visual"] = "titulo"
        if re.search(r"\d", esc["frase"]):
            print(f"Escena {i}: la frase tiene dígitos; pásalos a palabras.")
    palabras = sum(len(e["frase"].split()) for e in guion["escenas"])
    print(f"{len(guion['escenas'])} escenas, {palabras} palabras (~{palabras / 2.6:.0f} s), {alertas} cifras por revisar.")

    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida).write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado {args.salida}. Revísalo contra el texto antes de narrar.")


if __name__ == "__main__":
    main()
