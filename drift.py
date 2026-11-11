#!/usr/bin/env python3
"""Reel "¿Tu mando se mueve solo?": animaciones técnicas del drift de los joysticks.

Añade al motor de reel.py un fondo de plano técnico y efectos animados:
el mando genérico (diseño original, sin marca), su despiece, el potenciómetro
por dentro, el desgaste de la pista de carbono, las quejas y el efecto Hall.

Uso:
    python3 drift.py --guion guion_drift.json --salida salida/drift [--preview 2]
"""
import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import reel
from reel import W, H, clamp, ease_out_back, ease_out_cubic, ease_in_out, fuente, texto_con_estilo

CIAN = (45, 226, 230)
ROSA = (255, 61, 139)
AMARILLO = (255, 210, 63)
ROJO = (255, 60, 70)
VERDE = (60, 220, 140)
COBRE = (222, 140, 70)


# --------------------------------------------------------------------------
# fondo: plano técnico
# --------------------------------------------------------------------------

def ilus_taller(rnd):
    img = reel.degradado([(0, (8, 12, 30)), (0.5, (14, 22, 52)), (1, (6, 8, 20))])
    d = ImageDraw.Draw(img)
    for x in range(0, img.width, 40):
        d.line((x, 0, x, img.height), fill=(45, 226, 230, 22 if x % 200 else 45), width=1)
    for y in range(0, img.height, 40):
        d.line((0, y, img.width, y), fill=(45, 226, 230, 22 if y % 200 else 45), width=1)
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((img.width / 2 - 520, 260, img.width / 2 + 520, 1100), fill=(60, 80, 200, 70))
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(120)))
    return img


reel.ILUSTRACIONES["taller"] = ilus_taller


# --------------------------------------------------------------------------
# utilidades de dibujo
# --------------------------------------------------------------------------

def capa():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def brillo(img, col, radio=18, fuerza=0.9):
    a = img.getchannel("A").filter(ImageFilter.GaussianBlur(radio))
    g = Image.new("RGBA", img.size, col + (0,))
    g.putalpha(a.point(lambda v: int(v * fuerza)))
    return g


def etiqueta(frame, texto, x, y, hacia, aparicion, col=CIAN):
    """Etiqueta con línea guía: (x, y) es el punto señalado; hacia = (x, y) del texto."""
    if aparicion <= 0:
        return
    d = ImageDraw.Draw(frame)
    p = ease_out_cubic(aparicion)
    tx, ty = hacia
    mx, my = x + (tx - x) * p, y + (ty - y) * p
    d.line((x, y, mx, my), fill=col + (230,), width=4)
    d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=col + (255,))
    if p > 0.6:
        f = fuente(38)
        bb = f.getbbox(texto)
        a = int(255 * clamp((p - 0.6) / 0.4))
        izq = tx < x
        x0 = tx - bb[2] - 36 if izq else tx
        x0 = max(24, min(W - 24 - bb[2] - 36, x0))  # que no se salga de la pantalla
        d.rounded_rectangle((x0, ty - 32, x0 + bb[2] + 36, ty + 32), radius=12, fill=(8, 12, 30, int(a * 0.85)),
                            outline=col + (a,), width=3)
        d.text((x0 + 18, ty), texto, font=f, fill=(255, 255, 255, a), anchor="lm")


def lectura(frame, x, y, eje, valor, col):
    """Indicador digital del valor que lee la consola."""
    d = ImageDraw.Draw(frame)
    f = fuente(54)
    txt = f"{eje}: {valor:+.2f}"
    bb = f.getbbox("X: +0.00")
    w = bb[2] + 60
    d.rounded_rectangle((x - w / 2, y - 46, x + w / 2, y + 46), radius=16, fill=(4, 8, 20, 230), outline=col + (255,),
                        width=5)
    d.text((x, y), txt, font=f, fill=col + (255,), anchor="mm")


# --------------------------------------------------------------------------
# mando genérico (diseño original)
# --------------------------------------------------------------------------

