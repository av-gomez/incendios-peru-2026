# Revisión del guion contra la fuente

Fuente: `README.md` del repositorio (informe de situación, corte 21-oct-2026).
Modelo: Qwen3.8 en chat.qwen.ai, con `prompt.txt`. Respuesta original: `salidas/respuesta_qwen.txt`.
El control automático de `guion.py` no marcó ninguna cifra: las 6 estaban en el texto.
Las correcciones de abajo salieron de leer cada frase contra el README.

## Escenas

| # | Qwen escribió | Problema | Quedó |
|---|---|---|---|
| 1 | «¿Qué está pasando con los incendios forestales…?», sin cifra | Pregunta genérica y pantalla vacía | «¿Qué muestran los satélites…?», con «Oct. 2026» en pantalla |
| 4 | «…setenta y cuatro por ciento más que el **promedio histórico**» | La comparación es con la media **2012–2025**, no con toda la historia | «…más que la media desde dos mil doce» |
| 5 | «**Cerca de** cuarenta mil seiscientas setenta y una personas…» | «Cerca de» con una cifra exacta; la etiqueta decía «personas **expuestas a incendios**» | Sin «cerca de». Etiqueta: «Personas a menos de 5 km» (exposición potencial, WorldPop 2020) |
| 6 | «Siete incendios en la costa podrían ser quemas agrícolas o falsas detecciones, las cifras satelitales y oficiales miden cosas distintas» | Junta dos limitaciones en una frase. Además, el README no los cuenta como incendios: son detecciones **por verificar** que no se suman | «Ojo: un foco de calor no es un incendio. Siete detecciones en la costa desértica podrían ser quemas agrícolas o suelo caliente» |
| nueva | — | Faltaba el único dato de área quemada medido con raster (Sentinel-2, dNBR), que es el centro del método | Escena de Curahuasi: al menos 1 946 ha, el 90 % pastizal |

## Posts

- **Facebook:** «una ola de incendios **sin precedentes**» es **falso**. Según el README es el 2.º valor de la serie 2012–2026, y solo 2020 lo supera (12 845 focos). También quité «Alerta» y cambié «40 671 personas **están expuestas**» por «**viven a menos de 5 km** de un incendio activo».
- **LinkedIn:** «muestra **cifras alarmantes**» es una opinión, no un dato. Agregué que 2020 tuvo más focos.
- **X:** «media histórica» → «media 2012–2025». «Personas expuestas» → «a menos de 5 km de un incendio activo».

## Lección

Las cifras eran correctas y aun así había frases engañosas: «sin precedentes», «expuestas» o «promedio histórico». El código comprueba que el número existe en la fuente, pero no comprueba lo que la frase dice de ese número.
