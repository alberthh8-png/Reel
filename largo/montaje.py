#!/usr/bin/env python3
"""Montaje del vídeo largo horizontal (1920x1080, 30 fps) para YouTube.

Uso:
    python3 largo/montaje.py                      # render completo -> salida/largo/video.mp4
    python3 largo/montaje.py --capitulos 01_records 02_reservas   # solo esos segmentos
    python3 largo/montaje.py --preview 01_records 12.5 30           # fotogramas de muestra (segundos)
    python3 largo/montaje.py --solo-audio / --unir                  # pasos sueltos

Cada capítulo se renderiza como un segmento independiente (en paralelo) y al final
se concatenan y se les pone el audio (voz + música original + efectos).
"""
import argparse
import json
import math
import os
import random
import re
import subprocess
import sys
import unicodedata
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reel  # noqa: E402
from reel import fuente, ajustar_fuente, texto_con_estilo, SR  # noqa: E402

RAIZ = reel.RAIZ
W, H, FPS = 1920, 1080, 30
XF = 0.4                                   # fundido entre planos (s)
PAUSA = 0.55                               # silencio entre párrafos
SAL = os.path.join(RAIZ, "salida", "largo")
SEG = os.path.join(SAL, "segmentos")
GUION = json.load(open(os.path.join(RAIZ, "largo", "guion_largo.json")))
PLANO = json.load(open(os.path.join(RAIZ, "largo", "plano_largo.json")))

BLANCO = (255, 255, 255)
AMARILLO = (255, 214, 0)
CIAN = (0, 229, 255)
MAGENTA = (255, 46, 196)
MORADO = (138, 63, 252)
FONDO_TARJ = (16, 10, 32, 225)

# teléfono (planos verticales)
PW, PH = 450, 800
PX, PY = 260, 92
PANEL = (840, 150, 1840, 880)            # zona libre a la derecha del teléfono

PRON_INV = {"Mister Bist": "MrBeast", "Sénsor Táuer": "Sensor Tower", "Cyberpunk dos mil setenta y siete": "Cyberpunk 2077",
            "Grass Rívers": "Grassrivers", "Port Guélhorn": "Port Gellhorn", "Boni y Claid": "Bonnie y Clyde",
            "Red Ded Redémpshon dos": "Red Dead Redemption 2", "Kik": "Kick", "Guórsoun": "Warzone",
            "Dédpul y Lobezno": "Deadpool y Lobezno", "Búbi Áik": "Boobie Ike", "Bráian Jéder": "Brian Heder", "Fil Cásidi": "Phil Cassidy", "Teik Tú": "Take-Two", "Cal Jámpton": "Cal Hampton", "Ci Yei": "CJ", "Bráian": "Brian", "Yi Nius": "GNews"}


# --------------------------------------------------------------------------
# tiempos
# --------------------------------------------------------------------------

def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ ]", "", s)


def duracion(ruta):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", ruta]))


def palabras(ruta_json, t0):
    al = json.load(open(ruta_json))["alineacion"]
    ws, cur, a, b = [], "", None, None
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if ch.isspace():
            if cur:
                ws.append([cur, a + t0, b + t0])
            cur, a = "", None
            continue
        if a is None:
            a = s
        cur += ch
        b = e
    if cur:
        ws.append([cur, a + t0, b + t0])
    # deshacer los cambios de pronunciación (varias palabras -> una)
    for pron, orig in PRON_INV.items():
        p = pron.split()
        i = 0
        while i <= len(ws) - len(p):
            if [norm(w[0]) for w in ws[i:i + len(p)]] == [norm(x) for x in p]:
                cola = re.sub(r"^.*?([^\wñáéíóúü]*)$", r"\1", ws[i + len(p) - 1][0])
                ws[i:i + len(p)] = [[orig + cola, ws[i][1], ws[i + len(p) - 1][2]]]
            i += 1
    return ws


def buscar(ws, frase, desde=0.0):
    obj = norm(frase)
    n = [norm(w[0]) for w in ws]
    for i in range(len(ws)):
        if ws[i][1] < desde - 0.01:
            continue
        acum = ""
        for j in range(i, len(ws)):
            acum = (acum + " " + n[j]).strip()
            if acum == obj:
                return ws[i][1], ws[j][2]
            if len(acum) >= len(obj):
                break
    raise ValueError(f"No encuentro «{frase}»")