STICK_IZQ = (-150, 70)
STICK_DER = (150, 70)


@lru_cache(maxsize=8)
def cuerpo_mando(s=1.0, tono=(40, 44, 60), contorno=CIAN):
    w, h = int(860 * s), int(520 * s)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    m = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(m)
    cx, cy = w / 2, h * 0.42
    dm.rounded_rectangle((cx - 300 * s, cy - 130 * s, cx + 300 * s, cy + 90 * s), radius=int(110 * s), fill=255)
    for lado in (-1, 1):  # empuñaduras
        gx = cx + lado * 290 * s
        dm.ellipse((gx - 130 * s, cy - 120 * s, gx + 130 * s, cy + 140 * s), fill=255)
        dm.polygon([(gx - 120 * s, cy + 40 * s), (gx + 120 * s, cy + 40 * s),
                    (gx + lado * 60 * s + 60 * s, cy + 270 * s), (gx + lado * 60 * s - 80 * s, cy + 280 * s)], fill=255)
        dm.ellipse((gx + lado * 60 * s - 90 * s, cy + 190 * s, gx + lado * 60 * s + 70 * s, cy + 300 * s), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(2))
    base = Image.new("RGBA", (w, h), tono + (255,))
    # degradado de volumen
    grad = np.linspace(1.25, 0.7, h)[:, None]
    arr = np.asarray(base).astype(float)
    arr[:, :, :3] = np.clip(arr[:, :, :3] * grad[:, :, None], 0, 255)
    base = Image.fromarray(arr.astype(np.uint8), "RGBA")
    base.putalpha(m)
    img.alpha_composite(base)
    # borde de luz
    borde = np.clip(np.asarray(m).astype(int) - np.roll(np.asarray(m).astype(int), 5, 0), 0, 255).astype(np.uint8)
    r = Image.new("RGBA", (w, h), contorno + (0,))
    r.putalpha(Image.fromarray(borde, "L"))
    img.alpha_composite(r)
    d = ImageDraw.Draw(img)
    # cruceta
    px, py = cx - 255 * s, cy - 40 * s
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        d.rounded_rectangle((px + dx * 38 * s - 20 * s, py + dy * 38 * s - 20 * s,
                             px + dx * 38 * s + 20 * s, py + dy * 38 * s + 20 * s), radius=int(6 * s), fill=(20, 22, 32, 255))
    d.rectangle((px - 20 * s, py - 20 * s, px + 20 * s, py + 20 * s), fill=(20, 22, 32, 255))
    # 4 botones lisos (sin símbolos)
    bx, by = cx + 255 * s, cy - 40 * s
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        x, y = bx + dx * 46 * s, by + dy * 46 * s
        d.ellipse((x - 25 * s, y - 25 * s, x + 25 * s, y + 25 * s), fill=(215, 220, 235, 255))
        d.ellipse((x - 17 * s, y - 21 * s, x + 13 * s, y + 5 * s), fill=(245, 248, 255, 255))
    # botones centrales y barra de luz
    for dx in (-60, 60):
        d.rounded_rectangle((cx + dx * s - 22 * s, cy - 92 * s, cx + dx * s + 22 * s, cy - 76 * s), radius=6,
                            fill=(20, 22, 32, 255))
    d.rounded_rectangle((cx - 110 * s, cy - 126 * s, cx + 110 * s, cy - 114 * s), radius=6, fill=CIAN + (255,))
    # huecos de los joysticks
    for sx, sy in (STICK_IZQ, STICK_DER):
        x, y = cx + sx * s, cy + sy * s - 70 * s
        d.ellipse((x - 72 * s, y - 72 * s, x + 72 * s, y + 72 * s), fill=(14, 16, 24, 255))
    return img


