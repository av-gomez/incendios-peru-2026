# Reel: del informe de incendios a 50 segundos con mi voz

Tarea de la sesión 15 (Del texto a tu voz) · Ciencia de Datos con Python · Amanda Gomez.

El README del repositorio (informe de situación de los incendios de octubre de 2026) se convierte en un reel vertical narrado con mi voz clonada. Todo se hace con modelos abiertos.

| Paso | Herramienta | Archivo |
|---|---|---|
| 1. Guion | Qwen3.8 (chat.qwen.ai) con `prompt.txt` | `salidas/respuesta_qwen.txt` |
| 2. Revisión | Yo, contra el README | `salidas/guion.json`, `revision.md` |
| 3. Voz | Qwen3-TTS-12Hz-0.6B-Base, clonada con 20 s de mi voz | `salidas/reel.wav` |
| 4. Subtítulos y control | faster-whisper `small` | `salidas/reel.srt` |
| 5. Video | Pillow + ffmpeg (imageio-ffmpeg) | `salidas/reel.mp4`, `portada.png`, `posts.md` |

Los fondos de cada escena (`visuales/`) salen de los datos del informe con `visuales.py`.

## Reproducir

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python qwen-tts faster-whisper pillow imageio-ffmpeg soundfile jiwer num2words pypdf
# fondos (usa el entorno del proyecto principal)
cd ..; uv run python reel/visuales.py; cd reel
# 1. prompt -> pegar en chat.qwen.ai -> guardar la respuesta
.venv\Scripts\python guion.py --texto ..\README.md --solo-prompt > prompt.txt
.venv\Scripts\python guion.py --texto ..\README.md --respuesta salidas\respuesta_qwen.txt
# 2. revisar salidas\guion.json a mano; 3. voz, subtítulos y video
.venv\Scripts\python hacer_reel.py --voz mi_voz.mp4 --autor "Amanda Gomez" --fuente "NASA FIRMS, Sentinel-2, WorldPop"
```

## Controles

- **Cifras:** `guion.py` marca con ¡¡ toda cifra que no aparece tal cual en el texto.
- **Pronunciación:** Whisper vuelve a escuchar cada escena. Si el error de palabras (WER) supera el 25 %, la escena se genera de nuevo, hasta 3 veces. Los números se comparan escritos en palabras.
- **Volumen:** −14 LUFS, con `loudnorm` de ffmpeg en dos pasadas.
- **Formato:** 1080×1920, 30 fps, H.264 + AAC. Nada importante en los bordes, donde van los botones de cada app.
- **Aviso de IA:** «Voz generada con IA» se ve durante todo el video y va al final de cada post.

## Lo que corregí

Detalle en [`revision.md`](revision.md). En resumen, las cifras de Qwen eran correctas, pero el post de Facebook decía «sin precedentes», cuando 2020 tuvo más focos. Además, el guion hablaba de «promedio histórico» en lugar de «media 2012–2025» y de «personas expuestas» en lugar de «a menos de 5 km», y omitía el área quemada medida con Sentinel-2.

## Rendimiento

En una laptop con Intel i7-1185G7 y sin GPU, Qwen3-TTS 0.6B tarda unos 18 s de cálculo por cada segundo de audio. Un reel de 50 s tarda unos 20 minutos.

Mi voz (`mi_voz.*`) y los audios intermedios no se suben al repositorio.
