#!/usr/bin/env python3
"""Reel "Medio día antes que tú": clips de acción de fondo (IA, originales) y capas animadas.

Capas nuevas (todas dibujadas por código, sin logos):
  - relojes:   dos marcadores digitales (Nueva Zelanda / España) que ruedan y se clavan.
  - espera:    barra de 12 horas que se llena de Nueva Zelanda a España.
  - lobby:     "BUSCANDO JUGADORES" con ruleta y sello de "NO DISPONIBLE".
  - fps:       contador de FPS y comparativa 60 (suave) / 30 (a saltos).
  - modo_juego: interruptor OFF -> ON y barra de retraso que baja.
  - clip_tramo: un clip que sólo se ve entre "desde" y "hasta" (para encadenar dos clips en una escena).

Uso:
    python3 doce.py --guion guion_doce_horas.json --salida salida/doce_horas
"""
import math

from PIL import Image, ImageDraw, ImageFilter

import reel
import drift2  # registra "clip" y "velo_superior"
from reel import W, clamp, ease_out_back, ease_out_cubic, ease_in_out, fuente, pegar_centrado, texto_con_estilo

VERDE, ROJO, AMARILLO, CIAN, ROSA = (60, 230, 120), (255, 50, 70), (255, 210, 63), (45, 226, 230), (255, 61, 139)
OSCURO = (12, 8, 24)


def tarjeta(w, h, relleno=(20, 14, 38, 195), borde=None, radio=34):
    img = Image.new("RGBA", (w + 40, h + 50), (0, 0, 0, 0))
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((26, 30, w + 26, h + 30), radius=radio, fill=(0, 0, 0, 150))
    img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((20, 20, w + 20, h + 20), radius=radio, fill=relleno,
                        outline=borde + (255,) if borde else None, width=5 if borde else 0)
    return img


def entrada(a, dur=0.35):
    return ease_out_back(a / dur, 1.6) if a >= 0 else 0.0


class Relojes(reel.Efecto):
    """Dos marcadores: las cifras ruedan a toda velocidad y se clavan con un golpe."""

    def __init__(self, ev, semilla):
        self.t0, self.para = ev.get("t", 0.0), ev.get("para", 0.75)
        self.y = ev.get("y", 900)
        self.datos = [("NUEVA ZELANDA", "00:00", "19 NOV", "¡YA JUEGAN!", VERDE),
                      ("ESPAÑA", "12:00", "18 NOV", "ESPERANDO", ROJO)]
        self.base = tarjeta(430, 330)
        self.cache = {}

    def _num(self, s, col):
        k = (s, col)
        if k not in self.cache:
            self.cache[k] = texto_con_estilo(s, fuente(128), col + (255,), borde=8, color_borde=OSCURO)
        return self.cache[k]

    def destello(self, t):
        b = t - self.t0 - self.para
        return 0.35 * (1 - b / 0.2) ** 2 if 0 <= b < 0.2 else 0

    def sacudida(self, t):
        b = t - self.t0 - self.para
        return 16 * (1 - b / 0.25) if 0 <= b < 0.25 else 0

    def encima(self, frame, t):
        a = t - self.t0
        for k, (lugar, hora, dia, estado, col) in enumerate(self.datos):
            x = 290 + k * 500
            pegar_centrado(frame, self.base, x, self.y, escala=1.0 if self.t0 <= 0 else entrada(a))
            d = ImageDraw.Draw(frame)
            d.text((x, self.y - 120), lugar, font=fuente(40), fill=(220, 210, 240, 255), anchor="mm")
            if a < self.para:  # cifras rodando
                n = int((t * 37 + k * 13) * 10) % 1440
                txt, c = f"{n // 60:02d}:{n % 60:02d}", (255, 255, 255)
                esc = 1.0
            else:
                txt, c = hora, AMARILLO
                b = a - self.para
                esc = 1 + 0.18 * math.exp(-b * 9)
            pegar_centrado(frame, self._num(txt, c), x, self.y - 10, escala=esc)
            if a >= self.para:
                d.text((x, self.y + 80), dia, font=fuente(40), fill=(200, 190, 220, 255), anchor="mm")
                b = a - self.para - 0.15
                if b >= 0:
                    chip = texto_con_estilo(estado, fuente(44), col + (255,), borde=6, color_borde=OSCURO)
                    pegar_centrado(frame, chip, x, self.y + 145, escala=ease_out_back(b / 0.3))