def palanca(d, x, y, s, off, col_aro=(90, 96, 120)):
    """Seta del joystick vista desde arriba; off = desplazamiento (-1..1, -1..1)."""
    ox, oy = off[0] * 26 * s, off[1] * 26 * s
    d.ellipse((x + ox - 56 * s, y + oy - 56 * s, x + ox + 56 * s, y + oy + 56 * s), fill=(28, 30, 42, 255))
    d.ellipse((x + ox - 50 * s, y + oy - 50 * s, x + ox + 50 * s, y + oy + 50 * s), fill=col_aro + (255,))
    d.ellipse((x + ox - 38 * s, y + oy - 38 * s, x + ox + 38 * s, y + oy + 38 * s), fill=(48, 52, 70, 255))
    for k in range(6):
        r = 30 * s - k * 5 * s
        d.ellipse((x + ox - r, y + oy - r, x + ox + r, y + oy + r), outline=(70, 76, 98, 255), width=2)


def dibujar_mando(frame, cx, cy, s, off_izq=(0, 0), off_der=(0, 0), alfa=1.0, aviso=0.0):
    cuerpo = cuerpo_mando(round(s, 3))
    if alfa < 0.999:
        cuerpo = cuerpo.copy()
        cuerpo.putalpha(cuerpo.getchannel("A").point(lambda v: int(v * alfa)))
    x0, y0 = int(cx - cuerpo.width / 2), int(cy - cuerpo.height * 0.42)
    frame.alpha_composite(cuerpo, (x0, y0))
    d = ImageDraw.Draw(frame)
    for (sx, sy), off in ((STICK_IZQ, off_izq), (STICK_DER, off_der)):
        palanca(d, cx + sx * s, cy + sy * s - 70 * s, s, off)
    if aviso > 0:  # aro rojo pulsante sobre el joystick izquierdo
        x, y = cx + STICK_IZQ[0] * s, cy + STICK_IZQ[1] * s - 70 * s
        r = 90 * s + 14 * s * math.sin(aviso * 12)
        d.ellipse((x - r, y - r, x + r, y + r), outline=ROJO + (230,), width=8)


# --------------------------------------------------------------------------
# efectos
# --------------------------------------------------------------------------

class ManoDrift(reel.Efecto):
    """Pantalla con un personaje que camina solo y el mando quieto con el joystick derivando."""

    def __init__(self, ev, semilla):
        self.t0 = ev.get("t", 0)

    def dibujar(self, frame, t, mapa):
        # televisor
        d = ImageDraw.Draw(frame)
        tx0, ty0, tx1, ty1 = 150, 170, 930, 600
        d.rounded_rectangle((tx0 - 14, ty0 - 14, tx1 + 14, ty1 + 14), radius=28, fill=(18, 20, 30, 255),
                            outline=(70, 80, 110, 255), width=4)
        pantalla = Image.new("RGBA", (tx1 - tx0, ty1 - ty0), (20, 16, 48, 255))
        dp = ImageDraw.Draw(pantalla)
        pw, ph = pantalla.size
        dp.rectangle((0, ph * 0.72, pw, ph), fill=(40, 26, 70, 255))
        desp = (t * 90) % 160
        for k in range(-1, 7):  # edificios que pasan (el personaje avanza solo)
            bx = k * 160 - desp
            alto = 90 + (k * 37) % 120
            dp.rectangle((bx, ph * 0.72 - alto, bx + 110, ph * 0.72), fill=(60, 36, 100, 255))
            for wy in range(int(ph * 0.72 - alto + 14), int(ph * 0.72 - 10), 24):
                dp.rectangle((bx + 18, wy, bx + 30, wy + 10), fill=(255, 205, 120, 200))
                dp.rectangle((bx + 70, wy, bx + 82, wy + 10), fill=(45, 226, 230, 200))
        # personaje original (silueta simple con gorra)
        px, py = pw * 0.45, ph * 0.72
        paso = math.sin(t * 11)
        col = (250, 250, 255, 255)
        dp.ellipse((px - 22, py - 150, px + 22, py - 106), fill=col)
        dp.rectangle((px - 26, py - 128, px + 30, py - 120), fill=ROSA + (255,))
        dp.rounded_rectangle((px - 26, py - 104, px + 26, py - 44), radius=10, fill=ROSA + (255,))
        dp.line((px - 8, py - 46, px - 8 + 22 * paso, py), fill=col, width=14)
        dp.line((px + 8, py - 46, px + 8 - 22 * paso, py), fill=col, width=14)
        dp.line((px, py - 96, px + 26 * paso, py - 56), fill=col, width=12)
        # aviso DRIFT y flecha
        if int(t * 4) % 2 == 0:
            f = fuente(64)
            dp.text((pw * 0.73, ph * 0.22), "DRIFT", font=f, fill=ROJO + (255,), anchor="mm")
        ax = pw * 0.6 + (t * 60) % 40
        dp.polygon([(ax, ph * 0.5 - 22), (ax + 60, ph * 0.5), (ax, ph * 0.5 + 22)], fill=AMARILLO + (255,))
        dp.rectangle((ax - 60, ph * 0.5 - 8, ax, ph * 0.5 + 8), fill=AMARILLO + (255,))
        frame.alpha_composite(pantalla, (tx0, ty0))
        # mando quieto; el joystick izquierdo tiembla hacia la derecha
        tiembla = (0.35 + 0.08 * math.sin(t * 37), 0.05 * math.sin(t * 29))
        dibujar_mando(frame, 540, 860, 0.82, off_izq=tiembla, aviso=t + 0.01)
        etiqueta(frame, "¡NO LO TOCAS!", 540 - 150 * 0.82, 860 - 0 * 0.82, (330, 1010), (t - 0.3) / 0.3, ROJO)


