# Reel: GTA 6, 5 secretos y teorías que casi nadie conoce

Vídeo vertical 1080×1920 a 30 fps y de 41 s para **Instagram Reels** y **YouTube Shorts**. Se genera entero con código: animaciones, subtítulos tipo karaoke, música synthwave original y efectos de sonido.

| Archivo | Qué es |
|---|---|
| `salida/reel.mp4` | El vídeo final, listo para subir |
| `salida/portada.jpg` | Portada o miniatura |
| `salida/subtitulos.srt` | Subtítulos, por si quieres subirlos aparte |
| `salida/locucion.md` | Guion con tiempos, por si quieres grabar tu voz encima |

## Estructura y por qué engancha

| Tiempo | Bloque | Técnica |
|---|---|---|
| 0–3,6 s | **Gancho:** «GTA VI llega sin ONLINE» | Afirmación que choca y deja una pregunta abierta. El texto ya se lee en el primer fotograma, porque mucha gente ve los vídeos sin sonido. |
| 3,6–6,8 s | **Promesa:** «5 secretos y teorías… la última te vuela la cabeza» | Bucle abierto para que se quede hasta el final |
| 6,8–33,6 s | 5 datos, unos 5 s cada uno | Contador de progreso (●●●●●), un número grande por dato y un corte con glitch y *whoosh* en cada cambio para romper el patrón |
| 33,6–37 s | Bonus | Recompensa a quien llega al final |
| 37–41 s | Llamada a la acción: «¿Jason es poli? Comenta SÍ o NO» | Una pregunta binaria genera muchos comentarios y el algoritmo lo premia |

Cada dato lleva un **sello** (CONFIRMADO, RUMOR, TEORÍA o ANALISTAS). Así queda claro qué es oficial y qué no, y las teorías provocan debate.

### Los datos (verificados a 10/11/2026)
1. **Sin Online de salida (CONFIRMADO).** Take-Two lo presenta como juego para un jugador en el lanzamiento y seguirá dando soporte al GTA Online de GTA V «después del lanzamiento de GTA 6 y más allá».
2. **¿Online en 2027? (RUMOR).** En código filtrado aparecen cadenas de texto de multijugador, y varias fuentes apuntan a 2027 para el nuevo Online.
3. **El yate de Michael (TEORÍA).** El yate que aparece junto a la casa de Jason podría ser el de Michael De Santa.
4. **3.200 millones $ (ANALISTAS).** Es la previsión de DFC Intelligence para el primer año, el doble que GTA V.
5. **¿Jason es policía infiltrado? (TEORÍA).** En el tráiler 2 un guardia le dice que ya le ha visto antes y él responde «puede ser».
- **Bonus (TEORÍA):** ¿un tercer personaje jugable oculto?

Fuentes: [TechRadar](https://www.techradar.com/gaming/gta-6-online-might-not-be-coming-anytime-soon-as-take-two-confirms-gta-online-support-will-continue-after-gta-6-launches-and-beyond) · [Game Rant](https://gamerant.com/gta-6-online-just-got-a-disappointing-update/) · [Notebookcheck](https://www.notebookcheck.net/Leaked-GTA-6-release-date-build-hints-online-multiplayer-could-launch-soon.1445605.0.html) · [GamesRadar (DFC)](https://gamesradar.com/games/grand-theft-auto/gta-6-will-double-gta-5-and-make-usd3-2-billion-in-its-first-year-analysts-say-the-pent-up-demand-is-greater-than-anything-weve-seen-before) · [Yahoo Tech, teorías del tráiler 2](https://tech.yahoo.com/gaming/articles/gta-6-trailer-2-wild-112932290.html) · [Esquire SG, teorías](https://esquiresg.com/we-read-all-the-gta-6-fan-theories-so-you-dont-have-to/) · [Gulf News, fecha](https://gulfnews.com/technology/gaming/gta-6-drops-nov-19-as-preloads-open-nov-10-five-things-to-know-about-grand-theft-auto-1.500740670)

> ⚠️ El gancho dice «llega en 9 días», que vale para publicarlo el **10 de noviembre**. Si lo publicas otro día, cambia la frase en `guion.json` y vuelve a generarlo.

## Texto para publicar

**Descripción:**
> GTA 6 llega SIN Online 😳 y no es lo único… ¿Jason es poli? Comenta SÍ o NO 👇
> #GTA6 #GTAVI #GTAOnline #Rockstar #videojuegos #gaming #gamer #shorts

**Título para YouTube Shorts:** `GTA 6 llega SIN ONLINE 😳 (y 4 secretos más) #shorts`

## Imágenes del juego

El vídeo no incluye capturas de GTA 6, porque son material con derechos de Rockstar. Lleva un fondo original de estilo neón y costa al atardecer. Si tienes material que puedas usar, por ejemplo capturas del kit de prensa oficial, ponlo en `imagenes/` con el `id` de la escena y se usará como fondo de esa escena con zoom suave (efecto Ken Burns):

```
imagenes/gancho.jpg   imagenes/dato1.jpg   imagenes/dato3.jpg  ...
```

## Cómo regenerarlo

Requisitos: Python 3, `numpy`, `Pillow` y `ffmpeg`.

```bash
pip install numpy pillow
python3 reel.py --preview 1   # fotogramas de muestra en salida/preview/
python3 reel.py               # vídeo completo en salida/reel.mp4 (~2 min)
```

Todo el contenido (textos, tiempos, colores, sellos, iconos) está en `guion.json`. Si cambias la `voz` de una escena, los subtítulos se recalculan solos.

La fuente es Inter (licencia OFL, en `fonts/`).