class Espera(reel.Efecto):
    """Barra de 12 horas: de Nueva Zelanda (ya juega) a España (le toca 12 h después)."""

    def __init__(self, ev, semilla):
        self.t0, self.dur, self.y = ev.get("t", 0.3), ev.get("dur", 3.0), ev.get("y", 880)
        self.base = tarjeta(940, 300)

    def encima(self, frame, t):
        a = t - self.t0
        if a < 0:
            return
        pegar_centrado(frame, self.base, W / 2, self.y, escala=entrada(a))
        if a < 0.3:
            return
        d = ImageDraw.Draw(frame)
        x0, x1, yb = 120, 960, self.y + 10
        d.rounded_rectangle((x0, yb - 22, x1, yb + 22), radius=22, fill=(60, 50, 80, 255))
        p = ease_in_out(clamp((a - 0.3) / self.dur))
        xf = x0 + (x1 - x0) * p
        d.rounded_rectangle((x0, yb - 22, max(x0 + 44, xf), yb + 22), radius=22, fill=AMARILLO + (255,))
        d.ellipse((xf - 30, yb - 30, xf + 30, yb + 30), fill=(255, 255, 255, 255))
        d.text((x0, self.y - 80), "NUEVA ZELANDA", font=fuente(40), fill=VERDE + (255,), anchor="lm")
        d.text((x1, self.y - 80), "ESPAÑA", font=fuente(40), fill=ROSA + (255,), anchor="rm")
        d.text((x0, self.y + 90), "00:00", font=fuente(48), fill=(255, 255, 255, 255), anchor="lm")
        d.text((x1, self.y + 90), "12:00", font=fuente(48), fill=(255, 255, 255, 255), anchor="rm")
        horas = int(round(12 * p))
        chip = texto_con_estilo(f"+{horas} H", fuente(70), AMARILLO + (255,), borde=8, color_borde=OSCURO)
        pegar_centrado(frame, chip, W / 2, self.y + 95, escala=1 + (0.15 if horas == 12 else 0) * math.exp(
            -max(0, a - 0.3 - self.dur) * 8))


class Lobby(reel.Efecto):
    """Pantalla de 'BUSCANDO JUGADORES' con ruleta, y sello rojo de NO DISPONIBLE."""

    def __init__(self, ev, semilla):
        self.t0, self.t_sello, self.y = ev.get("t", 0.2), ev.get("sello", 2.6), ev.get("y", 860)
        self.base = tarjeta(860, 420)
        self.sello = texto_con_estilo("NO DISPONIBLE", fuente(110), ROJO + (255,), borde=12,
                                      color_borde=(40, 0, 10), brillo=(255, 40, 60))

    def destello(self, t):
        b = t - self.t_sello
        return 0.25 * (1 - b / 0.2) ** 2 if 0 <= b < 0.2 else 0

    def sacudida(self, t):
        b = t - self.t_sello
        return 14 * (1 - b / 0.25) if 0 <= b < 0.25 else 0

    def encima(self, frame, t):
        a = t - self.t0
        if a < 0:
            return
        pegar_centrado(frame, self.base, W / 2, self.y, escala=entrada(a))
        if a < 0.3:
            return
        d = ImageDraw.Draw(frame)
        d.text((W / 2, self.y - 140), "MODO ONLINE", font=fuente(56), fill=(255, 255, 255, 255), anchor="mm")
        cx, cy, r = W / 2, self.y + 10, 70
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(70, 60, 95, 255), width=16)
        ang = (t * 400) % 360
        d.arc((cx - r, cy - r, cx + r, cy + r), ang, ang + 100, fill=CIAN + (255,), width=16)
        puntos = "." * (1 + int(t * 3) % 3)
        d.text((W / 2, self.y + 140), f"BUSCANDO JUGADORES{puntos}", font=fuente(46),
               fill=(200, 190, 220, 255), anchor="mm")
        b = t - self.t_sello
        if b >= 0:
            esc = 2.0 - 1.0 * ease_out_cubic(b / 0.18)
            pegar_centrado(frame, self.sello, W / 2, self.y + 10, escala=esc, alfa=clamp(b / 0.08), angulo=-10)