class Despiece(reel.Efecto):
    """El mando se abre en capas: carcasa, placa, batería, motores y módulos de joystick."""

    def __init__(self, ev, semilla):
        self.t0 = ev.get("t", 0)

    def dibujar(self, frame, t, mapa):
        a = t - self.t0
        sep = ease_in_out(a / 0.9)
        cx, cy, s = 540, 800, 0.82
        # carcasa inferior
        dibujar_mando(frame, cx, cy + 120 * sep, s, alfa=0.55)
        # placa base (verde, con pistas)
        pl = capa()
        dp = ImageDraw.Draw(pl)
        py = cy - 40 * sep - 10
        dp.rounded_rectangle((cx - 300, py - 90, cx + 300, py + 110), radius=60, fill=(20, 110, 70, 255),
                             outline=(120, 240, 170, 255), width=4)
        rnd = random.Random(4)
        for _ in range(26):
            x0, y0 = rnd.uniform(cx - 270, cx + 270), rnd.uniform(py - 70, py + 90)
            x1 = x0 + rnd.choice([-1, 1]) * rnd.uniform(40, 140)
            dp.line((x0, y0, x1, y0, x1, y0 + rnd.uniform(-40, 40)), fill=(180, 230, 120, 200), width=3)
        for k in range(4):
            dp.rectangle((cx - 60 + k * 32, py - 30, cx - 36 + k * 32, py + 10), fill=(15, 15, 20, 255))
        frame.alpha_composite(pl)
        d = ImageDraw.Draw(frame)
        # batería
        by = py + 10 - 160 * sep
        d.rounded_rectangle((cx - 90, by - 50, cx + 90, by + 50), radius=14, fill=(60, 70, 90, 255),
                            outline=(200, 210, 230, 255), width=4)
        d.text((cx, by), "+  −", font=fuente(48), fill=(255, 255, 255, 255), anchor="mm")
        # motores de vibración con peso excéntrico girando
        for lado in (-1, 1):
            mx, my = cx + lado * 330, py + 120 - 60 * sep
            d.rounded_rectangle((mx - 40, my - 55, mx + 40, my + 55), radius=18, fill=(150, 155, 170, 255))
            ang = t * 25 * lado
            ex, ey = mx + math.cos(ang) * 30, my - 70 + math.sin(ang) * 12
            d.line((mx, my - 55, mx, my - 70), fill=(200, 200, 210, 255), width=8)
            d.pieslice((ex - 30, ey - 22, ex + 30, ey + 22), math.degrees(ang), math.degrees(ang) + 180,
                       fill=(240, 200, 90, 255))
        # módulos de joystick
        for sx in (-150, 150):
            jx, jy = cx + sx * s, py - 30 - 230 * sep
            d.rectangle((jx - 62, jy - 62, jx + 62, jy + 62), fill=(120, 126, 145, 255), outline=AMARILLO + (255,),
                        width=5)
            d.rectangle((jx + 62, jy - 22, jx + 90, jy + 22), fill=(40, 40, 50, 255))
            d.rectangle((jx - 22, jy + 62, jx + 22, jy + 90), fill=(40, 40, 50, 255))
            d.ellipse((jx - 30, jy - 30, jx + 30, jy + 30), fill=(30, 32, 44, 255))
            d.ellipse((jx - 12, jy - 12, jx + 12, jy + 12), fill=(200, 160, 60, 255))
            if sep > 0.95:
                r = 80 + 8 * math.sin(t * 9)
                d.rectangle((jx - r, jy - r, jx + r, jy + r), outline=AMARILLO + (180,), width=4)
        # carcasa superior que sale volando hacia arriba
        if sep < 1:
            dibujar_mando(frame, cx, cy - 520 * sep, s, alfa=1 - sep * 0.85)
        # etiquetas
        etiqueta(frame, "PLACA", cx + 240, py + 60, (930, py + 170), (a - 0.9) / 0.3, (120, 240, 170))
        etiqueta(frame, "BATERÍA", cx - 90, by, (130, by - 60), (a - 1.15) / 0.3, (200, 210, 230))
        etiqueta(frame, "VIBRACIÓN", cx + 330, py + 60 - 60 * sep, (980, py - 60), (a - 1.4) / 0.3, (240, 200, 90))
        jx = cx - 150 * s
        etiqueta(frame, "JOYSTICKS", jx, py - 30 - 230 * sep - 62, (180, 300), (a - 1.65) / 0.3, AMARILLO)


