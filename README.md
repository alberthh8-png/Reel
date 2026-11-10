# Reel: GTA 6, 5 teorías que los fans juran que son reales

Vídeo vertical de **~25 s** (1080×1920, 30 fps) para **Instagram Reels** y **YouTube Shorts**. Es de acción: disparos, fogonazos, agujeros de bala en la pantalla, explosiones con onda expansiva y sacudida de cámara, lluvia de billetes, subtítulos tipo karaoke y una encuesta "¿Tú qué crees?" en cada teoría.

| Archivo | Qué es |
|---|---|
| `salida/reel.mp4` | Vídeo final, listo para subir |
| `salida/portada.jpg` | Portada o miniatura |
| `salida/subtitulos.srt` | Subtítulos, por si quieres subirlos aparte |
| `salida/locucion.md` | Guion de la locución con tiempos |
| `voz/` | Locución de narrador: una frase por escena (`voz/original/` son los archivos tal cual salen de Higgsfield) |

## Estructura

| Tiempo | Escena | Acción |
|---|---|---|
| 0–3,4 s | **Gancho:** "5 TEORÍAS que los fans juran que son reales" | Explosión con "BOOM!" en el primer fotograma, helicóptero y disparos |
| 3,4–6,9 s | **#1 Jason es poli** (infiltrado) | Tiroteo junto a un coche patrulla con luces de sirena → "¿Tú qué crees?" |
| 6,9–10,3 s | **#2 Uno mata al otro** (en el final) | Duelo en una azotea al atardecer → "¿Te lo crees?" |
| 10,3–14,4 s | **#3 Hay un tercer protagonista** (un poli veterano) | Aparece un "?" sobre una tercera silueta → "¿Real o fake?" |
| 14,4–18,6 s | **#4 Online de pago** (un juego aparte) | Lluvia de billetes y un coche que explota → "¿Lo pagarías?" |
| 18,6–22,7 s | **#5 El yate de Michael** (aparece en Leonida) | Puerto con un yate, disparos y explosión → "¿Tú qué opinas?" |
| 22,7–24,9 s | **Cierre:** "¿Cuál es real? Comenta el número" | Explosión final |

Por qué engancha:
- La acción arranca en el primer fotograma y hay un golpe visual cada 1–2 s.
- La encuesta SÍ/NO invita a comentar.
- El cierre pide comentar un número, que es una respuesta fácil y empuja el vídeo en el algoritmo.
- Las 5 teorías son de la comunidad, no son datos oficiales. Salen de foros y medios como [Yahoo Tech](https://tech.yahoo.com/gaming/articles/gta-6-trailer-2-wild-112932290.html), [Esquire SG](https://esquiresg.com/we-read-all-the-gta-6-fan-theories-so-you-dont-have-to/) y [Game Rant](https://gamerant.com/gta-6-online-just-got-a-disappointing-update/).

## Voz

La narración es la voz **"Dan – Upbeat, Dynamic and Friendly"** de tu cuenta de **ElevenLabs**: masculina, joven, español nativo y pensada para redes sociales. Se genera con el modelo `eleven_multilingual_v2`, con estos ajustes: estabilidad 0.38, similitud 0.8, estilo 0.55 y realce del hablante activado.

Hay una frase por escena. Cada frase:
- se recorta de silencios,
- se acelera un 8 %,
- y se comprime y normaliza a -16 LUFS.

El motor la coloca al inicio de cada escena y baja la música y los efectos mientras habla. Los subtítulos siguen la duración real de cada frase.

- `voz/original/`: los mp3 tal cual salen de ElevenLabs.
- `voz/escena_N.wav`: las frases ya procesadas que usa el vídeo.

La API key de ElevenLabs **no está en el repositorio**. Está guardada como secreto del entorno cloud "Reel" y el proxy la inyecta en cada llamada. `.env.local`, que crea el CLI de ElevenLabs, está en `.gitignore`.

## Imágenes

Todas las ilustraciones son **originales** y se dibujan por código: ciudad neón, coche patrulla, helicóptero, deportivos, yate, mansión y personajes en silueta genéricos. **No tienen copyright de nadie** y no reproducen capturas, logos ni personajes del juego.

Si quieres cambiar el fondo de una escena por una imagen tuya (de tu propiedad o con licencia libre), ponla en `imagenes/` con el `id` de la escena y se usará en lugar de la ilustración:

```
imagenes/gancho.jpg   imagenes/teoria1.jpg   imagenes/teoria4.png  ...
```

## Texto para publicar

Textos, hashtags, horarios y estrategia para Instagram, YouTube Shorts y TikTok en **[PUBLICAR.md](PUBLICAR.md)**.

## Cómo regenerarlo

Requisitos: Python 3, `numpy`, `Pillow` y `ffmpeg`.

```bash
pip install numpy pillow
python3 reel.py --preview 2   # fotogramas de muestra en salida/preview/
python3 reel.py               # vídeo completo en salida/reel.mp4 (~1-2 min)
```

Todo se edita en `guion.json`:
- textos, preguntas y duración de cada escena
- efectos de cada escena (`fx`): `disparo` (con posición, ángulo y agujero de bala), `explosion` (con posición, escala y texto tipo "BOOM!"), `dinero`, `sirena` y `revelar`
- qué ilustración usa cada escena (`ilustracion`)

La música y los efectos de sonido son originales y se generan por código, así que no hay problemas de derechos. La fuente es Inter (licencia OFL, en `fonts/`).