class Fps(reel.Efecto):
    """Contador de FPS y dos carriles: a 60 la bola va suave; a 30 va a saltos."""

    def __init__(self, ev, semilla):
        self.t0, self.y = ev.get("t", 0.2), ev.get("y", 860)
        self.base = tarjeta(900, 420)
        self.n30 = texto_con_estilo("30 FPS", fuente(120), AMARILLO + (255,), borde=10, color_borde=OSCURO,
                                    brillo=(255, 140, 60))

    def encima(self, frame, t):
        a = t - self.t0
        if a < 0:
            return
        pegar_centrado(frame, self.base, W / 2, self.y, escala=entrada(a))
        if a < 0.3:
            return
        pegar_centrado(frame, self.n30, W / 2, self.y - 120, escala=1 + 0.04 * math.sin(a * 5))
        d = ImageDraw.Draw(frame)
        x0, x1 = 230, 900
        for k, (lab, fps, col) in enumerate((("60", 60, VERDE), ("30", 30, AMARILLO))):
            yy = self.y + 20 + k * 110
            d.text((150, yy), lab, font=fuente(52), fill=col + (255,), anchor="mm")
            d.rounded_rectangle((x0, yy - 8, x1, yy + 8), radius=8, fill=(60, 50, 80, 255))
            fase = (a * 0.9) % 1.0
            paso = math.floor(fase * fps / 2) / (fps / 2)  # a 30 se ve la mitad de posiciones
            u = fase if fps == 60 else paso
            u = 0.5 - 0.5 * math.cos(u * 2 * math.pi)
            bx = x0 + (x1 - x0) * u
            d.ellipse((bx - 30, yy - 30, bx + 30, yy + 30), fill=col + (255,))


class ModoJuego(reel.Efecto):
    """Interruptor de MODO JUEGO que pasa a ON y la barra de retraso que baja."""

    def __init__(self, ev, semilla):
        self.t0, self.t_on, self.y = ev.get("t", 0.15), ev.get("on", 1.2), ev.get("y", 880)
        self.base = tarjeta(860, 400)

    def destello(self, t):
        b = t - self.t_on
        return 0.2 * (1 - b / 0.2) ** 2 if 0 <= b < 0.2 else 0

    def encima(self, frame, t):
        a = t - self.t0
        if a < 0:
            return
        pegar_centrado(frame, self.base, W / 2, self.y, escala=entrada(a))
        if a < 0.3:
            return
        d = ImageDraw.Draw(frame)
        p = ease_out_cubic(clamp((t - self.t_on) / 0.25))
        d.text((150, self.y - 100), "MODO JUEGO", font=fuente(64), fill=(255, 255, 255, 255), anchor="lm")
        sx, sy = 800, self.y - 100
        col = tuple(int(90 + (c - 90) * p) for c in VERDE)
        d.rounded_rectangle((sx - 80, sy - 42, sx + 80, sy + 42), radius=42, fill=col + (255,))
        kx = sx - 38 + 76 * p
        d.ellipse((kx - 34, sy - 34, kx + 34, sy + 34), fill=(255, 255, 255, 255))
        d.text((sx, sy + 75), "ON" if p > 0.5 else "OFF", font=fuente(40),
               fill=(VERDE if p > 0.5 else (180, 170, 200)) + (255,), anchor="mm")
        d.text((150, self.y + 50), "RETRASO", font=fuente(48), fill=(200, 190, 220, 255), anchor="lm")
        largo = 1.0 - 0.75 * ease_in_out(clamp((t - self.t_on - 0.1) / 0.6))
        bc = ROJO if largo > 0.6 else (AMARILLO if largo > 0.35 else VERDE)
        d.rounded_rectangle((150, self.y + 100, 930, self.y + 140), radius=20, fill=(60, 50, 80, 255))
        d.rounded_rectangle((150, self.y + 100, 150 + 780 * largo, self.y + 140), radius=20, fill=bc + (255,))


class ClipTramo(drift2.Clip):
    """Clip que sólo se dibuja entre 'desde' y 'hasta' (tiempo de la escena)."""

    def dibujar(self, frame, t, mapa):
        desde, hasta = self.ev.get("desde", 0), self.ev.get("hasta", 1e9)
        if desde <= t < hasta:
            super().dibujar(frame, t - desde + self.ev.get("offset", 0.0), mapa)