def construir(cid):
    cap = next(c for c in GUION["capitulos"] if c["id"] == cid)
    lead = 2.4 if cap["titulo"] else 0.35
    t, pars = lead, []
    for i, txt in enumerate(cap["parrafos"]):
        base = os.path.join(RAIZ, "voz", "largo", f"{cid}_{i:02d}")
        d = duracion(base + ".wav")
        pars.append({"t0": t, "t1": t + d, "wav": base + ".wav", "ws": palabras(base + ".json", t), "texto": txt})
        t += d + PAUSA
    total = t - PAUSA + (0.9 if cid != "12_cierre" else 2.5)
    n = int(round(total * FPS))
    return {"cap": cap, "lead": lead, "pars": pars, "total": n / FPS, "n": n}


# --------------------------------------------------------------------------
# fondos (ffmpeg -> fotogramas RGB)
# --------------------------------------------------------------------------

def ruta(p):
    return p if os.path.isabs(p) else os.path.join(RAIZ, p)


class Plano:
    """Un plano de fondo: lo decodifica ffmpeg ya montado a 1920x1080."""

    def __init__(self, spec, n, semilla):
        self.spec, self.n, self.leidos, self.ult = spec, n, 0, None
        tipo, _, resto = spec.partition(":")
        self.vertical = tipo in ("v", "reel")
        rnd = random.Random(semilla)
        dur = n / FPS
        if tipo == "h":
            x = "(iw-ow)*t/%.3f" % dur if rnd.random() < 0.5 else "(iw-ow)*(1-t/%.3f)" % dur
            vf = (f"scale=2140:1196:flags=lanczos,crop=1920:1080:'{x}':'(ih-oh)/2',fps={FPS},"
                  "unsharp=5:5:0.5,eq=saturation=1.06")
            cmd = ["-i", ruta(resto), "-vf", vf]
        elif tipo == "img":
            z0, z1 = (1.0, 1.10) if rnd.random() < 0.6 else (1.10, 1.0)
            vf = (f"scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,"
                  f"zoompan=z='{z0}+({z1}-{z0})*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n + 5}:s=1920x1080:fps={FPS}")
            cmd = ["-loop", "1", "-framerate", str(FPS), "-i", ruta(resto), "-vf", vf]
        else:  # vertical dentro del teléfono
            partes = resto.split(":")
            src, ss = ruta(partes[0]), (["-ss", partes[1]] if len(partes) > 1 else [])
            tapa = ""
            if tipo == "reel":   # difumina los subtítulos quemados del reel original
                y1, hb = int(PH * 0.655), int(PH * 0.15)
                tapa = f",split[f1][f2];[f2]crop={PW}:{hb}:0:{y1},boxblur=14:3[bl];[f1][bl]overlay=0:{y1}"
            fc = (f"[0:v]fps={FPS},split[a][b];[a]scale=480:-2,crop=480:270,boxblur=12:2,scale=1920:1080,"
                  f"eq=brightness=-0.22:saturation=1.1[bg];[b]scale={PW}:{PH}:flags=lanczos,unsharp=5:5:0.6{tapa}[fg];"
                  f"[bg][fg]overlay={PX}:{PY}")
            cmd = ss + ["-stream_loop", "-1", "-i", src, "-filter_complex", fc]
        self.p = subprocess.Popen(["ffmpeg", "-v", "error"] + cmd + ["-frames:v", str(n), "-f", "rawvideo",
                                  "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

    def leer(self):
        if self.leidos < self.n:
            b = self.p.stdout.read(W * H * 3)
            if len(b) == W * H * 3:
                self.ult = np.frombuffer(b, np.uint8).reshape(H, W, 3)
            self.leidos += 1
        return self.ult

    def cerrar(self):
        try:
            self.p.stdout.close()
            self.p.kill()
        except Exception:
            pass


def dur_fuente(spec):
    tipo, _, resto = spec.partition(":")
    if tipo == "img":
        return 6.5
    partes = resto.split(":")
    d = duracion(ruta(partes[0]))
    if len(partes) > 2:
        return float(partes[2])
    return d - (float(partes[1]) if len(partes) > 1 else 0)


def lista_planos(info):
    """Reparte los fondos: cada tramo (desde un párrafo o frase) recorre su propia lista."""
    pl = PLANO[info["cap"]["id"]]
    total = info["total"]
    tramos = [(0.0, pl["fondos"])]
    for c in pl.get("fondos_cambios", []):
        p = info["pars"][c["p"]]
        t = buscar(p["ws"], c["en"])[0] - 0.25 if c.get("en") else p["t0"] - 0.3
        tramos.append((max(0.0, t), c["fondos"]))
    tramos.sort(key=lambda x: x[0])
    planos = []
    for k, (ini, fuentes) in enumerate(tramos):
        fin = tramos[k + 1][0] if k + 1 < len(tramos) else total
        t, i = ini, 0
        while t < fin - 0.05:
            spec = fuentes[i % len(fuentes)]
            i += 1
            d = min(dur_fuente(spec), 9.0)
            if fin - (t + d) < 1.6:          # no dejar un plano final ridículo
                d = fin - t
            planos.append((t, min(fin, t + d), spec))
            t += d
    return planos


# --------------------------------------------------------------------------
# elementos gráficos
# --------------------------------------------------------------------------

def caja(w, h, r=28, relleno=FONDO_TARJ, borde=MAGENTA, grosor=4):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), r, fill=relleno)
    if borde:
        d.rounded_rectangle((0, 0, w - 1, h - 1), r, outline=borde + (255,), width=grosor)
    return im