def pista_y_lamina(frame, cx, cy, r, valor, desgaste=0.0, surcos=(), col_lectura=VERDE, t=0.0):
    """Potenciómetro por dentro: pista de carbono en arco y lámina de cobre (wiper)."""
    d = ImageDraw.Draw(frame)
    d.ellipse((cx - r - 30, cy - r - 30, cx + r + 30, cy + r + 30), fill=(10, 14, 30, 240), outline=CIAN + (255,),
              width=6)
    ini, fin = 150, 390  # grados (arco de 240°)
    tono = int(70 - 30 * desgaste)
    d.arc((cx - r, cy - r, cx + r, cy + r), ini, fin, fill=(tono, tono, tono + 10, 255), width=44)
    d.arc((cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8), ini, fin, fill=(110, 110, 125, 120), width=6)
    for ang_s, prof in surcos:  # surcos de desgaste
        a = math.radians(ang_s)
        for k in range(3):
            rr = r - 14 + k * 12
            d.line((cx + math.cos(a - 0.04) * rr, cy + math.sin(a - 0.04) * rr,
                    cx + math.cos(a + 0.04) * rr, cy + math.sin(a + 0.04) * rr), fill=(15, 12, 18, int(255 * prof)),
                   width=7)
    for ang_t in (ini, fin):  # terminales
        a = math.radians(ang_t)
        d.ellipse((cx + math.cos(a) * r - 18, cy + math.sin(a) * r - 18, cx + math.cos(a) * r + 18,
                   cy + math.sin(a) * r + 18), fill=COBRE + (255,))
    ang = math.radians(270 + valor * 115)  # posición de la lámina
    ex, ey = cx + math.cos(ang) * r, cy + math.sin(ang) * r
    d.line((cx, cy, ex, ey), fill=COBRE + (255,), width=18)
    d.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), fill=(200, 205, 220, 255))
    g = capa()
    ImageDraw.Draw(g).ellipse((ex - 26, ey - 26, ex + 26, ey + 26), fill=AMARILLO + (255,))
    frame.alpha_composite(g.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(frame)
    d.ellipse((ex - 12, ey - 12, ex + 12, ey + 12), fill=(255, 250, 220, 255))
    return ex, ey


def modulo_joystick(frame, cx, cy, off_x, s=1.0):
    """Módulo del joystick en vista lateral con su potenciómetro del eje X."""
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((cx - 120 * s, cy - 40 * s, cx + 120 * s, cy + 110 * s), radius=14,
                        fill=(110, 116, 135, 255), outline=(200, 205, 225, 255), width=4)
    ang = off_x * 0.45
    tx, ty = cx + math.sin(ang) * 200 * s, cy - math.cos(ang) * 200 * s
    d.line((cx, cy + 10 * s, tx, ty), fill=(70, 74, 90, 255), width=int(28 * s))
    d.ellipse((tx - 70 * s, ty - 26 * s, tx + 70 * s, ty + 26 * s), fill=(48, 52, 70, 255), outline=(90, 96, 120, 255),
              width=4)
    d.rectangle((cx + 120 * s, cy + 10 * s, cx + 170 * s, cy + 70 * s), fill=(40, 40, 50, 255),
                outline=AMARILLO + (255,), width=4)
    return cx + 170 * s, cy + 40 * s


class Potenciometro(reel.Efecto):
    """Cómo funciona: la palanca mueve la lámina por la pista y la consola lee un número."""

    def __init__(self, ev, semilla):
        self.t0 = ev.get("t", 0)

    def dibujar(self, frame, t, mapa):
        a = max(0.0, t - self.t0)
        valor = math.sin(a * 2.4) * clamp(a / 0.4)
        sx, sy = modulo_joystick(frame, 250, 640, valor, 0.95)
        cx, cy, r = 735, 560, 190
        d = ImageDraw.Draw(frame)
        d.line((sx, sy, cx - r - 30, cy + 40), fill=CIAN + (180,), width=3)
        d.line((sx, sy - 40, cx - r * 0.7, cy - r * 0.8), fill=CIAN + (180,), width=3)
        pista_y_lamina(frame, cx, cy, r, valor, t=a)
        etiqueta(frame, "PISTA DE CARBONO", cx - r * 0.86, cy + r * 0.5, (cx - 20, cy + 300), (a - 0.3) / 0.3,
                 (180, 180, 200))
        etiqueta(frame, "LÁMINA DE METAL", cx + math.cos(math.radians(270 + valor * 115)) * r * 0.5,
                 cy + math.sin(math.radians(270 + valor * 115)) * r * 0.5, (cx + 40, 250), (a - 0.6) / 0.3, COBRE)
        lectura(frame, 250, 920, "X", valor, VERDE)


class Desgaste(reel.Efecto):
    """Con el roce la pista se desgasta, salen restos, entra polvo y en reposo ya no marca 0."""

    def __init__(self, ev, semilla):
        rnd = random.Random(semilla)
        self.t0 = ev.get("t", 0)
        self.surcos = [(rnd.uniform(200, 340), rnd.uniform(0.4, 1.0)) for _ in range(18)]
        self.restos = [(rnd.uniform(0, 1.6), rnd.uniform(0, 6.28), rnd.uniform(60, 240)) for _ in range(70)]
        self.polvo = [(rnd.uniform(0, W), rnd.uniform(150, 1000), rnd.uniform(0.5, 2)) for _ in range(60)]

    def dibujar(self, frame, t, mapa):
        a = max(0.0, t - self.t0)
        rozando = a < 1.6
        if rozando:
            valor = math.sin(a * 9) * 0.9
        else:
            valor = 0.13 + 0.02 * math.sin(a * 20)  # suelta el mando pero no vuelve a 0
        desgaste = clamp(a / 1.6)
        n = int(len(self.surcos) * desgaste)
        sx, sy = modulo_joystick(frame, 250, 640, valor if rozando else 0.0, 0.95)
        cx, cy, r = 735, 560, 190
        ex, ey = pista_y_lamina(frame, cx, cy, r, valor, desgaste, self.surcos[:n], t=a)
        d = ImageDraw.Draw(frame)
        for nace, ang, vel in self.restos:  # partículas de carbono arrancadas
            b = a - nace
            if 0 < b < 0.7 and nace < 1.6:
                px, py = ex + math.cos(ang) * vel * b, ey + math.sin(ang) * vel * b + 300 * b * b
                d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=(20, 18, 24, int(255 * (1 - b / 0.7))))
        for x, y, vel in self.polvo:  # polvo que entra
            px = (x + a * 60 * vel) % W
            py = y + math.sin(a * vel * 2 + x) * 20
            d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=(200, 190, 160, int(140 * desgaste)))
        if not rozando:
            etiqueta(frame, "SUELTAS... Y NO ES 0", 250, 600, (110, 300), (a - 1.7) / 0.25, ROJO)
            lectura(frame, 250, 920, "X", valor, ROJO)
        else:
            lectura(frame, 250, 920, "X", valor, VERDE)
            etiqueta(frame, "ROCE = DESGASTE", ex, ey, (cx, 250), (a - 0.2) / 0.3, AMARILLO)