class Paises(reel.Efecto):
    """Tabla de horas: qué hora es en cada país cuando en Nueva Zelanda ya se juega."""

    FILAS = [("NUEVA ZELANDA", "00:00", "19 NOV", None), ("ESPAÑA", "12:00", "18 NOV", "+12 H"),
             ("ARGENTINA · CHILE", "08:00", "18 NOV", "+16 H"), ("COLOMBIA · PERÚ", "06:00", "18 NOV", "+18 H"),
             ("MÉXICO", "05:00", "18 NOV", "+19 H")]

    def __init__(self, ev, semilla):
        self.t0, self.y = ev.get("t", 0.15), ev.get("y", 900)
        self.tiempos = ev.get("filas", [0.4, 3.2, 4.0, 4.6, 5.3])
        self.base = tarjeta(940, 560)

    def encima(self, frame, t):
        a = t - self.t0
        if a < 0:
            return
        top = self.y - 280
        pegar_centrado(frame, self.base, W / 2, self.y, escala=entrada(a))
        if a < 0.3:
            return
        d = ImageDraw.Draw(frame)
        for k, ((pais, hora, dia, dif), tk) in enumerate(zip(self.FILAS, self.tiempos)):
            b = t - tk
            if b < 0:
                continue
            p = ease_out_cubic(clamp(b / 0.25))
            yy = top + 70 + k * 105
            dx = (1 - p) * 120
            if k == 0:
                d.rounded_rectangle((90, yy - 44, 990, yy + 44), radius=22, fill=(40, 120, 70, int(200 * p)))
            col_p = VERDE if k == 0 else (255, 255, 255)
            d.text((115 + dx, yy), pais, font=fuente(38), fill=col_p + (int(255 * p),), anchor="lm")
            d.text((770 + dx, yy), hora, font=fuente(58), fill=AMARILLO + (int(255 * p),), anchor="rm")
            if dif:
                d.text((975, yy), dif, font=fuente(40), fill=ROSA + (int(255 * p),), anchor="rm")
            elif b > 0.25:
                chip = texto_con_estilo("¡YA!", fuente(44), (255, 255, 255, 255), borde=6, color_borde=OSCURO)
                pegar_centrado(frame, chip, 900, yy, escala=1 + 0.08 * math.sin(b * 8))


class MenuXbox(reel.Efecto):
    """Menú de ajustes genérico: el cursor baja paso a paso hasta 'NUEVA ZELANDA' y aparece el aviso."""

    PASOS = ["CONFIGURACIÓN", "SISTEMA", "IDIOMA Y UBICACIÓN", "UBICACIÓN: NUEVA ZELANDA"]

    def __init__(self, ev, semilla):
        self.t0, self.y = ev.get("t", 0.15), ev.get("y", 880)
        self.pasos_t = ev.get("pasos", [1.4, 2.2, 3.0, 3.8])
        self.t_aviso = ev.get("aviso", 5.2)
        self.base = tarjeta(900, 520)
        self.aviso = texto_con_estilo("NO GARANTIZADO", fuente(64), (255, 150, 40, 255), borde=8,
                                      color_borde=(40, 10, 0))

    def encima(self, frame, t):
        a = t - self.t0
        if a < 0:
            return
        pegar_centrado(frame, self.base, W / 2, self.y, escala=entrada(a))
        if a < 0.3:
            return
        d = ImageDraw.Draw(frame)
        top = self.y - 260
        d.text((W / 2, top + 50), "AJUSTES DE LA CONSOLA", font=fuente(40), fill=(200, 190, 220, 255), anchor="mm")
        activo = sum(1 for tp in self.pasos_t if t >= tp) - 1
        for k, paso in enumerate(self.PASOS):
            yy = top + 140 + k * 95
            if k == activo:
                d.rounded_rectangle((110, yy - 38, 970, yy + 38), radius=20, fill=(255, 255, 255, 235))
                col = (20, 12, 30)
            else:
                col = (255, 255, 255) if k < max(activo, 0) else (150, 140, 170)
            final = k == 3 and activo == 3
            d.text((150, yy), paso, font=fuente(42), fill=(VERDE if final else col) + (255,) if not k == activo
                   else col + (255,), anchor="lm")
            if k < 3:
                d.text((930, yy), "›", font=fuente(50), fill=col + (255,), anchor="mm")
            elif final:  # tick dibujado
                d.line([(905, yy), (922, yy + 17), (950, yy - 18)], fill=(40, 170, 90, 255), width=9,
                       joint="curve")
        b = t - self.t_aviso
        if b >= 0:
            pegar_centrado(frame, self.aviso, W / 2, self.y + 300, escala=ease_out_back(b / 0.3), angulo=-4)


reel.FX.update({"paises": Paises, "menu_xbox": MenuXbox, "relojes": Relojes, "espera": Espera, "lobby": Lobby, "fps": Fps, "modo_juego": ModoJuego,
                "clip_tramo": ClipTramo})

if __name__ == "__main__":
    reel.main()
