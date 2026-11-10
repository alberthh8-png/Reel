#!/usr/bin/env python3
"""Genera un reel vertical (1080x1920) a partir de guion.json.

Uso:
    python3 reel.py                 # render completo -> salida/reel.mp4
    python3 reel.py --preview 4     # fotogramas de muestra -> salida/preview/

Si colocas imágenes en ./imagenes/<id_escena>.jpg|png (por ejemplo
imagenes/dato3.jpg) se usarán como fondo de esa escena con efecto Ken Burns.
Usa solo imágenes sobre las que tengas derechos (p. ej. material de prensa oficial).
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
TRANS = 0.28  # segundos de transición entre escenas

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


_fuentes = {}


def fuente(tam, bold=True):
    clave = (tam, bold)
    if clave not in _fuentes:
        _fuentes[clave] = ImageFont.truetype(FUENTE_BOLD if bold else FUENTE_MED, tam)
    return _fuentes[clave]


def ajustar_fuente(texto, ancho_max, tam_max, bold=True, tam_min=40):
    tam = tam_max
    while tam > tam_min:
        f = fuente(tam, bold)
        if f.getbbox(texto)[2] <= ancho_max:
            return f
        tam -= 4
    return fuente(tam_min, bold)


def envolver(texto, f, ancho_max):
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if f.getbbox(prueba)[2] <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def texto_con_estilo(texto, f, relleno, borde=0, color_borde=(0, 0, 0),
                     sombra=True, brillo=None):
    """Devuelve una imagen RGBA con el texto, borde, sombra y glow opcional."""
    x0, y0, x1, y1 = f.getbbox(texto, stroke_width=borde)
    pad = 40
    w, h = x1 - x0 + pad * 2, y1 - y0 + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pos = (pad - x0, pad - y0)
    if brillo:
        g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(g).text(pos, texto, font=f, fill=brillo + (255,),
                               stroke_width=borde + 6, stroke_fill=brillo + (255,))
        g = g.filter(ImageFilter.GaussianBlur(18))
        img.alpha_composite(g)
    if sombra:
        s = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(s).text((pos[0] + 6, pos[1] + 10), texto, font=f,
                               fill=(0, 0, 0, 170), stroke_width=borde,
                               stroke_fill=(0, 0, 0, 170))
        s = s.filter(ImageFilter.GaussianBlur(6))
        img.alpha_composite(s)
    ImageDraw.Draw(img).text(pos, texto, font=f, fill=relleno,
                             stroke_width=borde, stroke_fill=color_borde)
    return img


def pegar_centrado(base, capa, cx, cy, escala=1.0, alfa=1.0, angulo=0.0):
    if escala <= 0.01 or alfa <= 0.01:
        return
    if abs(escala - 1) > 1e-3:
        capa = capa.resize((max(1, int(capa.width * escala)),
                            max(1, int(capa.height * escala))), Image.BILINEAR)
    if angulo:
        capa = capa.rotate(angulo, resample=Image.BICUBIC, expand=True)
    if alfa < 0.999:
        a = capa.getchannel("A").point(lambda v: int(v * alfa))
        capa = capa.copy()
        capa.putalpha(a)
    base.alpha_composite(capa, (int(cx - capa.width / 2), int(cy - capa.height / 2)))


# --------------------------------------------------------------------------
# fondo procedural: ciudad costera neón al atardecer (original)
# --------------------------------------------------------------------------

class Mundo:
    def __init__(self, W, H, semilla=7):
        self.W, self.H = W, H
        rnd = random.Random(semilla)
        self.horizonte = int(H * 0.56)
        self.cielo = self._cielo(rnd)
        self.ciudad = self._ciudad(rnd)
        self.palmeras = self._palmeras(rnd)
        self.grano = [self._grano(rnd) for _ in range(4)]
        self.scan = self._scanlines()
        self.vineta = self._vineta()

    def _cielo(self, rnd):
        W, H, hz = self.W, self.H, self.horizonte
        y = np.linspace(0, 1, H)[:, None]
        paradas = [(0.0, (14, 6, 40)), (0.30, (58, 16, 102)), (0.47, (196, 38, 128)),
                   (0.56, (255, 122, 80)), (0.561, (30, 10, 60)), (0.75, (18, 8, 46)),
                   (1.0, (8, 4, 22))]
        img = np.zeros((H, W, 3), np.float32)
        for (p0, c0), (p1, c1) in zip(paradas, paradas[1:]):
            m = ((y >= p0) & (y <= p1)).astype(np.float32)
            t = np.clip((y - p0) / max(p1 - p0, 1e-6), 0, 1)
            for k in range(3):
                img[:, :, k] += m[:, 0:1] * (c0[k] + (c1[k] - c0[k]) * t)
        img = np.clip(img, 0, 255).astype(np.uint8)
        cielo = Image.fromarray(img, "RGB").convert("RGBA")
        d = ImageDraw.Draw(cielo)
        for _ in range(140):  # estrellas
            sx, sy = rnd.randrange(W), rnd.randrange(int(hz * 0.45))
            r = rnd.choice([1, 1, 2])
            d.ellipse((sx, sy, sx + r, sy + r), fill=(255, 255, 255, rnd.randrange(90, 230)))
        # sol con franjas
        R, cx, cy = 300, W // 2, hz - 40
        sol = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ys = np.arange(H)[:, None]
        grad = np.clip((ys - (cy - R)) / (2 * R), 0, 1)
        col = np.concatenate([255 * np.ones_like(grad), 220 - 150 * grad,
                              90 + 60 * grad, 255 * np.ones_like(grad)], 1)
        capa = np.repeat(col[:, None, :], W, 1).astype(np.uint8)
        mascara = Image.new("L", (W, H), 0)
        dm = ImageDraw.Draw(mascara)
        dm.ellipse((cx - R, cy - R, cx + R, cy + R), fill=255)
        for i in range(7):  # franjas retro
            fy = cy + 20 + i * 34
            dm.rectangle((0, fy, W, fy + 4 + i * 3), fill=0)
        dm.rectangle((0, hz, W, H), fill=0)
        sol = Image.fromarray(capa, "RGBA")
        sol.putalpha(mascara)
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse((cx - R - 80, cy - R - 80, cx + R + 80, cy + R + 80),
                                     fill=(255, 90, 140, 120))
        halo = halo.filter(ImageFilter.GaussianBlur(90))
        cielo.alpha_composite(halo)
        cielo.alpha_composite(sol)
        # reflejos en el agua
        d = ImageDraw.Draw(cielo)
        for i in range(26):
            ry = hz + 14 + i * i * 1.25
            if ry > H:
                break
            ancho = int(R * (1.0 - i * 0.025)) + rnd.randrange(-30, 30)
            d.rectangle((cx - ancho, ry, cx + ancho, ry + 3 + i // 4),
                        fill=(255, 140 - i * 3, 120, max(30, 170 - i * 6)))
        # rejilla en perspectiva sobre el agua
        rej = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(rej)
        for i in range(-14, 15):
            dr.line((cx + i * 40, hz, cx + i * 420, H), fill=(45, 226, 230, 55), width=2)
        for i in range(1, 16):
            gy = hz + (H - hz) * (i / 15) ** 2.2
            dr.line((0, gy, W, gy), fill=(45, 226, 230, 50), width=2)
        cielo.alpha_composite(rej)
        return cielo

    def _ciudad(self, rnd):
        W, hz = self.W * 3, self.horizonte
        img = Image.new("RGBA", (W, hz + 20), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = 0
        while x < W:  # capa lejana
            w, h = rnd.randrange(50, 120), rnd.randrange(80, 260)
            d.rectangle((x, hz - h, x + w, hz), fill=(40, 14, 70, 255))
            x += w + rnd.randrange(0, 12)
        x = 0
        while x < W:  # capa cercana con ventanas
            w, h = rnd.randrange(70, 150), rnd.randrange(140, 460)
            top = hz - h
            d.rectangle((x, top, x + w, hz), fill=(22, 8, 42, 255))
            if rnd.random() < 0.3:  # antena
                d.rectangle((x + w // 2 - 2, top - 50, x + w // 2 + 2, top), fill=(22, 8, 42, 255))
                d.ellipse((x + w // 2 - 6, top - 58, x + w // 2 + 6, top - 46), fill=(255, 61, 139, 255))
            for wy in range(top + 16, hz - 12, 22):
                for wx in range(x + 10, x + w - 12, 18):
                    if rnd.random() < 0.33:
                        c = rnd.choice([(255, 210, 120), (45, 226, 230), (255, 61, 139), (255, 240, 200)])
                        d.rectangle((wx, wy, wx + 7, wy + 10), fill=c + (rnd.randrange(150, 255),))
            if rnd.random() < 0.35:  # borde neón
                c = rnd.choice([(255, 61, 139), (45, 226, 230)])
                d.line((x, top, x + w, top), fill=c + (255,), width=4)
            x += w + rnd.randrange(4, 26)
        return img

    def _palmera(self, rnd, alto):
        w = int(alto * 0.9)
        img = Image.new("RGBA", (w, alto), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        base_x, top_y = w // 2 + rnd.randrange(-40, 40), int(alto * 0.18)
        curva = rnd.uniform(-0.25, 0.25) * alto
        pts = []
        for i in range(31):
            t = i / 30
            px = base_x + curva * (1 - t) ** 2 - curva
            py = alto - t * (alto - top_y)
            pts.append((px, py))
        for i in range(30):
            grosor = int(30 - 16 * i / 30)
            d.line((pts[i], pts[i + 1]), fill=(8, 2, 18, 255), width=grosor)
        cx, cy = pts[-1]
        for k in range(9):
            ang = math.radians(-180 + k * 22.5 + rnd.uniform(-8, 8))
            largo = alto * rnd.uniform(0.28, 0.38)
            hoja = []
            for j in range(13):
                t = j / 12
                hx = cx + math.cos(ang) * largo * t
                hy = cy + math.sin(ang) * largo * t + (t ** 2) * largo * 0.55
                hoja.append((hx, hy))
            for j in range(12):
                d.line((hoja[j], hoja[j + 1]), fill=(8, 2, 18, 255), width=max(4, int(22 * (1 - j / 12))))
                if j % 2 == 0:  # foliolos
                    hx, hy = hoja[j]
                    d.line((hx, hy, hx + 18 * math.cos(ang + 1.2), hy + 26), fill=(8, 2, 18, 255), width=5)
        return img

    def _palmeras(self, rnd):
        W, H = self.W * 3, self.H
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        x = -100
        while x < W:
            alto = rnd.randrange(int(H * 0.55), int(H * 0.9))
            p = self._palmera(rnd, alto)
            img.alpha_composite(p, (x, H - alto + 40))
            x += rnd.randrange(420, 900)
        return img

    def _grano(self, rnd):
        n = np.random.default_rng(rnd.randrange(1 << 30)).integers(0, 255, (self.H // 2, self.W // 2), dtype=np.uint8)
        g = Image.fromarray(n, "L").resize((self.W, self.H), Image.NEAREST)
        a = Image.new("RGBA", (self.W, self.H), (255, 255, 255, 0))
        a.putalpha(g.point(lambda v: 14 if v > 200 else 0))
        return a

    def _scanlines(self):
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for y in range(0, self.H, 6):
            d.line((0, y, self.W, y), fill=(0, 0, 0, 26), width=2)
        return img

    def _vineta(self):
        W, H = self.W, self.H
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        dist = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.5) / (H * 0.62)) ** 2)
        a = np.clip((dist - 0.55) * 300, 0, 200).astype(np.uint8)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        img.putalpha(Image.fromarray(a, "L"))
        return img

    def render(self, t, pan, zoom):
        W, H = self.W, self.H
        frame = self.cielo.copy()
        cx = int((pan * 900 + t * 18) % (self.ciudad.width - W))
        frame.alpha_composite(self.ciudad.crop((cx, 0, cx + W, self.ciudad.height)), (0, 0))
        px = int((pan * 1800 + t * 60) % (self.palmeras.width - W))
        frame.alpha_composite(self.palmeras.crop((px, 0, px + W, H)), (0, 0))
        if zoom > 1.001:
            nw, nh = int(W * zoom), int(H * zoom)
            frame = frame.resize((nw, nh), Image.BILINEAR)
            ox, oy = (nw - W) // 2, int((nh - H) * 0.45)
            frame = frame.crop((ox, oy, ox + W, oy + H))
        return frame


def fondo_imagen(ruta, W, H):
    img = Image.open(ruta).convert("RGB")
    esc = max(W * 1.15 / img.width, H * 1.15 / img.height)
    img = img.resize((int(img.width * esc), int(img.height * esc)), Image.LANCZOS)
    return img.convert("RGBA")


# --------------------------------------------------------------------------
# iconos dibujados (simples y originales)
# --------------------------------------------------------------------------

def icono(nombre, tam, color):
    S = tam
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = color + (255,)
    g = max(8, S // 14)
    if nombre == "reloj":
        d.ellipse((g, g, S - g, S - g), outline=c, width=g)
        d.line((S / 2, S / 2, S / 2, S * 0.24), fill=c, width=g)
        d.line((S / 2, S / 2, S * 0.7, S * 0.6), fill=c, width=g)
    elif nombre == "descarga":
        d.line((S / 2, S * 0.1, S / 2, S * 0.62), fill=c, width=g + 4)
        d.polygon([(S * 0.25, S * 0.45), (S * 0.75, S * 0.45), (S / 2, S * 0.72)], fill=c)
        d.line((S * 0.12, S * 0.75, S * 0.12, S * 0.9, S * 0.88, S * 0.9, S * 0.88, S * 0.75),
               fill=c, width=g, joint="curve")
    elif nombre == "duo":
        for ox, col in ((-0.17, hexrgb("#ff3d8b")), (0.17, hexrgb("#2de2e6"))):
            cc = col + (255,)
            x = S * (0.5 + ox)
            d.ellipse((x - S * 0.13, S * 0.14, x + S * 0.13, S * 0.4), fill=cc)
            d.pieslice((x - S * 0.24, S * 0.46, x + S * 0.24, S * 1.1), 180, 360, fill=cc)
    elif nombre == "play":
        d.rounded_rectangle((g, S * 0.18, S - g, S * 0.82), radius=S // 8, outline=c, width=g)
        d.polygon([(S * 0.42, S * 0.36), (S * 0.42, S * 0.64), (S * 0.66, S * 0.5)], fill=c)
    elif nombre == "etiqueta":
        d.polygon([(S * 0.1, S * 0.45), (S * 0.45, S * 0.1), (S * 0.9, S * 0.1),
                   (S * 0.9, S * 0.55), (S * 0.55, S * 0.9)], outline=c, width=g)
        d.ellipse((S * 0.66, S * 0.22, S * 0.78, S * 0.34), fill=c)
    elif nombre == "pc":
        d.rounded_rectangle((g, S * 0.12, S - g, S * 0.68), radius=S // 14, outline=c, width=g)
        d.rectangle((S * 0.44, S * 0.68, S * 0.56, S * 0.82), fill=c)
        d.rounded_rectangle((S * 0.26, S * 0.82, S * 0.74, S * 0.9), radius=6, fill=c)
    elif nombre == "sin_red":
        for i, r in enumerate((0.42, 0.29, 0.16)):
            d.arc((S / 2 - S * r, S * 0.62 - S * r, S / 2 + S * r, S * 0.62 + S * r), 220, 320, fill=c, width=g)
        d.ellipse((S / 2 - g, S * 0.66 - g, S / 2 + g, S * 0.66 + g), fill=c)
        rojo = hexrgb("#ff3d8b") + (255,)
        d.line((S * 0.14, S * 0.14, S * 0.86, S * 0.86), fill=(10, 4, 30, 255), width=g * 3)
        d.line((S * 0.14, S * 0.14, S * 0.86, S * 0.86), fill=rojo, width=g + 4)
    elif nombre == "yate":
        d.polygon([(S * 0.04, S * 0.58), (S * 0.96, S * 0.58), (S * 0.8, S * 0.78), (S * 0.16, S * 0.78)], fill=c)
        d.polygon([(S * 0.22, S * 0.58), (S * 0.34, S * 0.4), (S * 0.72, S * 0.4), (S * 0.8, S * 0.58)], fill=c)
        d.polygon([(S * 0.38, S * 0.4), (S * 0.46, S * 0.26), (S * 0.62, S * 0.26), (S * 0.66, S * 0.4)], fill=c)
        for i in range(4):
            x = S * (0.38 + i * 0.09)
            d.rectangle((x, S * 0.45, x + S * 0.05, S * 0.52), fill=(10, 4, 30, 255))
        for k in range(2):
            y = S * (0.86 + k * 0.08)
            d.arc((S * 0.05, y - S * 0.05, S * 0.35, y + S * 0.05), 0, 180, fill=c, width=g // 2 + 2)
            d.arc((S * 0.35, y - S * 0.05, S * 0.65, y + S * 0.05), 180, 360, fill=c, width=g // 2 + 2)
            d.arc((S * 0.65, y - S * 0.05, S * 0.95, y + S * 0.05), 0, 180, fill=c, width=g // 2 + 2)
    elif nombre == "dinero":
        verde = (80, 230, 140, 255)
        for k in range(3):
            o = k * S * 0.07
            d.rounded_rectangle((S * 0.06 + o, S * 0.22 + o, S * 0.8 + o, S * 0.62 + o), radius=S // 18,
                                fill=(10, 4, 30, 255), outline=verde, width=g)
        o = 2 * S * 0.07
        fd = fuente(int(S * 0.34))
        bb = fd.getbbox("$")
        d.text((S * 0.43 + o - (bb[2] + bb[0]) / 2, S * 0.42 + o - (bb[3] + bb[1]) / 2), "$", font=fd, fill=verde)
    elif nombre == "placa":
        cx, cy = S / 2, S / 2
        pts = []
        for k in range(14):
            r = S * (0.46 if k % 2 == 0 else 0.3)
            a = math.pi * 2 * k / 14 - math.pi / 2
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        d.polygon(pts, fill=hexrgb("#ffd23f") + (255,))
        d.ellipse((cx - S * 0.2, cy - S * 0.2, cx + S * 0.2, cy + S * 0.2), fill=(10, 4, 30, 255))
        fq = fuente(int(S * 0.26))
        bb = fq.getbbox("?")
        d.text((cx - (bb[2] + bb[0]) / 2, cy - (bb[3] + bb[1]) / 2), "?", font=fq, fill=hexrgb("#ffd23f") + (255,))
    elif nombre == "interrogante":
        d.ellipse((g, g, S - g, S - g), outline=c, width=g)
        fq = fuente(int(S * 0.6))
        bb = fq.getbbox("?")
        d.text((S / 2 - (bb[2] + bb[0]) / 2, S / 2 - (bb[3] + bb[1]) / 2), "?", font=fq, fill=c)
    elif nombre == "comentario":
        d.rounded_rectangle((g, S * 0.12, S - g, S * 0.7), radius=S // 6, outline=c, width=g)
        d.polygon([(S * 0.26, S * 0.66), (S * 0.46, S * 0.66), (S * 0.22, S * 0.9)], fill=c)
        for i in range(3):
            x = S * (0.32 + i * 0.18)
            d.ellipse((x - g, S * 0.41 - g, x + g, S * 0.41 + g), fill=c)
    return img


# --------------------------------------------------------------------------
# subtítulos estilo karaoke
# --------------------------------------------------------------------------

def tiempos_palabras(voz, inicio, dur):
    palabras = voz.split()
    pesos = [len(p) + 2 + (6 if p.endswith(("...", ".", "?", ":")) else 0) for p in palabras]
    total = sum(pesos)
    arranque = 0.0 if inicio == 0 else 0.15
    t, salida = inicio + arranque, []
    util = dur - 0.2 - arranque
    for p, w in zip(palabras, pesos):
        d = util * w / total
        salida.append((p, t, t + d))
        t += d
    return salida


def bloques_subtitulo(palabras, max_palabras=3):
    bloques, actual = [], []
    for p in palabras:
        actual.append(p)
        if len(actual) >= max_palabras or p[0].endswith((".", "?", ":", ",", "...")):
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return bloques


def limpiar(p):
    return p.replace("...", "").upper()


# --------------------------------------------------------------------------
# render de escenas
# --------------------------------------------------------------------------

class Render:
    def __init__(self, guion):
        self.g = guion
        self.W, self.H, self.fps = guion["ancho"], guion["alto"], guion["fps"]
        col = guion["colores"]
        self.acento, self.rosa = hexrgb(col["acento"]), hexrgb(col["rosa"])
        self.cian, self.blanco = hexrgb(col["cian"]), hexrgb(col["texto"])
        self.mundo = Mundo(self.W, self.H)
        t = 0.0
        self.escenas = []
        for i, e in enumerate(guion["escenas"]):
            e = dict(e)
            e["inicio"], e["fin"], e["idx"] = t, t + e["duracion"], i
            ruta = None
            for ext in ("jpg", "jpeg", "png", "webp"):
                p = os.path.join(RAIZ, "imagenes", f"{e['id']}.{ext}")
                if os.path.exists(p):
                    ruta = p
            e["fondo"] = fondo_imagen(ruta, self.W, self.H) if ruta else None
            self._preparar(e)
            self.escenas.append(e)
            t += e["duracion"]
        self.total = t
        self.palabras = []
        for e in self.escenas:
            self.palabras.extend(tiempos_palabras(e["voz"], e["inicio"], e["duracion"]))
        self.bloques = bloques_subtitulo([(p, a, b) for p, a, b in self.palabras])
        self.etiqueta = self._etiqueta(guion.get("etiqueta", ""))

    # capas estáticas por escena (se escalan/animan por fotograma)
    def _preparar(self, e):
        W = self.W
        e["capa_ante"] = None
        if e.get("antetitulo"):
            f = ajustar_fuente(e["antetitulo"].upper(), W - 200, 78)
            e["capa_ante"] = texto_con_estilo(e["antetitulo"].upper(), f, self.cian + (255,),
                                              borde=4, color_borde=(10, 4, 30))
        tit = e["titular"]
        tam = 250 if len(tit) <= 7 else 150
        f = ajustar_fuente(tit, W - 120, tam)
        e["capa_tit"] = texto_con_estilo(tit, f, self.acento + (255,), borde=10,
                                         color_borde=(20, 6, 40), brillo=self.rosa)
        e["capa_det"] = None
        if e.get("detalle"):
            f = fuente(54, bold=False)
            lineas = envolver(e["detalle"], f, W - 220)
            capas = [texto_con_estilo(l, f, self.blanco + (255,), borde=3, color_borde=(10, 4, 30))
                     for l in lineas]
            h = sum(c.height - 50 for c in capas) + 50
            caja = Image.new("RGBA", (max(c.width for c in capas) + 60, h + 40), (0, 0, 0, 0))
            ImageDraw.Draw(caja).rounded_rectangle((10, 10, caja.width - 10, caja.height - 10),
                                                   radius=34, fill=(12, 4, 32, 170),
                                                   outline=self.rosa + (200,), width=4)
            y = 20
            for c in capas:
                caja.alpha_composite(c, ((caja.width - c.width) // 2, y))
                y += c.height - 50
            e["capa_det"] = caja
        e["capa_icono"] = icono(e["icono"], 190, self.blanco) if e.get("icono") else None
        e["capa_num"] = None
        if e.get("numero"):
            S = 200
            n = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            dn = ImageDraw.Draw(n)
            dn.ellipse((8, 8, S - 8, S - 8), fill=self.rosa + (255,), outline=self.blanco + (255,), width=8)
            fn = fuente(120)
            bb = fn.getbbox(str(e["numero"]))
            dn.text(((S - bb[2] - bb[0]) / 2, (S - bb[3] - bb[1]) / 2 - 4), str(e["numero"]),
                    font=fn, fill=self.blanco + (255,))
            e["capa_num"] = n
        e["capa_sello"] = None
        if e.get("sello"):
            colores = {"CONFIRMADO": (60, 220, 140), "RUMOR": self.acento, "TEORÍA": self.rosa,
                       "ANALISTAS": self.cian}
            cs = colores.get(e["sello"].upper(), self.cian)
            fs = fuente(40)
            txt = e["sello"].upper()
            bb = fs.getbbox(txt)
            sl = Image.new("RGBA", (bb[2] + 80, 86), (0, 0, 0, 0))
            ds = ImageDraw.Draw(sl)
            ds.rounded_rectangle((4, 4, sl.width - 5, 81), radius=14, fill=(10, 4, 30, 220),
                                 outline=cs + (255,), width=6)
            ds.text((40, 43 - (bb[3] + bb[1]) / 2), txt, font=fs, fill=cs + (255,))
            e["capa_sello"] = sl
        if e["tipo"] == "linea_tiempo":
            fh = ajustar_fuente(max(e["hitos"], key=len), W - 300, 60)
            e["capas_hitos"] = [texto_con_estilo(h, fh, self.blanco + (255,), borde=4,
                                                 color_borde=(10, 4, 30)) for h in e["hitos"]]

    def _etiqueta(self, txt):
        if not txt:
            return None
        f = fuente(34)
        bb = f.getbbox(txt)
        img = Image.new("RGBA", (bb[2] + 70, 76), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, img.width - 1, 75), radius=38, fill=(255, 61, 139, 230))
        d.text((35, 38 - (bb[3] + bb[1]) / 2), txt, font=f, fill=(255, 255, 255, 255))
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
        W, H = self.W, self.H
        # --- fondo
        zoom = 1.0 + 0.07 * (lt / e["duracion"])
        if e["tipo"] == "gancho":
            zoom += 0.12 * (1 - ease_out_cubic(lt / 0.6))
        if e["fondo"] is not None:
            img = e["fondo"]
            z = 1.0 + 0.08 * (lt / e["duracion"])
            nw, nh = int(W * z), int(H * z)
            ox = (img.width - nw) // 2 + int((e["idx"] % 2 * 2 - 1) * 40 * lt / e["duracion"])
            oy = (img.height - nh) // 2
            frame = img.crop((ox, oy, ox + nw, oy + nh)).resize((W, H), Image.BILINEAR)
            sombra = Image.new("RGBA", (W, H), (10, 4, 30, 110))
            frame.alpha_composite(sombra)
        else:
            frame = self.mundo.render(t, pan=e["idx"] * 0.37, zoom=zoom)
        # --- elementos de la escena
        self._elementos(frame, e, lt)
        # --- interfaz fija
        self._interfaz(frame, t)
        self._subtitulos(frame, t)
        frame.alpha_composite(self.mundo.scan)
        frame.alpha_composite(self.mundo.grano[n % 4])
        frame.alpha_composite(self.mundo.vineta)
        rgb = frame.convert("RGB")
        # --- transiciones: destello + glitch RGB + sacudida
        fuerza = 0.0
        for b in [x["inicio"] for x in self.escenas[1:]]:
            dt = t - b
            if -TRANS / 2 <= dt <= TRANS:
                fuerza = max(fuerza, 1 - abs(dt) / TRANS)
        if fuerza > 0:
            arr = np.asarray(rgb).astype(np.int16)
            off = int(28 * fuerza)
            arr[:, :, 0] = np.roll(arr[:, :, 0], off, axis=1)
            arr[:, :, 2] = np.roll(arr[:, :, 2], -off, axis=1)
            sh = int(math.sin(t * 90) * 30 * fuerza)
            arr = np.roll(arr, sh, axis=0)
            arr = arr + int(150 * fuerza ** 2)
            rgb = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        return rgb.tobytes()

    def _elementos(self, frame, e, lt):
        W = self.W
        sal = clamp((e["duracion"] - lt) / 0.22)  # desvanecido de salida
        tipo = e["tipo"]
        y_tit = 760
        if e["capa_num"] is not None:
            p = ease_out_back(lt / 0.4)
            nx = W / 2 - 120 if e["capa_icono"] is not None else W / 2
            pegar_centrado(frame, e["capa_num"], nx, 430, escala=p, alfa=sal,
                           angulo=(1 - clamp(lt / 0.4)) * 90)
        if e["capa_ante"] is not None:
            p = 1.0 if tipo == "gancho" else ease_out_cubic(lt / 0.35)
            y = 470 if e["capa_num"] is None else 330
            if e["capa_num"] is not None:
                pegar_centrado(frame, e["capa_ante"], W / 2 - (1 - p) * 300, 620, alfa=p * sal)
            else:
                pegar_centrado(frame, e["capa_ante"], W / 2, y + (1 - p) * 60, alfa=p * sal)
        # titular con pop y pulso al ritmo
        p = ease_out_back((lt - 0.12) / 0.45)
        if tipo == "gancho":
            p = 1.18 - 0.18 * ease_out_cubic(lt / 0.35)
        pulso = 1 + 0.025 * max(0, math.cos(2 * math.pi * lt * self.g["bpm"] / 60)) ** 8
        if tipo == "gancho":
            pulso += 0.04 * math.sin(lt * 6)
        pegar_centrado(frame, e["capa_tit"], W / 2, y_tit if tipo != "linea_tiempo" else 730,
                       escala=p * pulso, alfa=clamp(p) * sal)
        if tipo == "linea_tiempo":
            self._linea_tiempo(frame, e, lt, sal)
        elif e["capa_det"] is not None:
            p = ease_out_cubic((lt - 0.4) / 0.4)
            yd = 1010 if tipo == "gancho" else 1000
            if tipo == "gancho":
                p = ease_out_cubic((lt - 0.25) / 0.3)
            pegar_centrado(frame, e["capa_det"], W / 2, yd + (1 - p) * 80, alfa=p * sal)
        if e["capa_icono"] is not None and tipo != "gancho":
            p = ease_out_back((lt - 0.25) / 0.45)
            bob = math.sin(lt * 4) * 10
            x = W / 2 + 120 if e["capa_num"] is not None else W / 2
            y = 430 + bob if e["capa_num"] is not None else 300 + bob
            if e["capa_num"] is None and e["capa_ante"] is not None:
                y = 1130 + bob
            pegar_centrado(frame, e["capa_icono"], x, y, escala=p * 0.8, alfa=clamp(p) * sal)
        if e["capa_sello"] is not None:
            p = ease_out_cubic((lt - 0.3) / 0.22)
            if p > 0:
                ys = 575 if e["capa_num"] is not None else 590
                pegar_centrado(frame, e["capa_sello"], W / 2, ys, escala=1 + (1 - p) * 1.2,
                               alfa=p * sal, angulo=-4)
        if tipo == "gancho":
            self._cuenta_atras(frame, lt, sal)

    def _cuenta_atras(self, frame, lt, sal):
        d = ImageDraw.Draw(frame)
        W = self.W
        cx, cy, R = W / 2, 1200, 82
        frac = clamp(lt / 2.6)
        d.ellipse((cx - R, cy - R, cx + R, cy + R), outline=(255, 255, 255, int(70 * sal)), width=10)
        d.arc((cx - R, cy - R, cx + R, cy + R), -90, -90 + 360 * frac,
              fill=self.acento + (int(255 * sal),), width=12)
        ic = icono("reloj", 110, self.blanco)
        pegar_centrado(frame, ic, cx, cy, alfa=sal)

    def _linea_tiempo(self, frame, e, lt, sal):
        W = self.W
        d = ImageDraw.Draw(frame)
        ys = [920, 1050, 1180]
        for i, (capa, y) in enumerate(zip(e["capas_hitos"], ys)):
            ap = 0.5 + i * 1.15
            p = ease_out_cubic((lt - ap) / 0.35)
            if p <= 0:
                continue
            x = W / 2 + (1 - p) * 400
            ultimo = i == len(ys) - 1
            tachar = e.get("tachar", True)
            col = self.cian if ultimo else ((150, 140, 170) if tachar else self.acento)
            pegar_centrado(frame, capa, x + 40, y, alfa=p * sal)
            bx = x - capa.width / 2 - 20
            d.ellipse((bx - 30, y - 30, bx + 30, y + 30), fill=col + (int(255 * p * sal),))
            if ultimo:
                d.line((bx - 14, y, bx - 3, y + 12, bx + 16, y - 12), fill=(10, 4, 30, 255), width=8)
            elif not tachar:
                d.ellipse((bx - 10, y - 10, bx + 10, y + 10), fill=(10, 4, 30, 255))
            else:
                d.line((bx - 12, y - 12, bx + 12, y + 12), fill=(10, 4, 30, 255), width=8)
                d.line((bx - 12, y + 12, bx + 12, y - 12), fill=(10, 4, 30, 255), width=8)
                tach = ease_out_cubic((lt - ap - 0.45) / 0.3)
                if tach > 0:
                    x0 = x + 40 - capa.width / 2 + 40
                    x1 = x0 + (capa.width - 80) * tach
                    d.line((x0, y + 2, x1, y + 2), fill=self.rosa + (int(255 * sal),), width=9)

    def _interfaz(self, frame, t):
        W = self.W
        d = ImageDraw.Draw(frame)
        # barra de progreso global
        d.rectangle((0, 0, W, 12), fill=(0, 0, 0, 120))
        d.rectangle((0, 0, int(W * t / self.total), 12), fill=self.acento + (255,))
        if self.etiqueta is not None:
            frame.alpha_composite(self.etiqueta, ((W - self.etiqueta.width) // 2, 130))
        # puntos de progreso de los 5 datos
        datos = [e for e in self.escenas if e.get("numero")]
        if datos:
            actual = self.escena_en(t)
            n = len(datos)
            sep = 44
            x0 = W / 2 - (n - 1) * sep / 2
            for i, e in enumerate(datos):
                hecho = t >= e["inicio"]
                activo = e is actual
                r = 13 if activo else 9
                c = self.acento if hecho else (255, 255, 255)
                a = 255 if hecho else 90
                d.ellipse((x0 + i * sep - r, 250 - r, x0 + i * sep + r, 250 + r), fill=c + (a,))

    def _subtitulos(self, frame, t):
        bloque = None
        for b in self.bloques:
            if b[0][1] - 0.05 <= t < b[-1][2] + 0.1:
                bloque = b
        if bloque is None:
            return
        W = self.W
        f = fuente(76)
        palabras = [limpiar(p) for p, _, _ in bloque]
        espacio = 22
        anchos = [f.getbbox(p, stroke_width=8)[2] for p in palabras]
        total = sum(anchos) * 1.12 + espacio * (len(palabras) - 1)
        escala = min(1.0, (W - 120) / total)
        y = 1400
        aparicion = 1.0 if bloque[0][1] == 0 else 0.85 + 0.15 * ease_out_back((t - bloque[0][1]) / 0.18, 2.5)
        activas = [a <= t < b + 0.05 for _, a, b in bloque]
        escalas = [escala * aparicion * (1.12 if ac else 1.0) for ac in activas]
        total = sum(w * e for w, e in zip(anchos, escalas)) + espacio * escala * (len(palabras) - 1)
        x = (W - total) / 2
        for (p, a, b), txt, w, ac, esc in zip(bloque, palabras, anchos, activas, escalas):
            dicha = t >= a
            col = self.acento if ac else (self.blanco if dicha else (220, 220, 235))
            capa = texto_con_estilo(txt, f, col + (255,), borde=8, color_borde=(0, 0, 0), sombra=True)
            pegar_centrado(frame, capa, x + w * esc / 2, y - (6 if ac else 0), escala=esc)
            x += w * esc + espacio * escala


# --------------------------------------------------------------------------
# audio: música synthwave original + efectos, generada con numpy
# --------------------------------------------------------------------------

SR = 44100


def nota(n):  # número MIDI -> Hz
    return 440.0 * 2 ** ((n - 69) / 12)


def filtro_lp(x, corte):
    try:
        from scipy.signal import lfilter
        a = math.exp(-2 * math.pi * corte / SR)
        return lfilter([1 - a], [1, -a], x)
    except ImportError:
        k = max(1, int(SR / corte / 2))
        return np.convolve(x, np.ones(k) / k, mode="same")


def sierra(f, t):
    return 2 * ((t * f) % 1.0) - 1


def generar_audio(guion, total, ruta):
    bpm = guion.get("bpm", 118)
    beat = 60 / bpm
    N = int(total * SR) + SR
    t = np.arange(N) / SR
    mezcla = np.zeros(N)
    rng = np.random.default_rng(3)
    # progresión: Am - F - C - G
    acordes = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
    bajos = [33, 29, 36, 31]
    compas = beat * 4
    # pad
    pad = np.zeros(N)
    for i in range(int(total / compas) + 2):
        a, b = int(i * compas * SR), int((i + 1) * compas * SR)
        b = min(b, N)
        if a >= N:
            break
        tt = t[a:b]
        seg = np.zeros(b - a)
        for n in acordes[i % 4]:
            for det in (-0.08, 0.08):
                seg += sierra(nota(n + 12) * (1 + det / 100), tt)
        env = np.minimum(1, (tt - tt[0]) / 0.05) * np.minimum(1, (tt[-1] - tt + 1e-3) / 0.08)
        pad[a:b] = seg * env
    mezcla += filtro_lp(pad, 1800) * 0.05
    # bajo en corcheas + arpegio en semicorcheas
    for i in range(int(total / (beat / 2)) + 2):
        a = int(i * beat / 2 * SR)
        if a >= N:
            break
        largo = int(beat / 2 * SR * 0.9)
        b = min(a + largo, N)
        tt = np.arange(b - a) / SR
        acorde = int(i * beat / 2 / compas) % 4
        f = nota(bajos[acorde] + (12 if i % 2 else 0))
        env = np.exp(-tt * 7)
        mezcla[a:b] += filtro_lp(sierra(f, tt), 600 + 1200 * env.mean()) * env * 0.22
    for i in range(int(total / (beat / 4)) + 2):
        a = int(i * beat / 4 * SR)
        if a >= N:
            break
        b = min(a + int(beat / 4 * SR), N)
        tt = np.arange(b - a) / SR
        acorde = acordes[int(i * beat / 4 / compas) % 4]
        n = (acorde + [acorde[0] + 12])[i % 4] + 12
        onda = np.sign(np.sin(2 * math.pi * nota(n) * tt))
        mezcla[a:b] += onda * np.exp(-tt * 18) * 0.035
    # batería
    kick_env = np.zeros(N)
    for i in range(int(total / beat) + 2):
        a = int(i * beat * SR)
        if a >= N:
            break
        L = min(int(0.35 * SR), N - a)
        tt = np.arange(L) / SR
        fase = 2 * math.pi * (45 * tt + (110 / 25) * (1 - np.exp(-tt * 25)))
        mezcla[a:a + L] += np.sin(fase) * np.exp(-tt * 9) * 0.75
        kick_env[a:a + L] = np.maximum(kick_env[a:a + L], np.exp(-tt * 6))
        if i % 2 == 1:  # caja
            Ls = min(int(0.25 * SR), N - a)
            ts = np.arange(Ls) / SR
            ruido = filtro_lp(rng.standard_normal(Ls), 5000)
            mezcla[a:a + Ls] += (ruido * 0.35 + np.sin(2 * math.pi * 190 * ts) * 0.3) * np.exp(-ts * 16)
        for off in (0.5,):  # charles
            h = int((i + off) * beat * SR)
            Lh = min(int(0.05 * SR), N - h)
            if Lh > 0:
                ruido = rng.standard_normal(Lh)
                ruido = ruido - filtro_lp(ruido, 7000)
                mezcla[h:h + Lh] += ruido * np.exp(-np.arange(Lh) / SR * 70) * 0.18
    # efecto "sidechain" para que respire
    mezcla *= 1 - 0.35 * kick_env + 0.35 * kick_env * (np.abs(mezcla) > 0.5)
    return mezcla, N


def efectos(guion, escenas, total, N):
    sfx = np.zeros(N)
    rng = np.random.default_rng(9)
    for k, e in enumerate(escenas):
        b = e["inicio"]
        if k > 0:  # whoosh antes del corte
            L = int(0.45 * SR)
            a = int((b - 0.38) * SR)
            if a > 0 and a + L < N:
                tt = np.arange(L) / SR
                ruido = rng.standard_normal(L)
                barrido = np.concatenate([filtro_lp(ruido[:L // 2], 1500), filtro_lp(ruido[L // 2:], 4000)])
                env = np.sin(np.pi * tt / tt[-1]) ** 2
                sfx[a:a + L] += barrido * env * 0.35
        # impacto en el arranque de cada escena
        L = int(0.6 * SR)
        a = int(b * SR)
        if a + L < N:
            tt = np.arange(L) / SR
            boom = np.sin(2 * math.pi * (38 * tt + 3 * (1 - np.exp(-tt * 12)))) * np.exp(-tt * 5)
            fuerza = 1.0 if k == 0 else 0.45
            sfx[a:a + L] += boom * fuerza
        if e["tipo"] == "linea_tiempo":  # "tic" por cada hito
            for i in range(len(e.get("hitos", []))):
                a = int((b + 0.5 + i * 1.15) * SR)
                L = int(0.12 * SR)
                tt = np.arange(L) / SR
                sfx[a:a + L] += np.sin(2 * math.pi * (1200 + 300 * i) * tt) * np.exp(-tt * 40) * 0.25
    return sfx


def escribir_audio(guion, escenas, total, ruta):
    musica, N = generar_audio(guion, total, ruta)
    sfx = efectos(guion, escenas, total, N)
    mezcla = musica * 0.7 + sfx
    n_final = int(total * SR)
    mezcla = mezcla[:n_final]
    fade = int(0.6 * SR)
    mezcla[-fade:] *= np.linspace(1, 0, fade)
    mezcla = np.tanh(mezcla * 1.2)
    mezcla = mezcla / (np.max(np.abs(mezcla)) + 1e-9) * 0.89
    pcm = (mezcla * 32767).astype(np.int16)
    estereo = np.stack([pcm, pcm], 1)
    with wave.open(ruta, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(estereo.tobytes())


# --------------------------------------------------------------------------
# subtítulos .srt y guion de locución
# --------------------------------------------------------------------------

def fmt_srt(s):
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def escribir_srt(render, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        for i, b in enumerate(render.bloques, 1):
            texto = " ".join(p.replace("...", "…") for p, _, _ in b)
            f.write(f"{i}\n{fmt_srt(b[0][1])} --> {fmt_srt(b[-1][2])}\n{texto}\n\n")


def escribir_locucion(render, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(f"# Guion de locución — {render.g['titulo']}\n\n")
        f.write(f"Duración total: {render.total:.1f} s\n\n")
        for e in render.escenas:
            f.write(f"**[{e['inicio']:05.2f}s – {e['fin']:05.2f}s] {e['id']}**  \n{e['voz']}\n\n")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

_R = None


def _init(guion):
    global _R
    _R = Render(guion)


def _frame(n):
    return _R.frame(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guion", default=os.path.join(RAIZ, "guion.json"))
    ap.add_argument("--preview", type=int, default=0, help="nº de fotogramas de muestra por escena")
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
                n = int(t * r.fps)
                Image.frombytes("RGB", (r.W, r.H), r.frame(n)).save(
                    os.path.join(carpeta, f"{e['idx']:02d}_{e['id']}_{k}.jpg"), quality=88)
        print("Previews en", carpeta)
        return

    audio = os.path.join(SALIDA, "musica.wav")
    escribir_audio(guion, r.escenas, r.total, audio)
    escribir_srt(r, os.path.join(SALIDA, "subtitulos.srt"))
    escribir_locucion(r, os.path.join(SALIDA, "locucion.md"))
    salida = os.path.join(SALIDA, "reel.mp4")
    n_frames = int(round(r.total * r.fps))
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{r.W}x{r.H}", "-r", str(r.fps), "-i", "-",
           "-i", audio,
           "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "9M", "-bufsize", "18M", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "192k", "-shortest", salida]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(args.procesos, initializer=_init, initargs=(guion,)) as pool:
        for i, datos in enumerate(pool.imap(_frame, range(n_frames), chunksize=4)):
            ff.stdin.write(datos)
            if i % 60 == 0:
                print(f"\r  fotograma {i}/{n_frames}", end="", flush=True)
    ff.stdin.close()
    ff.wait()
    portada = os.path.join(SALIDA, "portada.jpg")
    Image.frombytes("RGB", (r.W, r.H), r.frame(int(1.2 * r.fps))).save(portada, quality=92)
    print(f"\nListo: {salida}")
    if ff.returncode:
        sys.exit(ff.returncode)


if __name__ == "__main__":
    main()