class Quejas(reel.Efecto):
    """Sobres de queja volando a una bandeja y contador hasta 25.000."""

    def __init__(self, ev, semilla):
        rnd = random.Random(semilla)
        self.t0 = ev.get("t", 0)
        self.total = ev.get("total", 25000)
        self.sobres = [(rnd.uniform(0, 1.8), rnd.uniform(-60, W + 60), rnd.uniform(-25, 25)) for _ in range(40)]

    def dibujar(self, frame, t, mapa):
        a = max(0.0, t - self.t0)
        d = ImageDraw.Draw(frame)
        # bandeja
        d.polygon([(250, 900), (830, 900), (790, 1000), (290, 1000)], fill=(60, 66, 90, 255), outline=CIAN + (255,))
        for nace, x0, giro in self.sobres:
            b = a - nace
            if b < 0:
                continue
            p = ease_out_cubic(b / 0.6)
            x = x0 + (540 + (x0 % 300) - 150 - x0) * p
            if p < 0.02:
                continue
            y = 620 + (880 - (nace * 20) % 60 - 620) * p
            ang = giro * (1 - p)
            sobre = Image.new("RGBA", (150, 100), (0, 0, 0, 0))
            ds = ImageDraw.Draw(sobre)
            ds.rectangle((2, 2, 147, 97), fill=(245, 245, 250, 255), outline=(180, 180, 200, 255), width=3)
            ds.line((2, 2, 75, 55, 147, 2), fill=(180, 180, 200, 255), width=4)
            reel.pegar_centrado(frame, sobre, x, y, angulo=ang)
        cuenta = int(self.total * ease_out_cubic(a / 1.8))
        txt = f"{cuenta:,}".replace(",", ".")
        capa_n = texto_con_estilo(txt, fuente(200), AMARILLO + (255,), borde=10, color_borde=(16, 4, 24), brillo=ROSA)
        reel.pegar_centrado(frame, capa_n, 540, 360, escala=1 + 0.04 * math.sin(a * 10))
        f = fuente(50)
        d = ImageDraw.Draw(frame)
        d.rounded_rectangle((300, 495, 780, 565), radius=14, fill=(8, 12, 30, 220))
        d.text((540, 530), "QUEJAS EN EUROPA", font=f, fill=(255, 255, 255, 255), anchor="mm")