def texto(img, xy, s, tam, color=BLANCO, bold=True, ancla="la", borde=0):
    ImageDraw.Draw(img).text(xy, s, font=fuente(tam, bold), fill=color, anchor=ancla,
                             stroke_width=borde, stroke_fill=(0, 0, 0))


def telefono():
    m = 16
    im = Image.new("RGBA", (PW + 2 * m, PH + 2 * m), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), 58, fill=(8, 6, 14, 255))
    hueco = Image.new("L", im.size, 0)
    ImageDraw.Draw(hueco).rounded_rectangle((m, m, m + PW - 1, m + PH - 1), 44, fill=255)
    a = np.array(im.getchannel("A"))
    a[np.array(hueco) > 0] = 0
    im.putalpha(Image.fromarray(a))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), 58, outline=(90, 70, 140, 255), width=3)
    d.rounded_rectangle((im.width // 2 - 60, m + 12, im.width // 2 + 60, m + 34), 11, fill=(8, 6, 14, 255))
    sombra = Image.new("RGBA", (im.width + 80, im.height + 80), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((40, 50, im.width + 40, im.height + 50), 58, fill=(0, 0, 0, 150))
    sombra = sombra.filter(ImageFilter.GaussianBlur(22))
    sombra.alpha_composite(im, (40, 40))
    a = np.array(sombra.getchannel("A"))
    h_ = np.array(hueco) > 0
    a[40:40 + im.height, 40:40 + im.width][h_] = 0
    sombra.putalpha(Image.fromarray(a))
    return sombra, (PX - m - 40, PY - m - 40)


def envolver(s, f, ancho):
    lineas, cur = [], ""
    for w in s.replace(" · ", "\u00a0· ").split(" "):
        prueba = (cur + " " + w).strip()
        if f.getlength(prueba) <= ancho or not cur:
            cur = prueba
        else:
            lineas.append(cur)
            cur = w
    if cur:
        lineas.append(cur)
    return lineas


# ---- tarjetas y gráficos: cada uno es f(progreso 0..1) -> RGBA ----

def g_cifra(ov, p, ancho=900):
    """Cifra grande con subtítulo (p.ej. 90 MILLONES / de visitas en 24 h)."""
    f1 = ajustar_fuente(ov["texto"], ancho - 80, 120, tam_min=60)
    lineas = envolver(ov.get("sub", ""), fuente(40, False), ancho - 80)
    h = 70 + f1.size + 20 + 52 * len(lineas) + 40
    im = caja(ancho, h)
    d = ImageDraw.Draw(im)
    d.rectangle((40, 34, 140, 42), fill=CIAN)
    texto(im, (40, 56), ov["texto"], f1.size, AMARILLO if ov.get("color") != "cian" else CIAN)
    for i, l in enumerate(lineas):
        texto(im, (40, 70 + f1.size + 20 + 52 * i), l, 40, BLANCO, bold=False)
    return im


def g_barras(ov, p, ancho=1000, alto=700):
    im = caja(ancho, alto)
    texto(im, (50, 44), ov["titulo"], 44, BLANCO)
    barras = ov["barras"]
    vmax = max(b[1] for b in barras)
    y = 150
    hb = (alto - 200) // len(barras)
    for i, (nombre, v, etiqueta) in enumerate(barras):
        pp = reel.ease_out_cubic(reel.clamp((p * 1.6) - i * 0.25))
        largo = int((ancho - 120) * v / vmax * pp)
        col = [AMARILLO, MAGENTA, CIAN, MORADO][i % 4]
        texto(im, (50, y), nombre, 34, (220, 215, 240), bold=False)
        ImageDraw.Draw(im).rounded_rectangle((50, y + 48, 50 + max(largo, 12), y + 48 + hb - 100), 12, fill=col + (255,))
        if pp > 0.05:
            ym = y + 48 + (hb - 100) // 2
            if largo < ancho - 360:
                texto(im, (70 + largo, ym), etiqueta, 40, BLANCO, ancla="lm")
            else:
                texto(im, (30 + largo, ym), etiqueta, 40, (20, 10, 30), ancla="rm")
        y += hb
    if ov.get("nota"):
        texto(im, (50, alto - 56), ov["nota"], 28, (190, 180, 210), bold=False)
    return im


def g_precio(ov, p, ancho=1000, alto=700):
    im = caja(ancho, alto)
    d = ImageDraw.Draw(im)
    texto(im, (50, 44), ov["titulo"], 44, BLANCO)
    for i, (nombre, precio) in enumerate(ov["precios"]):
        pp = reel.ease_out_back(reel.clamp(p * 2 - i * 0.3))
        if pp <= 0:
            continue
        x, y = 60 + i * 300, 150
        etq = Image.new("RGBA", (260, 200), (0, 0, 0, 0))
        de = ImageDraw.Draw(etq)
        de.rounded_rectangle((0, 0, 259, 199), 22, fill=(MORADO if i == 0 else MAGENTA) + (255,))
        texto(etq, (130, 70), precio, 64, BLANCO, ancla="mm")
        texto(etq, (130, 150), nombre, 30, BLANCO, bold=False, ancla="mm")
        etq = etq.resize((max(1, int(260 * pp)), max(1, int(200 * pp))))
        im.alpha_composite(etq, (x + (260 - etq.width) // 2, y + (200 - etq.height) // 2))
    # anillo de porcentaje
    pc = ov["porcentaje"] * reel.ease_out_cubic(reel.clamp(p * 1.4 - 0.4))
    cx, cy, r = 790, 255, 120
    d.arc((cx - r, cy - r, cx + r, cy + r), 0, 360, fill=(60, 50, 90), width=34)
    if pc > 0:
        d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * pc / 100, fill=AMARILLO, width=34)
    texto(im, (cx, cy), f"{int(round(pc))}%", 64, BLANCO, ancla="mm")
    for i, l in enumerate(envolver(ov["sub"], fuente(38, False), ancho - 110)):
        texto(im, (50, 440 + 54 * i), l, 38, BLANCO, bold=False)
    if ov.get("nota"):
        texto(im, (50, alto - 56), ov["nota"], 28, (190, 180, 210), bold=False)
    return im


def g_linea(ov, p, ancho=1000, alto=700):
    """Línea de tiempo con hitos; los tachados llevan una X roja."""
    im = caja(ancho, alto)
    d = ImageDraw.Draw(im)
    texto(im, (50, 44), ov["titulo"], 44, BLANCO)
    hitos = ov["hitos"]
    y0, x0, x1 = 360, 110, ancho - 110
    pp = reel.clamp(p * 1.3)
    d.line((x0, y0, x0 + (x1 - x0) * pp, y0), fill=(120, 100, 170), width=8)
    for i, (fecha, nota, tachado) in enumerate(hitos):
        x = x0 + (x1 - x0) * i / (len(hitos) - 1)
        q = reel.clamp((pp - i / (len(hitos) - 1)) * 6 + 0.001)
        if pp + 0.01 < i / (len(hitos) - 1):
            continue
        r = 26
        col = (255, 70, 90) if tachado else (60, 230, 120)
        d.ellipse((x - r, y0 - r, x + r, y0 + r), fill=col)
        texto(im, (x, y0 - 70), fecha, 40, BLANCO, ancla="mb")
        for k, l in enumerate(envolver(nota, fuente(30, False), 280)):
            texto(im, (x, y0 + 60 + 40 * k), l, 30, (210, 205, 230), bold=False, ancla="mt")
        if tachado and q > 0.5:
            d.line((x - 60, y0 - 130, x + 60, y0 - 50), fill=(255, 70, 90), width=10)
            d.line((x - 60, y0 - 50, x + 60, y0 - 130), fill=(255, 70, 90), width=10)
    return im


def g_lista(ov, p, ancho=1000, alto=700, tvis=None):
    """Lista numerada: cada punto aparece cuando se nombra (tvis = cuántos visibles)."""
    im = caja(ancho, alto)
    texto(im, (50, 44), ov["titulo"], 44, BLANCO)
    y = 140
    for i, item in enumerate(ov["items"]):
        if i >= (tvis or 0):
            continue
        d = ImageDraw.Draw(im)
        d.ellipse((50, y, 120, y + 70), fill=(MAGENTA if i % 2 == 0 else MORADO))
        texto(im, (85, y + 35), str(i + 1), 40, BLANCO, ancla="mm")
        for k, l in enumerate(envolver(item, fuente(38), ancho - 200)):
            texto(im, (150, y + 14 + 46 * k), l, 38, BLANCO if i == tvis - 1 else (200, 195, 220))
        y += max(120, 46 * len(envolver(item, fuente(38), ancho - 200)) + 50)
    return im


def g_tabla(ov, p, ancho=1000, alto=700):
    im = caja(ancho, alto)
    texto(im, (50, 44), ov["titulo"], 44, BLANCO)
    filas = ov["filas"]
    y = 140
    hf = (alto - 180) // len(filas)
    for i, (pais, hora, dia) in enumerate(filas):
        q = reel.ease_out_cubic(reel.clamp(p * 2.2 - i * 0.25))
        if q <= 0:
            continue
        capa = Image.new("RGBA", (ancho - 80, hf - 14), (0, 0, 0, 0))
        dc = ImageDraw.Draw(capa)
        dc.rounded_rectangle((0, 0, capa.width - 1, capa.height - 1), 16,
                             fill=((70, 30, 120, 230) if i == 0 else (35, 25, 60, 220)))
        texto(capa, (30, capa.height // 2), pais, 40, BLANCO, ancla="lm")
        texto(capa, (capa.width - 220, capa.height // 2), hora, 52, AMARILLO if i == 0 else CIAN, ancla="rm")
        texto(capa, (capa.width - 30, capa.height // 2), dia, 30, (200, 195, 220), bold=False, ancla="rm")
        capa.putalpha(capa.getchannel("A").point(lambda v: int(v * q)))
        im.alpha_composite(capa, (40 + int((1 - q) * 60), y))
        y += hf
    return im


def g_pregunta(ov, p, ancho=900):
    lineas = envolver(ov["texto"], fuente(54), ancho - 200)
    h = 120 + 66 * len(lineas)
    im = caja(ancho, h, borde=AMARILLO)
    d = ImageDraw.Draw(im)
    # icono de bocadillo
    d.rounded_rectangle((40, 40, 140, 110), 18, fill=AMARILLO)
    d.polygon([(64, 108), (60, 134), (92, 108)], fill=AMARILLO)
    for k in range(3):
        d.ellipse((62 + k * 26, 68, 76 + k * 26, 82), fill=(30, 20, 50))
    for i, l in enumerate(lineas):
        texto(im, (170, 50 + 66 * i), l, 54, BLANCO)
    texto(im, (170, 50 + 66 * len(lineas) + 4), ov.get("sub", "Respóndeme en los comentarios"), 30, AMARILLO, bold=False)
    return im


def g_etiqueta(ov, p):
    """Rótulo corto de lugar o nombre (p.ej. VICE CITY)."""
    f = ajustar_fuente(ov["texto"], 900, 76, tam_min=44)
    t = texto_con_estilo(ov["texto"], f, BLANCO, borde=0, sombra=True)
    sub = ov.get("sub")
    w = max(t.width, int(fuente(36, False).getlength(sub or "")) + 90) + 20
    im = Image.new("RGBA", (w, t.height + (60 if sub else 0)), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((44, 24, 56, t.height - 30), fill=CIAN)
    im.alpha_composite(t, (30, 0))
    if sub:
        texto(im, (76, t.height - 30), sub, 36, AMARILLO, bold=False)
    return im


GRAF = {"cifra": g_cifra, "barras": g_barras, "precio": g_precio, "linea": g_linea, "lista": g_lista,
        "tabla": g_tabla, "pregunta": g_pregunta, "etiqueta": g_etiqueta}
GRANDES = ("barras", "precio", "linea", "lista", "tabla")


def tarjeta_capitulo(num, titulo):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = ajustar_fuente(titulo, 1500, 130, tam_min=70)
    t = texto_con_estilo(titulo, f, BLANCO, borde=0, brillo=(120, 40, 220))
    n = texto_con_estilo(f"{num:02d}", fuente(110), AMARILLO, sombra=True)
    franja = Image.new("RGBA", (W, 330), (12, 6, 26, 215))
    ImageDraw.Draw(franja).rectangle((0, 0, W, 6), fill=MAGENTA)
    ImageDraw.Draw(franja).rectangle((0, 324, W, 330), fill=CIAN)
    im.alpha_composite(franja, (0, (H - 330) // 2))
    im.alpha_composite(n, ((W - n.width) // 2, (H - 330) // 2 - 30))
    im.alpha_composite(t, ((W - t.width) // 2, (H - 330) // 2 + 120))
    return im


# --------------------------------------------------------------------------
# subtítulos
# --------------------------------------------------------------------------

def trozos(ws):
    out, cur = [], []
    for w in ws:
        cur.append(w)
        fin = re.search(r"[.,;:?!]$", w[0])
        largo = sum(len(x[0]) + 1 for x in cur)
        if (fin and len(cur) >= 3) or largo > 46 or (fin and w[0][-1] in ".?!"):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


class Subs:
    def __init__(self, pars):
        self.items = []
        for p in pars:
            for tr in trozos(p["ws"]):
                self.items.append((tr[0][1], tr[-1][2] + 0.25, tr))
        self.cache = {}

    def imagen(self, t):
        for a, b, tr in self.items:
            if a - 0.05 <= t < b:
                k = sum(1 for w in tr if w[1] <= t) - 1
                clave = (id(tr), k)
                if clave not in self.cache:
                    self.cache = {} if len(self.cache) > 40 else self.cache
                    self.cache[clave] = self.render(tr, k)
                return self.cache[clave]
        return None

    @staticmethod
    def render(tr, k):
        f = fuente(50)
        sp = f.getlength(" ")
        anchos = [f.getlength(w[0]) for w in tr]
        total = sum(anchos) + sp * (len(tr) - 1)
        im = Image.new("RGBA", (int(total) + 80, 110), (0, 0, 0, 0))
        sombra = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ds, d = ImageDraw.Draw(sombra), ImageDraw.Draw(im)
        x = 40
        for i, w in enumerate(tr):
            ds.text((x + 3, 33), w[0], font=f, fill=(0, 0, 0, 200), stroke_width=6, stroke_fill=(0, 0, 0, 200))
            x += anchos[i] + sp
        im.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(4)))
        x = 40
        for i, w in enumerate(tr):
            d.text((x, 28), w[0], font=f, fill=AMARILLO if i == k else BLANCO, stroke_width=5, stroke_fill=(0, 0, 0))
            x += anchos[i] + sp
        return im


# --------------------------------------------------------------------------
# render de un capítulo
# --------------------------------------------------------------------------

def overlays_capitulo(info):
    """Resuelve los tiempos de los rótulos a partir de las frases de la locución."""
    out = []
    for ov in PLANO[info["cap"]["id"]].get("overlays", []):
        p = info["pars"][ov["p"]]
        a = buscar(p["ws"], ov["en"])[0] if ov.get("en") else p["t0"]
        if ov.get("hasta"):
            b = buscar(p["ws"], ov["hasta"], a)[1] + 0.3
        elif ov.get("hasta_p") is not None:
            b = info["pars"][ov["hasta_p"]]["t1"] + 0.2
        elif ov.get("dur"):
            b = a + ov["dur"]
        else:
            b = p["t1"] + 0.2
        o = dict(ov, a=a - 0.15, b=b)
        if ov["tipo"] == "lista":
            o["marcas"] = [buscar(info["pars"][ov.get("p_items", [ov["p"]] * 9)[i]]["ws"], fr)[0]
                           for i, fr in enumerate(ov["marcas"])]
        out.append(o)
    return out


def render_capitulo(cid):
    info = construir(cid)
    os.makedirs(SEG, exist_ok=True)
    salida = os.path.join(SEG, f"{cid}.mp4")
    planos = lista_planos(info)
    ovs = overlays_capitulo(info)
    subs = Subs(info["pars"])
    num = [c["id"] for c in GUION["capitulos"] if c["titulo"]].index(cid) + 1 if info["cap"]["titulo"] else 0
    card = tarjeta_capitulo(num, info["cap"]["titulo"]) if num else None
    tel, tel_pos = telefono()
    logo = Image.open(os.path.join(RAIZ, "marca", "gnews_logo_transparente.png")).convert("RGBA")
    logo = logo.resize((int(logo.width * 64 / logo.height), 64), Image.LANCZOS)
    logo.putalpha(logo.getchannel("A").point(lambda v: int(v * 0.85)))
    pill = None
    if num:
        s = f"{num:02d} · {info['cap']['titulo']}"
        f = fuente(28)
        pill = caja(int(f.getlength(s)) + 50, 54, r=27, relleno=(16, 10, 32, 190), borde=None)
        texto(pill, (25, 27), s, 28, BLANCO, ancla="lm")
    tema = None
    if num:
        tema = Image.new("RGBA", (PANEL[2] - PANEL[0], 400), (0, 0, 0, 0))
        texto(tema, (0, 120), f"{num:02d}", 90, AMARILLO)
        for i, l in enumerate(envolver(info["cap"]["titulo"], fuente(84), PANEL[2] - PANEL[0] - 40)):
            texto(tema, (0, 230 + 96 * i), l, 84, BLANCO)
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", salida], stdin=subprocess.PIPE)
    abiertos = {}
    cache_g = {}
    for fi in range(info["n"]):
        t = fi / FPS
        # ---------- fondo con fundidos
        activos = [(i, pl) for i, pl in enumerate(planos) if pl[0] - 1e-6 <= t < pl[1] + (XF if i < len(planos) - 1 else 0)]
        capas = []
        for i, (a, b, spec) in activos:
            if i not in abiertos:
                n = int(round((b - a + XF) * FPS)) + 2
                abiertos[i] = Plano(spec, n, hash((cid, i)) & 0xffff)
            capas.append((i, abiertos[i].leer(), a, b))
        for i in list(abiertos):
            if i not in [x[0] for x in activos]:
                abiertos.pop(i).cerrar()
        base = capas[0][1].astype(np.float32) if capas[0][1] is not None else np.zeros((H, W, 3), np.float32)
        vertical = abiertos[capas[0][0]].vertical
        if len(capas) > 1 and capas[1][1] is not None:
            k = reel.clamp((t - capas[0][3]) / XF)
            base = base * (1 - k) + capas[1][1].astype(np.float32) * k
            if k > 0.5:
                vertical = abiertos[capas[1][0]].vertical
        # ---------- rótulos activos
        act = [o for o in ovs if o["a"] <= t < o["b"]]
        grande = any(o["tipo"] in GRANDES for o in act)
        oscuro = 0.0
        if grande and not vertical:
            oscuro = 0.45
        if card is not None and t < info["lead"] + 0.4:
            oscuro = max(oscuro, 0.35 * (1 - reel.clamp((t - info["lead"]) / 0.4)))
        if oscuro:
            base *= (1 - oscuro)
        # viñeta inferior para los subtítulos
        base[H - 260:] *= VINETA
        img = Image.fromarray(base.clip(0, 255).astype(np.uint8))
        if vertical:
            img.paste(tel, tel_pos, tel)
            if tema is not None and not act and t > info["lead"]:
                img.paste(tema, (PANEL[0], PANEL[1]), tema)
        for o in act:
            dur_in = 0.35
            q = reel.clamp((t - o["a"]) / dur_in)
            sal = reel.clamp((o["b"] - t) / 0.25)
            prog = reel.clamp((t - o["a"]) / 1.4)
            clave = (id(o), o.get("_vis"))
            if o["tipo"] == "lista":
                vis = sum(1 for m in o["marcas"] if m - 0.1 <= t)
                capa = cache_g.get((id(o), vis)) or cache_g.setdefault((id(o), vis), g_lista(o, 1, tvis=vis))
            elif prog < 1 and o["tipo"] in ("barras", "precio", "linea", "tabla"):
                capa = GRAF[o["tipo"]](o, prog)
            else:
                if clave not in cache_g:
                    cache_g[clave] = GRAF[o["tipo"]](o, 1.0)
                capa = cache_g[clave]
            esc = 0.85 + 0.15 * reel.ease_out_back(q)
            alfa = min(q, sal)
            if o["tipo"] in GRANDES:
                if vertical:
                    cx, cy = (PANEL[0] + PANEL[2]) // 2, (PANEL[1] + PANEL[3]) // 2
                else:
                    cx, cy = W // 2, 470
            elif o["tipo"] == "etiqueta":
                cx, cy = (PANEL[0] + capa.width // 2 + 20, 300) if vertical else (90 + capa.width // 2, 200)
            elif o["tipo"] == "pregunta":
                cx, cy = ((PANEL[0] + PANEL[2]) // 2, 480) if vertical else (W // 2, 470)
            else:  # cifra
                cx, cy = ((PANEL[0] + PANEL[2]) // 2, 480) if vertical else (90 + capa.width // 2, 560)
            if abs(esc - 1) > 0.01:
                capa = capa.resize((max(1, int(capa.width * esc)), max(1, int(capa.height * esc))), Image.BILINEAR)
            if alfa < 0.99:
                capa = capa.copy()
                capa.putalpha(capa.getchannel("A").point(lambda v, a_=alfa: int(v * a_)))
            img.paste(capa, (int(cx - capa.width / 2), int(cy - capa.height / 2)), capa)
        # ---------- tarjeta de capítulo
        if card is not None and t < info["lead"] + 0.5:
            q = reel.ease_out_cubic(reel.clamp(t / 0.45))
            s = reel.clamp((info["lead"] + 0.5 - t) / 0.4)
            c = card
            if min(q, s) < 0.99:
                c = card.copy()
                c.putalpha(c.getchannel("A").point(lambda v, a_=min(q, s): int(v * a_)))
            img.paste(c, (int((1 - q) * -200), 0), c)
        # ---------- marca, píldora y subtítulos
        img.paste(logo, (44, 36), logo)
        if pill is not None and t > info["lead"] + 0.3:
            img.paste(pill, (W - pill.width - 44, 40), pill)
        s = subs.imagen(t)
        if s is not None:
            img.paste(s, ((W - s.width) // 2, H - 150), s)
        enc.stdin.write(img.tobytes())
    for p in abiertos.values():
        p.cerrar()
    enc.stdin.close()
    enc.wait()
    return cid, info["total"]


VINETA = np.linspace(1.0, 0.55, 260, dtype=np.float32)[:, None, None]


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------

def leer_wav(ruta_):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", ruta_, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"])
    return np.frombuffer(raw, np.float32).astype(np.float64)


def chill(total, bpm=88):
    """Base tranquila original (variante de la música nostálgica, más luminosa)."""
    return reel.musica_nostalgia(total, bpm)


def audio(capitulos, ruta_):
    infos = [construir(c) for c in capitulos]
    total = sum(i["total"] for i in infos)
    N = int(total * SR) + SR
    voz = np.zeros(N)
    mus = np.zeros(N)
    fx = np.zeros(N)
    rng = np.random.default_rng(3)
    off = 0.0
    for info in infos:
        cid = info["cap"]["id"]
        for p in info["pars"]:
            reel.pegar(voz, (off + p["t0"]) * SR, leer_wav(p["wav"]))
        estilo = PLANO[cid].get("musica", "chill")
        d = info["total"] + 1.0
        m = {"trap": lambda: reel.musica(d, 140) * 0.55, "nostalgia": lambda: reel.musica_nostalgia(d, 80),
             "chill": lambda: chill(d)}[estilo]()
        m = m / (np.sqrt(np.mean(m ** 2)) + 1e-9)
        L = len(m)
        env = np.ones(L)
        fade = int(0.8 * SR)
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        nivel = np.full(L, 0.028)
        # más música en la tarjeta del capítulo, menos bajo la voz
        a = int(max(0, info["lead"] - 0.2) * SR)
        nivel[:a] = 0.09
        nivel[a:a + int(0.6 * SR)] = np.linspace(0.09, 0.028, len(nivel[a:a + int(0.6 * SR)]))
        if cid == "12_cierre":
            fin = int(info["pars"][-1]["t1"] * SR)
            nivel[fin:] = np.linspace(0.028, 0.09, max(1, L - fin))
        reel.pegar(mus, (off - 0.3) * SR, m * env * nivel)
        if info["cap"]["titulo"]:
            reel.pegar(fx, (off + 0.05) * SR, reel.sfx_whoosh(rng, 0.55), 0.35)
        off += info["total"]
    voz_rms = np.sqrt(np.mean(voz[np.abs(voz) > 1e-4] ** 2))
    mezcla = voz + mus * (voz_rms / 0.1) * 1.0 + fx * voz_rms * 3
    mezcla /= max(1e-9, np.abs(mezcla).max()) / 0.9
    tmp = os.path.join(SAL, "_mezcla.wav")
    import wave
    with wave.open(tmp, "wb") as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(SR)
        wv.writeframes((mezcla * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp, "-af",
                    "highpass=f=60,acompressor=threshold=-18dB:ratio=2:attack=5:release=120,loudnorm=I=-14:TP=-1.5:LRA=9",
                    "-ar", "48000", "-ac", "2", ruta_], check=True)
    os.remove(tmp)
    return infos


def capitulos_y_marcas(infos):
    t, out = 0.0, []
    for i in infos:
        out.append((t, i["cap"]["titulo"] or ("Intro" if i["cap"]["id"] == "00_intro" else "Cierre")))
        t += i["total"]
    return out


def srt(infos, ruta_):
    off, k, lineas = 0.0, 1, []

    def ts(x):
        return f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(x * 1000 % 1000):03d}"
    for info in infos:
        for p in info["pars"]:
            for tr in trozos(p["ws"]):
                lineas.append(f"{k}\n{ts(off + tr[0][1])} --> {ts(off + tr[-1][2] + 0.2)}\n{' '.join(w[0] for w in tr)}\n")
                k += 1
        off += info["total"]
    open(ruta_, "w").write("\n".join(lineas))


def unir(capitulos):
    os.makedirs(SAL, exist_ok=True)
    infos = audio(capitulos, os.path.join(SAL, "audio.wav"))
    with open(os.path.join(SEG, "lista.txt"), "w") as f:
        for c in capitulos:
            f.write(f"file '{os.path.join(SEG, c + '.mp4')}'\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(SEG, "lista.txt"),
                    "-i", os.path.join(SAL, "audio.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                    os.path.join(SAL, "video.mp4")], check=True)
    srt(infos, os.path.join(SAL, "subtitulos.srt"))
    for t, n in capitulos_y_marcas(infos):
        print(f"{int(t // 60)}:{int(t % 60):02d} {n}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--capitulos", nargs="*")
    ap.add_argument("--unir", action="store_true")
    ap.add_argument("--procesos", type=int, default=4)
    a = ap.parse_args()
    todos = [c["id"] for c in GUION["capitulos"]]
    caps = a.capitulos or todos
    if not a.unir:
        with Pool(a.procesos) as pool:
            for cid, d in pool.imap_unordered(render_capitulo, sorted(caps, key=lambda c: -construir(c)["total"])):
                print("ok", cid, round(d, 1), flush=True)
    if a.unir or not a.capitulos:
        unir(todos)
