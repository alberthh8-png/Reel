#!/usr/bin/env python3
"""Genera un reel vertical de acción (1080x1920) a partir de guion.json.

Uso:
    python3 reel.py                 # render completo -> salida/reel.mp4
    python3 reel.py --preview 2     # fotogramas de muestra -> salida/preview/

Todas las ilustraciones (ciudad, coches, helicóptero, yate, personajes en
silueta genéricos) se dibujan por código: son originales y libres de derechos.
Si pones una imagen propia en ./imagenes/<id_escena>.jpg|png se usará como
fondo de esa escena en lugar de la ilustración.
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import wave
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
FUENTE_BOLD = os.path.join(RAIZ, "fonts", "Inter-ExtraBold.otf")
FUENTE_MED = os.path.join(RAIZ, "fonts", "Inter-Medium.otf")
SALIDA = os.path.join(RAIZ, "salida")
W, H = 1080, 1920
MARGEN = (54, 96)            # margen extra de la ilustración para mover la cámara
WC, HC = W + 2 * MARGEN[0], H + 2 * MARGEN[1]
TRANS = 0.25
OSCURO = (10, 6, 20, 255)

# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------

def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_cubic(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_out_back(t, s=1.9):
    t = clamp(t) - 1
    return t * t * ((s + 1) * t + s) + 1


def ease_in_out(t):
    t = clamp(t)
    return 3 * t * t - 2 * t * t * t


def mezclar(c0, c1, t):
    t = clamp(t)
    return tuple(int(a + (b - a) * t) for a, b in zip(c0, c1))


_fuentes = {}


def fuente(tam, bold=True):
    clave = (tam, bold)
    if clave not in _fuentes:
        _fuentes[clave] = ImageFont.truetype(FUENTE_BOLD if bold else FUENTE_MED, tam)
    return _fuentes[clave]


def ajustar_fuente(texto, ancho_max, tam_max, bold=True, tam_min=40, borde=0):
    tam = tam_max
    while tam > tam_min:
        f = fuente(tam, bold)
        if f.getbbox(texto, stroke_width=borde)[2] <= ancho_max:
            return f
        tam -= 4
    return fuente(tam_min, bold)


def texto_con_estilo(texto, f, relleno, borde=0, color_borde=(0, 0, 0), sombra=True, brillo=None):
    x0, y0, x1, y1 = f.getbbox(texto, stroke_width=borde)
    pad = 44
    w, h = x1 - x0 + pad * 2, y1 - y0 + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pos = (pad - x0, pad - y0)
    if brillo:
        g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(g).text(pos, texto, font=f, fill=brillo + (255,),
                               stroke_width=borde + 6, stroke_fill=brillo + (255,))
        img.alpha_composite(g.filter(ImageFilter.GaussianBlur(18)))
    if sombra:
        s = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(s).text((pos[0] + 8, pos[1] + 12), texto, font=f, fill=(0, 0, 0, 190),
                               stroke_width=borde, stroke_fill=(0, 0, 0, 190))
        img.alpha_composite(s.filter(ImageFilter.GaussianBlur(5)))
    ImageDraw.Draw(img).text(pos, texto, font=f, fill=relleno, stroke_width=borde, stroke_fill=color_borde)
    return img


def pegar_centrado(base, capa, cx, cy, escala=1.0, alfa=1.0, angulo=0.0):
    if escala <= 0.01 or alfa <= 0.01:
        return
    if abs(escala - 1) > 1e-3:
        capa = capa.resize((max(1, int(capa.width * escala)), max(1, int(capa.height * escala))),
                           Image.BILINEAR)
    if angulo:
        capa = capa.rotate(angulo, resample=Image.BICUBIC, expand=True)
    if alfa < 0.999:
        capa = capa.copy()
        capa.putalpha(capa.getchannel("A").point(lambda v: int(v * alfa)))
    base.alpha_composite(capa, (int(cx - capa.width / 2), int(cy - capa.height / 2)))


# --------------------------------------------------------------------------
# ilustraciones originales (coordenadas de pantalla 1080x1920)
# --------------------------------------------------------------------------

def degradado(paradas, w=WC, h=HC):
    y = np.linspace(0, 1, h)
    img = np.zeros((h, 3), np.float32)
    for (p0, c0), (p1, c1) in zip(paradas, paradas[1:]):
        m = (y >= p0) & (y <= p1)
        t = np.clip((y - p0) / max(p1 - p0, 1e-6), 0, 1)
        for k in range(3):
            img[m, k] = (c0[k] + (c1[k] - c0[k]) * t)[m]
    arr = np.repeat(img[:, None, :], w, 1).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


class Lienzo:
    """Lienzo con margen; se dibuja en coordenadas de pantalla."""

    def __init__(self, fondo):
        self.img = fondo
        self.ox, self.oy = MARGEN

    def capa(self):
        return Image.new("RGBA", (WC, HC), (0, 0, 0, 0))

    def p(self, x, y):
        return (x + self.ox, y + self.oy)

    def pts(self, lista):
        return [self.p(x, y) for x, y in lista]

    def poner(self, capa, borde=None, brillo=None, grosor_borde=5):
        """Compone una silueta añadiendo luz de borde (rim light) y halo."""
        if brillo:
            a = capa.getchannel("A").filter(ImageFilter.GaussianBlur(26))
            halo = Image.new("RGBA", capa.size, brillo + (0,))
            halo.putalpha(a.point(lambda v: int(v * 0.8)))
            self.img.alpha_composite(halo)
        self.img.alpha_composite(capa)
        if borde:
            a = np.asarray(capa.getchannel("A")).astype(np.int16)
            dx, dy = borde[1]
            desplazada = np.roll(np.roll(a, dy * grosor_borde, 0), dx * grosor_borde, 1)
            rim = np.clip(a - desplazada, 0, 255).astype(np.uint8)
            r = Image.new("RGBA", capa.size, borde[0] + (0,))
            r.putalpha(Image.fromarray(rim, "L"))
            self.img.alpha_composite(r)


def ordenar(pts):
    (x0, y0), (x1, y1) = pts
    return [(min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))]


def estrellas(lz, rnd, n=150, hasta=700):
    d = ImageDraw.Draw(lz.img)
    for _ in range(n):
        x, y = rnd.randrange(-50, W + 50), rnd.randrange(-90, hasta)
        r = rnd.choice([1, 1, 2, 3])
        d.ellipse(lz.pts([(x, y), (x + r, y + r)]), fill=(255, 255, 255, rnd.randrange(80, 230)))


def skyline(lz, rnd, base, alto_min, alto_max, color, ventanas=True, neon=True):
    c = lz.capa()
    d = ImageDraw.Draw(c)
    x = -60
    while x < W + 60:
        w, h = rnd.randrange(70, 170), rnd.randrange(alto_min, alto_max)
        top = base - h
        d.rectangle(lz.pts([(x, top), (x + w, base)]), fill=color + (255,))
        if rnd.random() < 0.25:
            d.rectangle(lz.pts([(x + w // 2 - 3, top - 70), (x + w // 2 + 3, top)]), fill=color + (255,))
            d.ellipse(lz.pts([(x + w // 2 - 7, top - 80), (x + w // 2 + 7, top - 66)]), fill=(255, 50, 60, 255))
        if ventanas:
            for wy in range(top + 18, base - 14, 24):
                for wx in range(x + 12, x + w - 14, 20):
                    if rnd.random() < 0.3:
                        col = rnd.choice([(255, 205, 120), (45, 226, 230), (255, 61, 139), (255, 240, 210)])
                        d.rectangle(lz.pts([(wx, wy), (wx + 8, wy + 11)]), fill=col + (rnd.randrange(140, 255),))
        if neon and rnd.random() < 0.3:
            col = rnd.choice([(255, 61, 139), (45, 226, 230)])
            d.line(lz.pts([(x, top), (x + w, top)]), fill=col + (255,), width=5)
        x += w + rnd.randrange(2, 24)
    lz.img.alpha_composite(c)


def palmera(lz, x, suelo, alto, rnd, color=OSCURO, inclinacion=None):
    c = lz.capa()
    d = ImageDraw.Draw(c)
    curva = alto * (inclinacion if inclinacion is not None else rnd.uniform(-0.2, 0.2))
    pts = [(x + curva * (i / 30) ** 2, suelo - (i / 30) * alto) for i in range(31)]
    for i in range(30):
        d.line(lz.pts([pts[i], pts[i + 1]]), fill=color, width=int(30 - 16 * i / 30))
    cx, cy = pts[-1]
    for k in range(9):
        ang = math.radians(-180 + k * 22.5 + rnd.uniform(-8, 8))
        largo = alto * rnd.uniform(0.3, 0.42)
        hoja = [(cx + math.cos(ang) * largo * j / 12,
                 cy + math.sin(ang) * largo * j / 12 + (j / 12) ** 2 * largo * 0.55) for j in range(13)]
        for j in range(12):
            d.line(lz.pts([hoja[j], hoja[j + 1]]), fill=color, width=max(4, int(22 * (1 - j / 12))))
            if j % 2 == 0:
                hx, hy = hoja[j]
                d.line(lz.pts([(hx, hy), (hx + 18 * math.cos(ang + 1.2), hy + 26)]), fill=color, width=5)
    lz.img.alpha_composite(c)


def persona(lz, x, pies, alto, mira=1, pose="pistola", mujer=False, gorra=False,
            borde=(255, 61, 139), brillo=None, color=OSCURO):
    """Silueta genérica original (no representa a ningún personaje concreto)."""
    c = lz.capa()
    d = ImageDraw.Draw(c)
    h = alto
    rc = h * 0.062
    cab = (x, pies - h + rc)
    hombro_y = pies - h * 0.8
    cadera_y = pies - h * 0.47
    ancho_h = h * (0.105 if mujer else 0.125)
    ancho_c = h * (0.095 if mujer else 0.085)
    if mujer:  # pelo largo
        d.polygon(lz.pts([(x - rc * 1.05, cab[1] - rc * 0.3), (x + rc * 1.05, cab[1] - rc * 0.3),
                          (x + rc * 1.0 - mira * rc * 0.6, cab[1] + rc * 3.2),
                          (x - rc * 1.0 - mira * rc * 0.6, cab[1] + rc * 3.2)]), fill=color)
    d.ellipse(lz.pts([(cab[0] - rc, cab[1] - rc), (cab[0] + rc, cab[1] + rc)]), fill=color)
    d.rectangle(lz.pts([(x - rc * 0.45, cab[1] + rc * 0.6), (x + rc * 0.45, hombro_y + 4)]), fill=color)
    if gorra:
        d.chord(lz.pts([(x - rc * 1.15, cab[1] - rc * 1.25), (x + rc * 1.15, cab[1] + rc * 0.6)]), 180, 360,
                fill=color)
        d.polygon(lz.pts([(x, cab[1] - rc * 0.35), (x + mira * rc * 2.0, cab[1] - rc * 0.15),
                          (x + mira * rc * 2.0, cab[1] + rc * 0.05), (x, cab[1] - rc * 0.05)]), fill=color)
    d.polygon(lz.pts([(x - ancho_h, hombro_y), (x + ancho_h, hombro_y),
                      (x + ancho_c, cadera_y), (x - ancho_c, cadera_y)]), fill=color)
    d.ellipse(lz.pts([(x - ancho_h - 14, hombro_y - 10), (x - ancho_h + 26, hombro_y + 30)]), fill=color)
    d.ellipse(lz.pts([(x + ancho_h - 26, hombro_y - 10), (x + ancho_h + 14, hombro_y + 30)]), fill=color)
    gp = h * 0.055
    for lado in (-1, 1):
        px = x + lado * h * 0.11
        d.polygon(lz.pts([(x + lado * 4, cadera_y - 6), (x + lado * ancho_c + lado * 4, cadera_y - 6),
                          (px + lado * gp * 0.6, pies - 10), (px - lado * gp * 0.6, pies - 10)]), fill=color)
        d.polygon(lz.pts([(px - gp * 0.7, pies - 18), (px + gp * 0.7 + mira * gp, pies - 18),
                          (px + gp * 0.7 + mira * gp * 1.2, pies), (px - gp * 0.7, pies)]), fill=color)
    ga = h * 0.045
    hx = x + mira * ancho_h * 0.8
    if pose == "pistola":
        mano = (hx + mira * h * 0.36, hombro_y + h * 0.02)
        d.line(lz.pts([(hx, hombro_y + ga * 0.6), mano]), fill=color, width=int(ga * 1.4))
        px, py = mano
        d.polygon(lz.pts([(px - mira * 6, py - 18), (px + mira * 62, py - 18), (px + mira * 62, py - 2),
                          (px + mira * 14, py - 2), (px + mira * 10, py + 30), (px - mira * 8, py + 30)]), fill=color)
        otro = x - mira * ancho_h * 0.8
        d.line(lz.pts([(otro, hombro_y + ga), (otro - mira * h * 0.02, cadera_y + h * 0.05)]),
               fill=color, width=int(ga * 1.3))
    else:
        for lado in (-1, 1):
            sx = x + lado * ancho_h * 0.85
            d.line(lz.pts([(sx, hombro_y + ga), (sx + lado * h * 0.03, cadera_y + h * 0.04)]),
                   fill=color, width=int(ga * 1.3))
    lz.poner(c, borde=(borde, (-mira, -1)) if borde else None, brillo=brillo)


def coche(lz, x, suelo, largo, color, mira=1, policia=False, deportivo=False, brillo=None):
    c = lz.capa()
    d = ImageDraw.Draw(c)
    L = largo
    alto = L * (0.24 if deportivo else 0.3)

    def P(u, v):  # u: 0..1 a lo largo (frontal = 1), v: altura sobre el suelo
        return (x + (u - 0.5) * L * mira, suelo - v)

    cuerpo = [P(0.0, alto * 0.25), P(0.02, alto * 0.62), P(0.3 if deportivo else 0.22, alto * 0.66),
              P(0.36, alto * (0.95 if deportivo else 1.0)), P(0.66, alto * (0.95 if deportivo else 1.0)),
              P(0.8, alto * 0.62), P(1.0, alto * 0.52), P(1.0, alto * 0.2), P(0.0, alto * 0.2)]
    d.polygon(lz.pts(cuerpo), fill=color + (255,))
    if policia:
        d.polygon(lz.pts([P(0.0, alto * 0.42), P(1.0, alto * 0.38), P(1.0, alto * 0.2), P(0.0, alto * 0.2)]),
                  fill=(20, 20, 28, 255))
        d.rectangle(ordenar(lz.pts([P(0.45, alto * 1.0), P(0.6, alto * 1.12)])), fill=(255, 40, 60, 255))
        d.rectangle(ordenar(lz.pts([P(0.6, alto * 1.0), P(0.75, alto * 1.12)])), fill=(40, 120, 255, 255))
    d.polygon(lz.pts([P(0.33 if deportivo else 0.26, alto * 0.66), P(0.38, alto * 0.93),
                      P(0.5, alto * 0.93), P(0.5, alto * 0.66)]), fill=(30, 40, 70, 255))
    d.polygon(lz.pts([P(0.52, alto * 0.66), P(0.52, alto * 0.93), P(0.64, alto * 0.93),
                      P(0.76, alto * 0.66)]), fill=(30, 40, 70, 255))
    for u in (0.2, 0.8):
        cx, cy = P(u, alto * 0.2)
        r = L * 0.085
        d.ellipse(lz.pts([(cx - r, cy - r), (cx + r, cy + r)]), fill=(12, 12, 16, 255))  # rueda
        d.ellipse(lz.pts([(cx - r * 0.5, cy - r * 0.5), (cx + r * 0.5, cy + r * 0.5)]), fill=(150, 150, 165, 255))
    fx, fy = P(0.99, alto * 0.45)
    d.ellipse(lz.pts([(fx - 14, fy - 9), (fx + 14, fy + 9)]), fill=(255, 245, 200, 255))
    bx, by = P(0.01, alto * 0.45)
    d.ellipse(lz.pts([(bx - 12, by - 8), (bx + 12, by + 8)]), fill=(255, 40, 40, 255))
    lz.poner(c, borde=((255, 255, 255), (0, -1)), brillo=brillo, grosor_borde=3)
    haz = lz.capa()
    ImageDraw.Draw(haz).polygon(lz.pts([(fx, fy - 6), (fx + mira * 520, fy - 70), (fx + mira * 520, fy + 90),
                                        (fx, fy + 6)]), fill=(255, 240, 190, 60))
    lz.img.alpha_composite(haz.filter(ImageFilter.GaussianBlur(12)))


def helicoptero(lz, x, y, s=1.0, foco=None):
    if foco:
        haz = lz.capa()
        ImageDraw.Draw(haz).polygon(lz.pts([(x - 10 * s, y + 40 * s), (x + 10 * s, y + 40 * s),
                                            (foco[0] + 150, foco[1]), (foco[0] - 150, foco[1])]),
                                    fill=(255, 250, 220, 70))
        lz.img.alpha_composite(haz.filter(ImageFilter.GaussianBlur(10)))
        luz = lz.capa()
        ImageDraw.Draw(luz).ellipse(lz.pts([(foco[0] - 170, foco[1] - 40), (foco[0] + 170, foco[1] + 40)]),
                                    fill=(255, 250, 220, 90))
        lz.img.alpha_composite(luz.filter(ImageFilter.GaussianBlur(16)))
    c = lz.capa()
    d = ImageDraw.Draw(c)
    d.ellipse(lz.pts([(x - 90 * s, y - 45 * s), (x + 90 * s, y + 45 * s)]), fill=OSCURO)
    d.polygon(lz.pts([(x + 60 * s, y - 15 * s), (x + 260 * s, y - 25 * s), (x + 260 * s, y - 5 * s),
                      (x + 60 * s, y + 15 * s)]), fill=OSCURO)
    d.polygon(lz.pts([(x + 240 * s, y - 70 * s), (x + 268 * s, y - 70 * s), (x + 262 * s, y - 5 * s),
                      (x + 240 * s, y - 5 * s)]), fill=OSCURO)
    d.rectangle(lz.pts([(x - 6 * s, y - 70 * s), (x + 6 * s, y - 45 * s)]), fill=OSCURO)
    d.line(lz.pts([(x - 260 * s, y - 72 * s), (x + 260 * s, y - 68 * s)]), fill=OSCURO, width=int(8 * s))
    d.line(lz.pts([(x - 80 * s, y + 70 * s), (x + 80 * s, y + 70 * s)]), fill=OSCURO, width=int(7 * s))
    for k in (-40, 40):
        d.line(lz.pts([(x + k * s, y + 40 * s), (x + k * s, y + 70 * s)]), fill=OSCURO, width=int(6 * s))
    d.polygon(lz.pts([(x - 80 * s, y - 10 * s), (x - 40 * s, y - 38 * s), (x - 10 * s, y - 38 * s),
                      (x - 10 * s, y)]), fill=(40, 60, 90, 255))
    d.ellipse(lz.pts([(x - 6, y + 38 * s), (x + 6, y + 50 * s)]), fill=(255, 40, 40, 255))
    lz.poner(c, borde=((45, 226, 230), (0, -1)), grosor_borde=3)


def yate(lz, x, linea_agua, L):
    c = lz.capa()
    d = ImageDraw.Draw(c)
    blanco = (238, 236, 245, 255)
    d.polygon(lz.pts([(x - L * 0.5, linea_agua - L * 0.1), (x + L * 0.5, linea_agua - L * 0.12),
                      (x + L * 0.36, linea_agua), (x - L * 0.44, linea_agua)]), fill=blanco)
    d.line(lz.pts([(x - L * 0.47, linea_agua - L * 0.045), (x + L * 0.42, linea_agua - L * 0.05)]),
           fill=(30, 50, 110, 255), width=10)
    d.polygon(lz.pts([(x - L * 0.36, linea_agua - L * 0.1), (x - L * 0.3, linea_agua - L * 0.19),
                      (x + L * 0.22, linea_agua - L * 0.19), (x + L * 0.33, linea_agua - L * 0.11)]), fill=blanco)
    d.polygon(lz.pts([(x - L * 0.24, linea_agua - L * 0.19), (x - L * 0.18, linea_agua - L * 0.265),
                      (x + L * 0.1, linea_agua - L * 0.265), (x + L * 0.18, linea_agua - L * 0.19)]), fill=blanco)
    for i in range(9):
        wx = x - L * 0.28 + i * L * 0.058
        d.rectangle(lz.pts([(wx, linea_agua - L * 0.165), (wx + L * 0.04, linea_agua - L * 0.13)]),
                    fill=(30, 40, 70, 255))
    for i in range(5):
        wx = x - L * 0.15 + i * L * 0.055
        d.rectangle(lz.pts([(wx, linea_agua - L * 0.245), (wx + L * 0.038, linea_agua - L * 0.215)]),
                    fill=(255, 210, 140, 255))
    d.line(lz.pts([(x - L * 0.05, linea_agua - L * 0.265), (x - L * 0.05, linea_agua - L * 0.34)]),
           fill=blanco, width=6)
    lz.poner(c, brillo=(255, 150, 120))
    # reflejo en el agua
    eje = linea_agua + lz.oy
    refl = c.crop((0, 0, WC, int(eje))).transpose(Image.FLIP_TOP_BOTTOM)
    r2 = Image.new("RGBA", c.size, (0, 0, 0, 0))
    r2.alpha_composite(refl, (0, int(eje)))
    r2.putalpha(r2.getchannel("A").point(lambda v: int(v * 0.25)))
    lz.img.alpha_composite(r2.filter(ImageFilter.GaussianBlur(4)))


def calle(lz, horizonte, color=(18, 12, 30)):
    c = lz.capa()
    d = ImageDraw.Draw(c)
    d.rectangle(lz.pts([(-60, horizonte), (W + 60, H + 100)]), fill=color + (255,))
    for i in range(10):
        t0, t1 = (i / 10) ** 2, ((i + 0.5) / 10) ** 2
        y0, y1 = horizonte + (H - horizonte) * t0, horizonte + (H - horizonte) * t1
        w0, w1 = 4 + 30 * t0, 4 + 30 * t1
        d.polygon(lz.pts([(W / 2 - w0, y0), (W / 2 + w0, y0), (W / 2 + w1, y1), (W / 2 - w1, y1)]),
                  fill=(255, 210, 63, 200))
    lz.img.alpha_composite(c)


def reflejos(lz, horizonte, rnd, n=26):
    c = lz.capa()
    d = ImageDraw.Draw(c)
    for _ in range(n):
        x = rnd.randrange(0, W)
        col = rnd.choice([(255, 61, 139), (45, 226, 230), (255, 200, 120)])
        d.rectangle(lz.pts([(x - 4, horizonte + 5), (x + 4, horizonte + rnd.randrange(150, 500))]), fill=col + (90,))
    lz.img.alpha_composite(c.filter(ImageFilter.GaussianBlur(7)))


def neblina(lz, y, alto, color=(255, 80, 140), alfa=70):
    c = lz.capa()
    ImageDraw.Draw(c).rectangle(lz.pts([(-60, y), (W + 60, y + alto)]), fill=color + (alfa,))
    lz.img.alpha_composite(c.filter(ImageFilter.GaussianBlur(60)))


def sol(lz, x, y, r):
    halo = lz.capa()
    ImageDraw.Draw(halo).ellipse(lz.pts([(x - r * 1.6, y - r * 1.6), (x + r * 1.6, y + r * 1.6)]),
                                 fill=(255, 120, 120, 120))
    lz.img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(80)))
    c = lz.capa()
    d = ImageDraw.Draw(c)
    d.ellipse(lz.pts([(x - r, y - r), (x + r, y + r)]), fill=(255, 210, 110, 255))
    for i in range(6):
        fy = y + r * 0.15 + i * r * 0.15
        d.rectangle(lz.pts([(x - r, fy), (x + r, fy + 4 + i * 3)]), fill=(0, 0, 0, 0))
    lz.img.alpha_composite(c)


NOCHE = [(0, (6, 4, 22)), (0.3, (40, 14, 80)), (0.5, (150, 30, 110)), (0.56, (255, 100, 90)), (1, (255, 100, 90))]
ATARDECER = [(0, (40, 10, 70)), (0.25, (130, 30, 110)), (0.45, (255, 90, 100)), (0.56, (255, 180, 90)),
             (1, (255, 180, 90))]


def ilus_ciudad_heli(rnd):
    lz = Lienzo(degradado(NOCHE))
    estrellas(lz, rnd)
    skyline(lz, rnd, 1080, 200, 600, (36, 14, 64))
    skyline(lz, rnd, 1080, 120, 420, (20, 8, 40))
    calle(lz, 1080)
    reflejos(lz, 1080, rnd)
    helicoptero(lz, 640, 330, 1.0, foco=(420, 1250))
    coche(lz, 330, 1300, 520, (235, 235, 240), mira=1, policia=True, brillo=(255, 60, 80))
    palmera(lz, 980, 1500, 900, rnd, inclinacion=-0.15)
    palmera(lz, 60, 1560, 1000, rnd, inclinacion=0.12)
    return lz.img


def ilus_poli(rnd):
    lz = Lienzo(degradado(NOCHE))
    estrellas(lz, rnd, 100)
    skyline(lz, rnd, 1040, 250, 700, (34, 12, 60))
    calle(lz, 1040)
    reflejos(lz, 1040, rnd)
    neblina(lz, 950, 160, (255, 60, 120), 80)
    coche(lz, 820, 1210, 560, (235, 235, 240), mira=-1, policia=True, brillo=(60, 100, 255))
    persona(lz, 300, 1240, 700, mira=1, pose="pistola", borde=(45, 226, 230), brillo=(45, 226, 230))
    palmera(lz, 1020, 1600, 1150, rnd, inclinacion=-0.18)
    return lz.img


def ilus_traicion(rnd):
    lz = Lienzo(degradado(ATARDECER))
    sol(lz, 540, 820, 300)
    skyline(lz, rnd, 1060, 120, 380, (90, 24, 80), ventanas=False, neon=False)
    skyline(lz, rnd, 1060, 60, 240, (60, 14, 60), ventanas=True, neon=False)
    c = lz.capa()
    d = ImageDraw.Draw(c)
    d.rectangle(lz.pts([(-60, 1060), (W + 60, H + 100)]), fill=(24, 8, 30, 255))
    d.rectangle(lz.pts([(-60, 1060), (W + 60, 1080)]), fill=(255, 120, 120, 255))
    lz.img.alpha_composite(c)
    persona(lz, 150, 1260, 680, mira=1, pose="pistola", borde=(45, 226, 230), brillo=(45, 226, 230))
    persona(lz, 930, 1260, 650, mira=-1, pose="pistola", mujer=True, borde=(255, 61, 139), brillo=(255, 61, 139))
    return lz.img


def ilus_tercero(rnd):
    lz = Lienzo(degradado([(0, (4, 4, 14)), (0.4, (24, 10, 50)), (0.6, (60, 20, 80)), (1, (30, 10, 40))]))
    skyline(lz, rnd, 1100, 400, 900, (18, 8, 34))
    calle(lz, 1100, (14, 10, 24))
    neblina(lz, 1000, 240, (120, 80, 200), 90)
    persona(lz, 250, 1280, 660, mira=1, pose="pistola", borde=(45, 226, 230), brillo=(45, 226, 230))
    persona(lz, 520, 1270, 620, mira=1, pose="pie", mujer=True, borde=(255, 61, 139), brillo=(255, 61, 139))
    persona(lz, 830, 1290, 700, mira=-1, pose="pie", gorra=True, borde=(255, 210, 63), color=(4, 2, 8, 255))
    return lz.img


def ilus_online(rnd):
    lz = Lienzo(degradado(NOCHE))
    estrellas(lz, rnd, 80)
    skyline(lz, rnd, 1080, 300, 750, (30, 10, 56))
    c = lz.capa()
    d = ImageDraw.Draw(c)
    d.rounded_rectangle(lz.pts([(330, 380), (750, 600)]), radius=30, outline=(45, 226, 230, 255), width=10)
    d.text(lz.p(540, 495), "$$$", font=fuente(170), fill=(255, 210, 63, 255), anchor="mm")
    lz.img.alpha_composite(c.filter(ImageFilter.GaussianBlur(10)))
    lz.img.alpha_composite(c)
    calle(lz, 1080)
    reflejos(lz, 1080, rnd, 40)
    coche(lz, 250, 1230, 470, (255, 61, 139), mira=1, deportivo=True, brillo=(255, 61, 139))
    coche(lz, 800, 1260, 520, (255, 190, 40), mira=-1, deportivo=True, brillo=(255, 190, 40))
    coche(lz, 520, 1420, 600, (45, 200, 230), mira=1, deportivo=True, brillo=(45, 226, 230))
    return lz.img


def ilus_yate(rnd):
    lz = Lienzo(degradado(ATARDECER))
    sol(lz, 700, 860, 230)
    c = lz.capa()
    d = ImageDraw.Draw(c)
    d.rectangle(lz.pts([(-60, 1000), (W + 60, H + 100)]), fill=(40, 20, 80, 255))
    for i in range(30):
        y = 1010 + i * i * 1.0
        if y > H:
            break
        d.rectangle(lz.pts([(470 + i * 4, y), (930 - i * 4, y + 3 + i // 5)]),
                    fill=(255, 170, 110, max(30, 200 - i * 6)))
    lz.img.alpha_composite(c)
    c = lz.capa()
    d = ImageDraw.Draw(c)
    d.rectangle(lz.pts([(-40, 820), (330, 1000)]), fill=(240, 220, 225, 255))
    d.rectangle(lz.pts([(-40, 720), (220, 820)]), fill=(240, 220, 225, 255))
    for i in range(5):
        d.rectangle(lz.pts([(10 + i * 64, 860), (50 + i * 64, 950)]), fill=(255, 200, 130, 255))
    for i in range(3):
        d.rectangle(lz.pts([(10 + i * 64, 750), (50 + i * 64, 800)]), fill=(255, 200, 130, 255))
    d.rectangle(lz.pts([(-40, 990), (420, 1010)]), fill=(120, 80, 90, 255))
    lz.img.alpha_composite(c)
    yate(lz, 680, 1060, 820)
    palmera(lz, 380, 1010, 520, rnd, inclinacion=0.2)
    palmera(lz, 60, 1600, 1200, rnd, inclinacion=0.15)
    return lz.img


ILUSTRACIONES = {"ciudad_heli": ilus_ciudad_heli, "poli": ilus_poli, "traicion": ilus_traicion,
                 "tercero": ilus_tercero, "online": ilus_online, "yate": ilus_yate}


def cargar_fondo(e, semilla):
    for ext in ("jpg", "jpeg", "png", "webp"):
        ruta = os.path.join(RAIZ, "imagenes", f"{e['id']}.{ext}")
        if os.path.exists(ruta):
            img = Image.open(ruta).convert("RGB")
            esc = max(WC / img.width, HC / img.height)
            img = img.resize((int(img.width * esc) + 1, int(img.height * esc) + 1), Image.LANCZOS)
            x, y = (img.width - WC) // 2, (img.height - HC) // 2
            return img.crop((x, y, x + WC, y + HC)).convert("RGBA")
    return ILUSTRACIONES[e.get("ilustracion", "ciudad_heli")](random.Random(semilla))


# --------------------------------------------------------------------------
# efectos de acción
# --------------------------------------------------------------------------

_comic = {}


def texto_comic(txt, tam):
    if (txt, tam) not in _comic:
        _comic[(txt, tam)] = texto_con_estilo(txt, fuente(tam), (255, 225, 60, 255), borde=12,
                                              color_borde=(20, 6, 20), brillo=(255, 80, 40))
    return _comic[(txt, tam)]


class Efecto:
    t0 = 0

    def sacudida(self, t):
        return 0

    def destello(self, t):
        return 0

    def dibujar(self, frame, t, mapa):
        pass

    def encima(self, frame, t):
        pass


class Explosion(Efecto):
    def __init__(self, ev, semilla):
        rnd = random.Random(semilla)
        self.t0, self.x, self.y = ev["t"], ev["x"], ev["y"]
        self.s = ev.get("escala", 1.0)
        self.texto = ev.get("texto")
        self.bolas = [(rnd.gauss(0, 70), rnd.gauss(0, 50), rnd.uniform(90, 190), rnd.uniform(0, 0.12))
                      for _ in range(16)]
        self.humo = [(rnd.gauss(0, 120), rnd.gauss(-40, 60), rnd.uniform(110, 210), rnd.uniform(0.15, 0.35))
                     for _ in range(12)]
        self.chispas = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(500, 1500), rnd.uniform(0.4, 0.9))
                        for _ in range(46)]
        self.restos = [(rnd.uniform(-2.6, -0.5), rnd.uniform(500, 1100), rnd.uniform(8, 22)) for _ in range(12)]

    def sacudida(self, t):
        a = t - self.t0
        return 0 if a < 0 else 46 * self.s * max(0, 1 - a / 0.6)

    def destello(self, t):
        a = t - self.t0
        return 0 if a < 0 else max(0, 1 - a / 0.14) * min(1, self.s)

    def dibujar(self, frame, t, mapa):
        a = t - self.t0
        if a < 0 or a > 1.6:
            return
        s = self.s
        L = int(1100 * s)
        loc = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        d = ImageDraw.Draw(loc)
        cx = cy = L / 2
        for dx, dy, r, ret in self.humo:
            b = a - ret
            if b < 0:
                continue
            rr = r * s * (0.5 + b * 1.1)
            al = int(200 * clamp(1 - b / 1.3))
            px, py = cx + dx * s * (0.6 + b), cy + dy * s - b * 160 * s
            d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=(35, 25, 35, al))
        for dx, dy, r, ret in self.bolas:
            b = a - ret
            if b < 0:
                continue
            g = ease_out_cubic(b / 0.3)
            rr = r * s * (0.25 + 0.95 * g) * (1 + 0.25 * b)
            if b < 0.07:
                col = (255, 255, 235)
            elif b < 0.22:
                col = mezclar((255, 240, 150), (255, 170, 40), (b - 0.07) / 0.15)
            elif b < 0.5:
                col = mezclar((255, 170, 40), (230, 70, 20), (b - 0.22) / 0.28)
            else:
                col = mezclar((230, 70, 20), (60, 30, 30), (b - 0.5) / 0.5)
            al = int(255 * clamp(1 - (b - 0.35) / 0.65))
            px, py = cx + dx * s * (0.4 + g), cy + dy * s * (0.4 + g) - b * 110 * s
            oscuro = mezclar(col, (120, 20, 10), 0.55)
            d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=oscuro + (al,))
            r2 = rr * 0.72
            d.ellipse((px - r2 - rr * 0.08, py - r2 - rr * 0.12, px + r2 - rr * 0.08, py + r2 - rr * 0.12),
                      fill=col + (al,))
            if b < 0.4:
                r3 = rr * 0.38
                nucleo = mezclar((255, 255, 230), col, b / 0.4)
                d.ellipse((px - r3, py - r3 - rr * 0.15, px + r3, py + r3 - rr * 0.15), fill=nucleo + (al,))
        loc = loc.filter(ImageFilter.GaussianBlur(3 * s))
        d = ImageDraw.Draw(loc)
        if a < 0.45:
            r = 60 + 620 * s * ease_out_cubic(a / 0.45)
            al = int(220 * (1 - a / 0.45))
            d.ellipse((cx - r, cy - r * 0.55, cx + r, cy + r * 0.55), outline=(255, 235, 190, al), width=int(14 * s))
        for ang, v, vida in self.chispas:
            if a > vida:
                continue
            px = cx + math.cos(ang) * v * a * s
            py = cy + math.sin(ang) * v * a * s + 900 * a * a * s
            qx = px - math.cos(ang) * v * 0.03 * s
            qy = py - (math.sin(ang) * v + 1800 * a) * 0.03 * s
            d.line((qx, qy, px, py), fill=(255, 220, 120, int(255 * (1 - a / vida))), width=max(2, int(4 * s)))
        for ang, v, tam in self.restos:
            px = cx + math.cos(ang) * v * a * s
            py = cy + math.sin(ang) * v * a * s + 1400 * a * a * s
            r = tam * s * 0.6
            d.polygon([(px - r, py), (px, py - r * 0.7), (px + r, py + r * 0.3), (px - r * 0.2, py + r)],
                      fill=(15, 10, 15, int(255 * clamp(1.4 - a))))
        sx, sy = mapa(self.x, self.y)
        frame.alpha_composite(loc, (int(sx - L / 2), int(sy - L / 2)))
        if self.texto and 0.02 < a < 0.75:
            pegar_centrado(frame, texto_comic(self.texto, 150), sx + 40, sy - 300 * s,
                           escala=ease_out_back(a / 0.18, 3), angulo=-10, alfa=clamp((0.75 - a) / 0.15))


def agujero_bala(semilla):
    rnd = random.Random(semilla)
    S = 260
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S / 2
    for _ in range(9):
        ang = rnd.uniform(0, 2 * math.pi)
        x, y, largo = c, c, rnd.uniform(60, 125)
        for k in range(4):
            ang += rnd.uniform(-0.35, 0.35)
            nx, ny = x + math.cos(ang) * largo / 4, y + math.sin(ang) * largo / 4
            d.line((x, y, nx, ny), fill=(255, 255, 255, 210 - k * 35), width=max(1, 4 - k))
            x, y = nx, ny
    for r in (44, 70):
        d.arc((c - r, c - r, c + r, c + r), rnd.randrange(0, 90), rnd.randrange(200, 330),
              fill=(255, 255, 255, 120), width=2)
    d.ellipse((c - 22, c - 22, c + 22, c + 22), fill=(230, 230, 240, 230))
    d.ellipse((c - 15, c - 15, c + 15, c + 15), fill=(5, 5, 10, 255))
    return img


class Disparo(Efecto):
    def __init__(self, ev, semilla):
        self.t0, self.x, self.y = ev["t"], ev["x"], ev["y"]
        self.ang = math.radians(ev.get("ang", 0))
        self.agujero = ev.get("agujero")
        self.texto = ev.get("texto")
        self.img_agujero = agujero_bala(semilla) if self.agujero else None

    def sacudida(self, t):
        a = t - self.t0
        return 0 if a < 0 else 14 * max(0, 1 - a / 0.15)

    def destello(self, t):
        a = t - self.t0
        return 0 if a < 0 else 0.25 * max(0, 1 - a / 0.06)

    def dibujar(self, frame, t, mapa):
        a = t - self.t0
        if a < 0:
            return
        sx, sy = mapa(self.x, self.y)
        dx, dy = math.cos(self.ang), math.sin(self.ang)
        if a < 0.07:  # fogonazo
            loc = Image.new("RGBA", (420, 420), (0, 0, 0, 0))
            dl = ImageDraw.Draw(loc)
            c = 210
            mx, my = c + 60 * dx, c + 60 * dy
            dl.ellipse((mx - 120, my - 120, mx + 120, my + 120), fill=(255, 180, 60, 140))
            loc = loc.filter(ImageFilter.GaussianBlur(20))
            dl = ImageDraw.Draw(loc)
            pts = []
            for k in range(16):
                ang = self.ang + k * math.pi / 8
                r = (150 if k % 2 == 0 else 45) * (1 - a / 0.1)
                if k == 0:
                    r *= 1.6
                pts.append((mx + math.cos(ang) * r, my + math.sin(ang) * r))
            dl.polygon(pts, fill=(255, 230, 140, 255))
            dl.ellipse((mx - 30, my - 30, mx + 30, my + 30), fill=(255, 255, 240, 255))
            frame.alpha_composite(loc, (int(sx - c), int(sy - c)))
        if a < 0.14:  # trazadora
            d = ImageDraw.Draw(frame)
            p0 = (sx + dx * a * 9000, sy + dy * a * 9000)
            p1 = (p0[0] - dx * 260, p0[1] - dy * 260)
            d.line((p1, p0), fill=(255, 200, 90, 160), width=12)
            d.line((p1, p0), fill=(255, 250, 220, 255), width=4)
        if 0.02 < a < 0.5 and self.texto:
            pegar_centrado(frame, texto_comic(self.texto, 110), sx + dx * 140, sy - 150,
                           escala=ease_out_back(a / 0.12, 3), angulo=8, alfa=clamp((0.5 - a) / 0.12))

    def encima(self, frame, t):
        if self.agujero and t >= self.t0 + 0.08:
            p = 1.3 - 0.3 * ease_out_cubic((t - self.t0 - 0.08) / 0.1)
            pegar_centrado(frame, self.img_agujero, self.agujero[0], self.agujero[1], escala=p)


class Dinero(Efecto):
    def __init__(self, ev, semilla):
        rnd = random.Random(semilla)
        self.t0 = ev.get("t", 0)
        self.billetes = [(rnd.uniform(-50, W + 50), rnd.uniform(-1400, -50), rnd.uniform(300, 520),
                          rnd.uniform(0, 6.28), rnd.uniform(2, 5), rnd.uniform(0.7, 1.2)) for _ in range(34)]
        b = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(b)
        d.rectangle((0, 0, 119, 59), fill=(90, 200, 120, 255), outline=(30, 90, 50, 255), width=4)
        d.ellipse((42, 12, 78, 48), outline=(30, 90, 50, 255), width=4)
        d.text((60, 30), "$", font=fuente(30), fill=(30, 90, 50, 255), anchor="mm")
        self.img = b

    def dibujar(self, frame, t, mapa):
        a = t - self.t0
        if a < 0:
            return
        for x, y, v, fase, giro, esc in self.billetes:
            py = y + v * a
            if py > H + 80 or py < -80:
                continue
            px = x + math.sin(fase + a * giro) * 60
            ancho = abs(math.cos(fase + a * giro * 1.3))
            img = self.img.resize((max(4, int(120 * esc * (0.3 + 0.7 * ancho))), int(60 * esc)))
            pegar_centrado(frame, img, px, py, angulo=math.degrees(math.sin(fase + a * giro)) * 0.6)


class Sirena(Efecto):
    def __init__(self, ev, semilla):
        pass

    def dibujar(self, frame, t, mapa):
        fase = int(t * 6) % 2
        col = (255, 30, 60) if fase else (40, 90, 255)
        capa = Image.new("RGBA", (W // 4, H // 4), (0, 0, 0, 0))
        x = W // 4 if fase else 0
        ImageDraw.Draw(capa).ellipse((x - 125, 100, x + 125, 375), fill=col + (110,))
        capa = capa.filter(ImageFilter.GaussianBlur(30)).resize((W, H), Image.BILINEAR)
        frame.alpha_composite(capa)


class Revelar(Efecto):
    def __init__(self, ev, semilla):
        self.t0, self.x, self.y = ev["t"], ev["x"], ev["y"]

    def dibujar(self, frame, t, mapa):
        a = t - self.t0
        if a < 0:
            return
        sx, sy = mapa(self.x, self.y)
        pulso = 1 + 0.06 * math.sin(a * 10)
        pegar_centrado(frame, texto_comic("?", 300), sx, sy - 330, escala=ease_out_back(a / 0.3) * pulso, angulo=-6)


FX = {"explosion": Explosion, "disparo": Disparo, "dinero": Dinero, "sirena": Sirena, "revelar": Revelar}


# --------------------------------------------------------------------------
# subtítulos
# --------------------------------------------------------------------------

VOZ_RETARDO = 0.06  # la voz entra justo después del corte


def leer_wav(ruta):
    with wave.open(ruta, "rb") as w:
        n, canales, sr = w.getnframes(), w.getnchannels(), w.getframerate()
        datos = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768
    if canales > 1:
        datos = datos.reshape(-1, canales).mean(axis=1)
    if sr != 44100:
        datos = np.interp(np.arange(0, len(datos), sr / 44100), np.arange(len(datos)), datos)
    return datos


def duracion_voz(e):
    ruta = e.get("audio_voz")
    if not ruta:
        return None
    ruta = os.path.join(RAIZ, ruta)
    if not os.path.exists(ruta):
        return None
    with wave.open(ruta, "rb") as w:
        return w.getnframes() / w.getframerate()


def tiempos_palabras(voz, inicio, dur, desde_inicio=False):
    palabras = voz.split()
    pesos = [len(p) + 2 + (5 if p.endswith(("...", ".", "?", ":", "!")) else 0) for p in palabras]
    total = sum(pesos)
    arranque = 0.0 if (inicio == 0 or desde_inicio) else 0.12
    t, salida = inicio + arranque, []
    util = dur - 0.15 - arranque
    for p, w in zip(palabras, pesos):
        d = util * w / total
        salida.append((p, t, t + d))
        t += d
    return salida


def bloques_subtitulo(palabras, max_palabras=3):
    bloques, actual = [], []
    for p in palabras:
        if p[0].startswith("¿") and actual:
            bloques.append(actual)
            actual = []
        actual.append(p)
        if len(actual) >= max_palabras or p[0].endswith((".", "?", ":", ",", "...")):
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return bloques


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

class Render:
    def __init__(self, guion):
        self.g = guion
        self.fps = guion["fps"]
        col = guion["colores"]
        self.acento, self.rosa = hexrgb(col["acento"]), hexrgb(col["rosa"])
        self.cian, self.blanco = hexrgb(col["cian"]), hexrgb(col["texto"])
        t = 0.0
        self.escenas = []
        for i, e in enumerate(guion["escenas"]):
            e = dict(e)
            e["inicio"], e["fin"], e["idx"] = t, t + e["duracion"], i
            e["fondo"] = cargar_fondo(e, 100 + i)
            e["fx_obj"] = [FX[f["tipo"]](f, 1000 + i * 50 + k) for k, f in enumerate(e.get("fx", []))]
            self._preparar(e)
            self.escenas.append(e)
            t += e["duracion"]
        self.total = t
        palabras = []
        for e in self.escenas:
            dv = duracion_voz(e)
            if dv:
                ini = e["inicio"] + (0 if e["idx"] == 0 else VOZ_RETARDO)
                palabras.extend(tiempos_palabras(e["voz"], ini, dv + 0.15, desde_inicio=True))
            else:
                palabras.extend(tiempos_palabras(e["voz"], e["inicio"], e["duracion"]))
        self.bloques = bloques_subtitulo(palabras)
        self.grano = [self._grano(k) for k in range(3)]
        self.vineta = self._vineta()
        self.degradado_inf = self._degradado_inferior()

    def _grano(self, k):
        n = np.random.default_rng(k).integers(0, 255, (H // 2, W // 2), dtype=np.uint8)
        g = Image.fromarray(n, "L").resize((W, H), Image.NEAREST)
        a = Image.new("RGBA", (W, H), (255, 255, 255, 0))
        a.putalpha(g.point(lambda v: 16 if v > 205 else 0))
        return a

    def _vineta(self):
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        dist = np.sqrt(((xx - W / 2) / (W * 0.72)) ** 2 + ((yy - H / 2) / (H * 0.6)) ** 2)
        a = np.clip((dist - 0.6) * 320, 0, 210).astype(np.uint8)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        img.putalpha(Image.fromarray(a, "L"))
        return img

    def _degradado_inferior(self):
        y = np.linspace(0, 1, H)
        a = np.clip((y - 0.55) / 0.25, 0, 1) * 200
        a = np.repeat(a[:, None], W, 1).astype(np.uint8)
        img = Image.new("RGBA", (W, H), (6, 2, 14, 0))
        img.putalpha(Image.fromarray(a, "L"))
        return img

    def _preparar(self, e):
        tit = e["titular"]
        f = ajustar_fuente(tit, W - 110, 150, borde=12)
        e["capa_tit"] = texto_con_estilo(tit, f, self.acento + (255,), borde=12, color_borde=(16, 4, 24),
                                         brillo=self.rosa)
        e["capa_det"] = None
        if e.get("detalle"):
            f = ajustar_fuente(e["detalle"], W - 160, 56, borde=6)
            e["capa_det"] = texto_con_estilo(e["detalle"], f, self.blanco + (255,), borde=6, color_borde=(10, 4, 20))
        etiqueta = e.get("etiqueta") or (f"TEORÍA #{e['numero']}" if e.get("numero") else None)
        e["capa_eti"] = None
        if etiqueta:
            fe = fuente(46)
            bb = fe.getbbox(etiqueta)
            img = Image.new("RGBA", (bb[2] + 70, 84), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((0, 0, img.width - 1, 83), radius=16, fill=self.rosa + (255,))
            d.text((35, 42 - (bb[3] + bb[1]) / 2), etiqueta, font=fe, fill=(255, 255, 255, 255))
            e["capa_eti"] = img
        e["capa_preg"] = self._sticker(e["pregunta"]) if e.get("pregunta") else None

    def _sticker(self, pregunta):
        f = ajustar_fuente(pregunta, 700, 76)
        bb = f.getbbox(pregunta)
        ancho = max(bb[2] + 100, 760)
        alto = 340
        img = Image.new("RGBA", (ancho + 40, alto + 50), (0, 0, 0, 0))
        sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sombra).rounded_rectangle((26, 30, ancho + 26, alto + 30), radius=44, fill=(0, 0, 0, 150))
        img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(10)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((20, 20, ancho + 20, alto + 20), radius=44, fill=(255, 255, 255, 255))
        d.text((20 + ancho / 2, 100), pregunta, font=f, fill=(15, 10, 25, 255), anchor="mm")
        fb = fuente(64)
        mitad = ancho / 2
        for k, (txt, col) in enumerate((("SÍ", (40, 200, 110)), ("NO", (255, 61, 90)))):
            x0 = 20 + 40 + k * mitad
            x1 = 20 + mitad - 20 + k * (mitad - 20)
            d.rounded_rectangle((x0, 180, x1, 310), radius=30, fill=col + (255,))
            d.text(((x0 + x1) / 2, 245), txt, font=fb, fill=(255, 255, 255, 255), anchor="mm")
        return img

    def escena_en(self, t):
        for e in self.escenas:
            if t < e["fin"]:
                return e
        return self.escenas[-1]

    def frame(self, n):
        t = n / self.fps
        e = self.escena_en(t)
        lt = t - e["inicio"]
        fx = e["fx_obj"]
        # cámara: zoom lento + paneo + sacudida
        sac = sum(f.sacudida(lt) for f in fx)
        if lt < TRANS and e["idx"] > 0:
            sac += 30 * (1 - lt / TRANS)
        k = ease_in_out(lt / e["duracion"])
        s = 1.1 - 0.075 * k
        cx = WC / 2 + (1 if e["idx"] % 2 else -1) * 30 * (k - 0.5)
        cy = HC / 2 - 20 * k
        ox = clamp(cx - W * s / 2 + math.sin(t * 73) * sac, 0, WC - W * s)
        oy = clamp(cy - H * s / 2 + math.cos(t * 61) * sac, 0, HC - H * s)
        frame = e["fondo"].crop((int(ox), int(oy), int(ox + W * s), int(oy + H * s))).resize((W, H), Image.BILINEAR)

        def mapa(x, y):
            return ((x + MARGEN[0] - ox) / s, (y + MARGEN[1] - oy) / s)

        for f in fx:
            f.dibujar(frame, lt, mapa)
        frame.alpha_composite(self.degradado_inf)
        frame.alpha_composite(self.vineta)
        self._textos(frame, e, lt)
        for f in fx:
            f.encima(frame, lt)
        self._sticker_preg(frame, e, lt)
        self._subtitulos(frame, t)
        d = ImageDraw.Draw(frame)
        d.rectangle((0, 0, W, 12), fill=(0, 0, 0, 140))
        d.rectangle((0, 0, int(W * t / self.total), 12), fill=self.acento + (255,))
        frame.alpha_composite(self.grano[n % 3])
        rgb = frame.convert("RGB")
        flash = sum(f.destello(lt) for f in fx)
        glitch = 0.0
        if e["idx"] > 0 and lt < TRANS:
            glitch = 1 - lt / TRANS
            flash += 0.7 * glitch ** 2
        if flash > 0.01 or glitch > 0:
            arr = np.asarray(rgb).astype(np.int16)
            if glitch > 0:
                off = int(34 * glitch)
                arr[:, :, 0] = np.roll(arr[:, :, 0], off, axis=1)
                arr[:, :, 2] = np.roll(arr[:, :, 2], -off, axis=1)
            arr = arr + int(150 * clamp(flash))
            rgb = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        return rgb.tobytes()

    def _textos(self, frame, e, lt):
        sal = clamp((e["duracion"] - lt) / 0.15)
        if e["capa_eti"] is not None:
            p = 1.0 if e["idx"] == 0 else ease_out_back((lt - 0.05) / 0.3)
            pegar_centrado(frame, e["capa_eti"], W / 2, 1090, escala=p, alfa=sal, angulo=3)
        a = lt - 0.12 if e["idx"] > 0 else lt
        if a >= 0:  # titular: golpe desde grande
            p = ease_out_cubic(a / 0.22)
            esc = 1.25 - 0.25 * p if e["idx"] == 0 else 1.7 - 0.7 * p
            pulso = 1 + 0.03 * max(0, math.cos(2 * math.pi * lt * self.g["bpm"] / 60)) ** 10
            alfa = 1.0 if e["idx"] == 0 else clamp(a / 0.08)
            pegar_centrado(frame, e["capa_tit"], W / 2, 1220, escala=esc * pulso, alfa=alfa * sal, angulo=-2)
        if e["capa_det"] is not None:
            p = 1.0 if e["idx"] == 0 else ease_out_cubic((lt - 0.35) / 0.3)
            pegar_centrado(frame, e["capa_det"], W / 2, 1345 + (1 - p) * 60, alfa=p * sal)

    def _sticker_preg(self, frame, e, lt):
        if e["capa_preg"] is None:
            return
        a = lt - (e["duracion"] - 1.45)
        if a < 0:
            return
        p = ease_out_back(a / 0.3, 2.6)
        bamboleo = math.sin(a * 7) * 3 * clamp(1 - a)
        pegar_centrado(frame, e["capa_preg"], W / 2, 640, escala=p, angulo=-4 + bamboleo)
        if a > 0.55:  # "toque" sobre el botón SÍ
            b = (a - 0.55) % 0.9
            r = 30 + 120 * ease_out_cubic(b / 0.5)
            al = int(200 * clamp(1 - b / 0.5))
            x, y = W / 2 - e["capa_preg"].width / 4 + 10, 640 + 95
            ImageDraw.Draw(frame).ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, al), width=8)

    def _subtitulos(self, frame, t):
        bloque = None
        for b in self.bloques:
            if b[0][1] - 0.03 <= t < b[-1][2] + 0.05:
                bloque = b
        if bloque is None:
            return
        f = fuente(70)
        palabras = [p.replace("...", "").upper() for p, _, _ in bloque]
        espacio = 20
        anchos = [f.getbbox(p, stroke_width=8)[2] for p in palabras]
        total = sum(anchos) * 1.12 + espacio * (len(palabras) - 1)
        escala = min(1.0, (W - 120) / total)
        aparicion = 1.0 if bloque[0][1] == 0 else 0.85 + 0.15 * ease_out_back((t - bloque[0][1]) / 0.15, 2.5)
        activas = [a <= t < b + 0.04 for _, a, b in bloque]
        escalas = [escala * aparicion * (1.12 if ac else 1.0) for ac in activas]
        total = sum(w * es for w, es in zip(anchos, escalas)) + espacio * escala * (len(palabras) - 1)
        x = (W - total) / 2
        for (p, a, b), txt, w, ac, es in zip(bloque, palabras, anchos, activas, escalas):
            col = self.acento if ac else self.blanco
            capa = texto_con_estilo(txt, f, col + (255,), borde=8, color_borde=(0, 0, 0))
            pegar_centrado(frame, capa, x + w * es / 2, 1500 - (6 if ac else 0), escala=es)
            x += w * es + espacio * escala


# --------------------------------------------------------------------------
# audio: beat original + efectos de acción
# --------------------------------------------------------------------------

SR = 44100


def nota(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def filtro_lp(x, corte):
    k = max(1, int(SR / corte / 2))
    return np.convolve(x, np.ones(k) / k, mode="same")


def pegar(buf, a, senal, g=1.0):
    a = int(a)
    if a >= len(buf) or a + len(senal) <= 0:
        return
    if a < 0:
        senal, a = senal[-a:], 0
    L = min(len(senal), len(buf) - a)
    buf[a:a + L] += senal[:L] * g


def sfx_disparo(rng):
    L = int(0.45 * SR)
    tt = np.arange(L) / SR
    ruido = rng.standard_normal(L)
    crack = (ruido - filtro_lp(ruido, 2500)) * np.exp(-tt * 60)
    cuerpo = filtro_lp(ruido, 1200) * np.exp(-tt * 14) * 1.4
    golpe = np.sin(2 * math.pi * (70 * tt + 60 * (1 - np.exp(-tt * 30)))) * np.exp(-tt * 18)
    return crack * 1.2 + cuerpo + golpe * 0.9


def sfx_explosion(rng, dur=2.2):
    L = int(dur * SR)
    tt = np.arange(L) / SR
    ruido = rng.standard_normal(L)
    estruendo = filtro_lp(filtro_lp(ruido, 400), 400) * np.exp(-tt * 2.2) * 3.5
    crujido = (ruido - filtro_lp(ruido, 3000)) * np.exp(-tt * 10) * 0.5
    boom = np.sin(2 * math.pi * (32 * tt + 25 * (1 - np.exp(-tt * 6)))) * np.exp(-tt * 3) * 1.4
    return (estruendo + crujido + boom) * np.minimum(1, tt / 0.004)


def sfx_whoosh(rng, dur=0.4):
    L = int(dur * SR)
    tt = np.arange(L) / SR
    ruido = rng.standard_normal(L)
    mezcla = filtro_lp(ruido, 900) * (1 - tt / dur) + filtro_lp(ruido, 3500) * (tt / dur)
    return mezcla * np.sin(np.pi * tt / dur) ** 2 * 0.9


def sfx_pop():
    L = int(0.18 * SR)
    tt = np.arange(L) / SR
    return np.sin(2 * math.pi * (500 * tt + 18000 * tt * tt)) * np.exp(-tt * 22) * 0.5


def sfx_caja():
    L = int(0.5 * SR)
    tt = np.arange(L) / SR
    return (np.sin(2 * math.pi * 2100 * tt) + 0.6 * np.sin(2 * math.pi * 3150 * tt)) * np.exp(-tt * 9) * 0.25


def musica(total, bpm):
    N = int(total * SR) + SR
    out = np.zeros(N)
    beat = 60 / bpm
    rng = np.random.default_rng(5)
    raices = [45, 45, 41, 43]
    compas = beat * 4
    n_comp = int(total / compas) + 2
    for c in range(n_comp):  # 808 con glide
        for paso, dur in ((0, 1.5), (1.75, 0.75), (2.5, 1.5)):
            L = int(dur * beat * SR)
            tt = np.arange(L) / SR
            f = nota(raices[c % 4] - 12)
            fase = 2 * math.pi * np.cumsum(f * (1 + 0.5 * np.exp(-tt * 30))) / SR
            pegar(out, (c * compas + paso * beat) * SR, np.tanh(np.sin(fase) * 2.2) * np.exp(-tt * 1.6), 0.42)
    for b in range(n_comp * 4):
        a = int(b * beat * SR)
        if b % 4 == 0 or b % 8 == 6:  # bombo
            L = int(0.3 * SR)
            tt = np.arange(L) / SR
            pegar(out, a, np.sin(2 * math.pi * (50 * tt + 4 * (1 - np.exp(-tt * 30)))) * np.exp(-tt * 10), 0.6)
        if b % 4 == 2:  # palmada
            L = int(0.25 * SR)
            tt = np.arange(L) / SR
            r = rng.standard_normal(L)
            palm = (r - filtro_lp(r, 1500)) * np.exp(-tt * 18)
            pegar(out, a, palm, 0.55)
            pegar(out, a + int(0.012 * SR), palm, 0.3)
        sub = 4 if b % 8 == 7 else 2  # charles con redobles
        for k in range(sub):
            L = int(0.04 * SR)
            r = rng.standard_normal(L)
            pegar(out, a + int(k * beat / sub * SR), (r - filtro_lp(r, 6000)) * np.exp(-np.arange(L) / SR * 90), 0.16)
    escala = [69, 72, 76, 74, 72, 71, 69, 64]
    for i in range(int(total / (beat / 2))):  # campana oscura
        if i % 3 == 2:
            continue
        L = int(0.5 * SR)
        tt = np.arange(L) / SR
        f = nota(escala[i % len(escala)])
        s = (np.sin(2 * math.pi * f * tt) + 0.4 * np.sin(2 * math.pi * f * 2.01 * tt)) * np.exp(-tt * 6)
        pegar(out, i * beat / 2 * SR, s, 0.07)
    return out


def escribir_audio(render, ruta):
    total = render.total
    N = int(total * SR) + SR
    rng = np.random.default_rng(11)
    mus = musica(total, render.g.get("bpm", 140))[:N] * 0.5
    sfx = np.zeros(N)
    for e in render.escenas:
        b = e["inicio"]
        if e["idx"] > 0:
            pegar(sfx, (b - 0.3) * SR, sfx_whoosh(rng), 0.8)
            pegar(sfx, b * SR, sfx_explosion(rng, 0.8), 0.35)
        pegar(sfx, (b + (0.12 if e["idx"] else 0)) * SR, sfx_disparo(rng), 0.25)
        for f in e.get("fx", []):
            if f["tipo"] == "explosion":
                pegar(sfx, (b + f["t"]) * SR, sfx_explosion(rng), 0.9 * min(1.2, f.get("escala", 1)))
            elif f["tipo"] == "disparo":
                pegar(sfx, (b + f["t"]) * SR, sfx_disparo(rng), 0.8)
            elif f["tipo"] == "dinero":
                for k in range(4):
                    pegar(sfx, (b + f.get("t", 0) + k * 0.35) * SR, sfx_caja(), 0.8)
            elif f["tipo"] == "revelar":
                pegar(sfx, (b + f["t"]) * SR, sfx_explosion(rng, 0.9), 0.4)
        if e.get("pregunta"):
            pegar(sfx, (b + e["duracion"] - 1.45) * SR, sfx_pop(), 1.0)
    voz = np.zeros(N)
    for e in render.escenas:
        archivo_voz = e.get("audio_voz")
        if archivo_voz and os.path.exists(os.path.join(RAIZ, archivo_voz)):
            retardo = 0 if e["idx"] == 0 else VOZ_RETARDO
            pegar(voz, (e["inicio"] + retardo) * SR, leer_wav(os.path.join(RAIZ, archivo_voz)), 1.0)
    env = filtro_lp(np.abs(sfx), 20)  # ducking: la música baja con los golpes
    env_voz = np.clip(filtro_lp(np.abs(voz), 8) * 12, 0, 1)  # y bastante más cuando habla la voz
    mus = mus / (1 + 2.5 * env) * (1 - 0.6 * env_voz)
    sfx = sfx * (1 - 0.35 * env_voz)
    mezcla = mus + sfx + voz * 1.35
    mezcla = mezcla[:int(total * SR)]
    fade = int(0.3 * SR)
    mezcla[-fade:] *= np.linspace(1, 0, fade)
    mezcla = np.tanh(mezcla * 1.3)
    mezcla = mezcla / (np.max(np.abs(mezcla)) + 1e-9) * 0.89
    pcm = (mezcla * 32767).astype(np.int16)
    with wave.open(ruta, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.stack([pcm, pcm], 1).tobytes())


# --------------------------------------------------------------------------
# salida auxiliar y main
# --------------------------------------------------------------------------

def fmt_srt(s):
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def escribir_srt(render, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        for i, b in enumerate(render.bloques, 1):
            texto = " ".join(p.replace("...", "…") for p, _, _ in b)
            f.write(f"{i}\n{fmt_srt(b[0][1])} --> {fmt_srt(b[-1][2])}\n{texto}\n\n")


def escribir_locucion(render, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(f"# Guion de locución — {render.g['titulo']}\n\nDuración total: {render.total:.1f} s\n\n")
        for e in render.escenas:
            f.write(f"**[{e['inicio']:05.2f}s – {e['fin']:05.2f}s] {e['id']}**  \n{e['voz']}\n\n")


_R = None


def _init(guion):
    global _R
    _R = Render(guion)


def _frame(n):
    return _R.frame(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guion", default=os.path.join(RAIZ, "guion.json"))
    ap.add_argument("--preview", type=int, default=0)
    ap.add_argument("--procesos", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    with open(args.guion, encoding="utf-8") as f:
        guion = json.load(f)
    os.makedirs(SALIDA, exist_ok=True)
    r = Render(guion)
    print(f"Duración: {r.total:.1f} s · {len(r.escenas)} escenas")
    if args.preview:
        carpeta = os.path.join(SALIDA, "preview")
        os.makedirs(carpeta, exist_ok=True)
        for e in r.escenas:
            for k in range(args.preview):
                t = e["inicio"] + e["duracion"] * (k + 1) / (args.preview + 1)
                Image.frombytes("RGB", (W, H), r.frame(int(t * r.fps))).save(
                    os.path.join(carpeta, f"{e['idx']:02d}_{e['id']}_{k}.jpg"), quality=88)
        print("Previews en", carpeta)
        return
    audio = os.path.join(SALIDA, "audio.wav")
    escribir_audio(r, audio)
    escribir_srt(r, os.path.join(SALIDA, "subtitulos.srt"))
    escribir_locucion(r, os.path.join(SALIDA, "locucion.md"))
    salida = os.path.join(SALIDA, "reel.mp4")
    n_frames = int(round(r.total * r.fps))
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(r.fps), "-i", "-",
           "-i", audio,
           "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "10M", "-bufsize", "20M",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "192k", "-shortest", salida]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(args.procesos, initializer=_init, initargs=(guion,)) as pool:
        for i, datos in enumerate(pool.imap(_frame, range(n_frames), chunksize=4)):
            ff.stdin.write(datos)
            if i % 60 == 0:
                print(f"\r  fotograma {i}/{n_frames}", end="", flush=True)
    ff.stdin.close()
    ff.wait()
    if ff.returncode:
        sys.exit(f"ffmpeg falló con código {ff.returncode}")
    Image.frombytes("RGB", (W, H), r.frame(int(0.5 * r.fps))).save(os.path.join(SALIDA, "portada.jpg"), quality=92)
    print(f"\nListo: {salida}")
    if ff.returncode:
        sys.exit(ff.returncode)


if __name__ == "__main__":
    main()