class EfectoHall(reel.Efecto):
    """Imán en la palanca + sensor debajo: miden sin tocarse."""

    def __init__(self, ev, semilla):
        self.t0 = ev.get("t", 0)

    def dibujar(self, frame, t, mapa):
        a = max(0.0, t - self.t0)
        valor = math.sin(a * 2.6) * clamp(a / 0.4) if a < 2.2 else 0.0
        cx, base = 540, 900
        ang = valor * 0.35
        d = ImageDraw.Draw(frame)
        # sensor (chip) con patas
        d.rounded_rectangle((cx - 110, base, cx + 110, base + 70), radius=8, fill=(20, 22, 30, 255),
                            outline=(140, 150, 170, 255), width=3)
        for k in range(6):
            x = cx - 90 + k * 36
            d.rectangle((x, base + 70, x + 12, base + 100), fill=(200, 200, 210, 255))
        d.text((cx, base + 35), "SENSOR", font=fuente(34), fill=(200, 210, 230, 255), anchor="mm")
        # palanca con imán en la punta inferior
        pivote = (cx, 600)
        ix, iy = pivote[0] - math.sin(ang) * 170, pivote[1] + math.cos(ang) * 170
        tx, ty = pivote[0] + math.sin(ang) * 260, pivote[1] - math.cos(ang) * 260
        d.line((ix, iy, tx, ty), fill=(90, 96, 120, 255), width=30)
        d.ellipse((tx - 80, ty - 28, tx + 80, ty + 28), fill=(48, 52, 70, 255), outline=(110, 116, 140, 255), width=4)
        iman = Image.new("RGBA", (120, 90), (0, 0, 0, 0))
        di = ImageDraw.Draw(iman)
        di.rectangle((0, 0, 59, 89), fill=(230, 60, 70, 255))
        di.rectangle((60, 0, 119, 89), fill=(60, 110, 240, 255))
        di.text((30, 45), "N", font=fuente(44), fill=(255, 255, 255, 255), anchor="mm")
        di.text((90, 45), "S", font=fuente(44), fill=(255, 255, 255, 255), anchor="mm")
        reel.pegar_centrado(frame, iman, ix, iy + 20, angulo=-math.degrees(ang))
        # líneas de campo animadas (sin contacto)
        campo = capa()
        dc = ImageDraw.Draw(campo)
        for k in range(1, 6):
            fase = (a * 1.5 + k * 0.2) % 1
            ancho = 50 + k * 34
            alto = 40 + k * 14
            yy = iy + 70
            dc.arc((ix - ancho, yy - alto, ix + ancho, yy + alto), 20, 160,
                   fill=CIAN + (int(200 * (1 - fase * 0.6)),), width=4)
        frame.alpha_composite(campo.filter(ImageFilter.GaussianBlur(1)))
        frame.alpha_composite(brillo(campo, CIAN, 10, 0.6))
        d = ImageDraw.Draw(frame)
        # hueco sin contacto marcado
        gy0, gy1 = iy + 65, base - 4
        if gy1 > gy0:
            d.line((cx + 170, gy0, cx + 170, gy1), fill=VERDE + (255,), width=5)
            d.line((cx + 155, gy0, cx + 185, gy0), fill=VERDE + (255,), width=5)
            d.line((cx + 155, gy1, cx + 185, gy1), fill=VERDE + (255,), width=5)
        etiqueta(frame, "SIN CONTACTO", cx + 170, (gy0 + gy1) / 2, (cx + 230, 420), (a - 0.3) / 0.3, VERDE)
        etiqueta(frame, "IMÁN", ix - 60, iy + 20, (180, 470), (a - 0.55) / 0.3, (240, 120, 130))
        lectura(frame, 250, 1000, "X", valor, VERDE)
        if a > 2.2:  # en reposo marca 0 exacto
            ok = ease_out_back((a - 2.2) / 0.3, 2.5)
            x, y = 450, 1000
            d.line((x - 22 * ok, y, x - 6 * ok, y + 18 * ok, x + 26 * ok, y - 20 * ok), fill=VERDE + (255,),
                   width=10)


reel.FX.update({"mando_drift": ManoDrift, "despiece": Despiece, "potenciometro": Potenciometro,
                "desgaste": Desgaste, "quejas": Quejas, "hall": EfectoHall})


if __name__ == "__main__":
    reel.main()
