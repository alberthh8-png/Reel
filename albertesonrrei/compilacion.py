#!/usr/bin/env python3
"""Recopilatorio vertical para Albertesonrrei: "El directo más pobre de Twitch".

Une varios momentos de un directo (cámara arriba, partida/menú en el centro, karaoke con su voz),
con voz grave y lenta + zoom en las expresiones malsonantes, stickers por momento y transiciones.

La configuración (momentos, tiempos, stickers) está en MOMENTOS. Uso:
    python3 albertesonrrei/compilacion.py --dir DIR_TWITCH --salida salida/albertesonrrei/pobre [--preview 1 5 9]
DIR_TWITCH contiene frB/ frC→fr/ frD/ (JPG a 60 fps), segB.wav, segC.wav, segD.wav y tB/tC/tD.json.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import wave
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from albertesonrrei.efectos import VEL_GRAVE, frase_lenta, voz_grave  # noqa: E402
from reel import ajustar_fuente, clamp, ease_out_back, ease_out_cubic, fuente, pegar_centrado, texto_con_estilo  # noqa: E402

W, H, FPS = 1080, 1920, 60
CAM = (46, 230, 314, 378)
JUEGO = (335, 0, 1145, 720)
Y_CAM, H_CAM = 300, 597
Y_JUEGO, H_JUEGO = 900, 960
LENTO = VEL_GRAVE
TRANS = 0.3
ROSA, AMARILLO, BLANCO, OSCURO, VERDE = (255, 61, 139), (255, 210, 63), (255, 255, 255), (12, 8, 24), (60, 230, 120)
MALSONANTES = {"culo", "mierda", "puta", "puto", "putas", "putos", "joder", "coño", "polla", "pinga", "verga",
               "cabrón", "cabron", "cabrones", "cabronazo", "gilipollas", "hostia", "hostias", "cago"}
CENSURA = {"culo": "c•lo", "mierda": "m•••da", "puta": "p•ta", "puto": "p•to", "joder": "j•der", "coño": "c•ño",
           "polla": "p•lla", "pinga": "p•nga", "verga": "v•rga", "cabrón": "c•brón", "gilipollas": "g•lipollas",
           "hostia": "h•stia", "hostias": "h•stias", "cabrones": "c•brones", "cabronazo": "c•bronazo",
           "pinga": "p•nga", "cago": "c•go"}

# s = segundo dentro de cada tramo descargado (segX.mp4); stt = desplazamiento para pasar de la transcripción a s
MOMENTOS = [
    dict(id="novia", frames="frD", s_frames=10.5, wav="segD.wav", palabras="tD.json", stt=9230 - 9405,
         s0=11.0, s1=31.0,
         stickers=[dict(tipo="chat", s=13.9, hasta=19.0, texto="Alberte, tengo novia, tiene 86 años, es millonaria")],
         zooms=[]),
    dict(id="ventilador", frames="frB", s_frames=7.0, wav="segB.wav", palabras="tB.json", stt=4680 - 4685,
         s0=7.4, s1=25.7,
         stickers=[dict(tipo="ventilador", s=11.2)],
         zooms=[18.2]),
    dict(id="var", frames="fr", s_frames=112.0, wav="segC.wav", palabras="tC.json", stt=6020 - 6045,
         s0=131.0, s1=150.6,
         stickers=[dict(tipo="var", s=144.3)], golpe=134.0, zooms=[133.8]),
]


TITULOS = ("EL DIRECTO MÁS POBRE", "DE TWITCH")


FORMATO = "camara"   # "camara": cámara grande arriba · "juego": la partida ocupa casi todo y la cámara va pequeña
# formato "juego" (pedido por Albert el 20 nov): partida 4:5 a todo el ancho, cámara en miniatura y subtítulos debajo
Y_J2, H_J2 = 290, 1350
JUEGO2 = (352, 0, 928, 720)          # 576x720 del centro de la partida (sin el chat de la izquierda)
PIP_W, PIP_H, PIP_X, PIP_Y = 330, 186, 1080 - 330 - 28, 290 + 26
Y_SUBS2 = 1785


def cargar_config(ruta):
    """Lee momentos y títulos de un JSON (si no, se usan los de "El directo más pobre")."""
    global MOMENTOS, TITULOS, FORMATO
    cfg = json.load(open(ruta))
    MOMENTOS = cfg["momentos"]
    TITULOS = tuple(cfg["titulos"])
    FORMATO = cfg.get("formato", "camara")


def limpia(txt):
    return txt.lower().strip(".,;:!?¡¿«»\"'-")


class Linea:
    """Línea de tiempo: tramos (momento, s0, s1, velocidad) en orden, con transiciones."""

    def __init__(self, dir_):
        self.tramos = []
        self.lentos = []
        self.cortes = []
        self.palabras = {}
        u = 0.0
        for m in MOMENTOS:
            ws = [w for w in json.load(open(os.path.join(dir_, m["palabras"])))["words"] if w.get("type") == "word"]
            self.palabras[m["id"]] = ws
            feas = []
            for k, w in enumerate(ws):
                if limpia(w["text"]) not in MALSONANTES:
                    continue
                ini, fin, _, _ = frase_lenta(ws, k)  # la frase entera, no solo la palabra
                a = max(ini + m["stt"] - 0.04, m["s0"])
                b = min(fin + m["stt"] + 0.1, m["s1"])
                if a < b and m["s0"] <= a < m["s1"] and m["s0"] <= w["start"] + m["stt"] <= m["s1"]:
                    if feas and a < feas[-1][1]:
                        feas[-1] = (feas[-1][0], max(b, feas[-1][1]))
                    else:
                        feas.append((a, b))
            if "graves" in m:  # frases elegidas a mano: solo esas van con voz grave
                feas = [(max(a, m["s0"]), min(b, m["s1"])) for a, b in m["graves"] if m["s0"] <= a < m["s1"]]
            if self.tramos and not m.get("suave"):
                self.cortes.append(u)
            s = m["s0"]
            for a, b in feas:
                if a > s:
                    self.tramos.append((u, m, s, a, 1.0))
                    u += a - s
                self.tramos.append((u, m, a, b, LENTO))
                self.lentos.append((u, u + (b - a) / LENTO))
                u += (b - a) / LENTO
                s = b
            self.tramos.append((u, m, s, m["s1"], 1.0))
            u += m["s1"] - s
        self.total = u

    def en(self, u):
        for u0, m, s0, s1, v in reversed(self.tramos):
            if u >= u0:
                return m, min(s1, s0 + (u - u0) * v)
        u0, m, s0, s1, v = self.tramos[0]
        return m, s0

    def u_de(self, mid, s):
        for u0, m, s0, s1, v in self.tramos:
            if m["id"] == mid and s0 <= s <= s1:
                return u0 + (s - s0) / v
        return None


class Editor:
    def __init__(self, dir_):
        self.dir = dir_
        self.L = Linea(dir_)
        self.titulo1 = texto_con_estilo(TITULOS[0], ajustar_fuente(TITULOS[0], 940, 78, tam_min=48, borde=10), AMARILLO + (255,), borde=10,
                                        color_borde=OSCURO, brillo=ROSA)
        self.titulo2 = texto_con_estilo(TITULOS[1], ajustar_fuente(TITULOS[1], 940, 64, tam_min=40, borde=8), BLANCO + (255,), borde=8, color_borde=OSCURO)
        self.fondo = Image.new("RGB", (W, H), (13, 9, 24))
        d = ImageDraw.Draw(self.fondo)
        if FORMATO == "juego":
            d.rectangle((0, Y_J2 - 6, W, Y_J2 - 1), fill=ROSA)
            d.rectangle((0, Y_J2 + H_J2, W, Y_J2 + H_J2 + 5), fill=ROSA)
        else:
            d.rectangle((0, Y_CAM - 6, W, Y_CAM - 1), fill=ROSA)
            d.rectangle((0, Y_JUEGO - 3, W, Y_JUEGO + 2), fill=ROSA)
        mask = Image.new("L", (PIP_W, PIP_H), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, PIP_W - 1, PIP_H - 1), 22, fill=255)
        self.pip_mask = mask
        self.st = {"var": self._var(), "ventilador": self._ventilador()}
        self.chat = {}
        self.bloques = self._bloques()

    # --- stickers ---
    def _caja(self, w, h, relleno=(20, 20, 30, 255), borde=BLANCO):
        img = Image.new("RGBA", (w + 40, h + 50), (0, 0, 0, 0))
        sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sombra).rounded_rectangle((26, 30, w + 26, h + 30), radius=30, fill=(0, 0, 0, 160))
        img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(10)))
        ImageDraw.Draw(img).rounded_rectangle((20, 20, w + 20, h + 20), radius=30, fill=relleno,
                                              outline=borde + (255,), width=5)
        return img

    def _var(self):
        img = self._caja(560, 150)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((45, 45, 165, 145), radius=12, outline=BLANCO + (255,), width=6)
        d.line((80, 145, 70, 160), fill=BLANCO + (255,), width=6)
        d.line((130, 145, 140, 160), fill=BLANCO + (255,), width=6)
        d.text((105, 95), "VAR", font=fuente(40), fill=AMARILLO + (255,), anchor="mm")
        d.text((195, 70), "VAR", font=fuente(56), fill=BLANCO + (255,), anchor="lm")
        d.text((195, 130), "REVISANDO", font=fuente(44), fill=(255, 80, 80, 255), anchor="lm")
        return img

    def _ventilador(self):
        img = self._caja(820, 150, relleno=(255, 255, 255, 255), borde=(20, 20, 30))
        d = ImageDraw.Draw(img)
        cx, cy = 100, 95  # ventilador dibujado
        d.ellipse((cx - 55, cy - 55, cx + 55, cy + 55), outline=(20, 20, 30, 255), width=6)
        for k in range(3):
            a = math.radians(k * 120)
            d.ellipse((cx + 28 * math.cos(a) - 18, cy + 28 * math.sin(a) - 18, cx + 28 * math.cos(a) + 18,
                       cy + 28 * math.sin(a) + 18), fill=(45, 120, 255, 255))
        d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(20, 20, 30, 255))
        d.text((180, 70), "CÁMARA APOYADA", font=fuente(50), fill=(20, 12, 30, 255), anchor="lm")
        d.text((180, 128), "EN UN VENTILADOR", font=fuente(50), fill=(45, 120, 255, 255), anchor="lm")
        return img

    def _texto(self, lineas):
        k = tuple(lineas)
        if k not in self.chat:
            img = self._caja(820, 40 + 66 * len(lineas), relleno=(255, 255, 255, 255), borde=(20, 20, 30))
            d = ImageDraw.Draw(img)
            for i, l in enumerate(lineas):
                d.text((430, 75 + 66 * i), l, font=fuente(54), fill=((20, 12, 30) if i == 0 else (230, 40, 70)) + (255,),
                       anchor="mm")
            self.chat[k] = img
        return self.chat[k]

    def _chat(self, texto):
        if texto not in self.chat:
            f = fuente(44)
            lineas, act = [], ""
            for p in texto.split():
                prueba = (act + " " + p).strip()
                if f.getbbox(prueba)[2] > 760:
                    lineas.append(act)
                    act = p
                else:
                    act = prueba
            lineas.append(act)
            img = self._caja(860, 90 + 58 * len(lineas), relleno=(24, 22, 38, 245), borde=(145, 70, 255))
            d = ImageDraw.Draw(img)
            d.text((60, 62), "CHAT", font=fuente(36), fill=(145, 70, 255, 255), anchor="lm")
            for k, l in enumerate(lineas):
                d.text((60, 115 + 58 * k), l, font=f, fill=BLANCO + (255,), anchor="lm")
            self.chat[texto] = img
        return self.chat[texto]

    # --- subtítulos ---
    def _bloques(self):
        bloques = []
        for m in MOMENTOS:
            act = []
            for w in self.L.palabras[m["id"]]:
                s0, s1 = w["start"] + m["stt"], w["end"] + m["stt"]
                if s0 < m["s0"] - 0.1 or s0 > m["s1"]:
                    continue
                txt = w["text"].strip()
                base = limpia(txt)
                if base in CENSURA:
                    txt = txt.lower().replace(base, CENSURA[base])
                u0 = self.L.u_de(m["id"], max(s0, m["s0"]))
                u1 = self.L.u_de(m["id"], min(s1, m["s1"]))
                if u0 is None or u1 is None:
                    continue
                act.append((txt, u0, u1))
                if len(act) >= 3 or txt.endswith((".", "?", "!", ",")):
                    bloques.append(act)
                    act = []
            if act:
                bloques.append(act)
        return bloques

    def _subs(self, frame, u):
        bloque = None
        for k, b in enumerate(self.bloques):
            sig = self.bloques[k + 1][0][1] if k + 1 < len(self.bloques) else self.L.total + 1
            if b[0][1] - 0.03 <= u < min(b[-1][2] + 0.4, sig - 0.03):
                bloque = b
        if bloque is None:
            return
        f = fuente(72)
        palabras = [p.upper() for p, _, _ in bloque]
        anchos = [f.getbbox(p, stroke_width=8)[2] for p in palabras]
        esp = 22
        total = sum(anchos) + esp * (len(palabras) - 1)
        esc = min(1.0, (W - 200) / total)
        x = (W - total * esc) / 2
        for (p, a, b), txt, w in zip(bloque, palabras, anchos):
            ac = a <= u < b + 0.05
            capa = texto_con_estilo(txt, f, (AMARILLO if ac else BLANCO) + (255,), borde=9, color_borde=(0, 0, 0))
            ys = Y_SUBS2 if FORMATO == "juego" else 1400
            pegar_centrado(frame, capa, x + w * esc / 2, ys - (6 if ac else 0), escala=esc * (1.1 if ac else 1.0))
            x += (w + esp) * esc

    # --- fotograma ---
    def render(self, n):
        u = n / FPS
        m, s = self.L.en(u)
        i = max(1, int(round((s - m["s_frames"]) * FPS)) + 1)
        ruta = os.path.join(self.dir, m["frames"], f"f_{i:05d}.jpg")
        while not os.path.exists(ruta) and i > 1:
            i -= 1
            ruta = os.path.join(self.dir, m["frames"], f"f_{i:05d}.jpg")
        src = Image.open(ruta).convert("RGB")
        zoom = 1.0
        for a, b in self.L.lentos:
            if a - 0.05 <= u < b + 0.15:
                zoom = max(zoom, 1 + 0.3 * ease_out_cubic((u - a + 0.05) / 0.12))
        for sz in m.get("zooms", []):
            uz = self.L.u_de(m["id"], sz)
            if uz is not None and uz <= u < uz + 2.5:
                k = (u - uz) / 2.5
                zoom = max(zoom, 1 + 0.22 * math.sin(min(k * 4, 1) * math.pi / 2) * (1 - max(0, (k - 0.75) / 0.25)))
        x0, y0, x1, y1 = CAM
        cw, ch = (x1 - x0) / zoom, (y1 - y0) / zoom
        cx, cy = (x0 + x1) / 2 + 10 * (zoom - 1) / 0.22, (y0 + y1) / 2 - 8 * (zoom - 1) / 0.22
        cam = src.resize((W, H_CAM), Image.LANCZOS, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))
        frame = self.fondo.copy()
        if FORMATO == "juego":
            box = JUEGO2
            if "crop_x" in m:  # clips de consola: el encuadre 4:5 sigue al personaje ([[t, x_centro], ...] en 1280x720)
                kx = m["crop_x"]
                cx = kx[0][1] if s <= kx[0][0] else kx[-1][1]
                for (ta, xa), (tb, xb) in zip(kx, kx[1:]):
                    if ta <= s < tb:
                        k = (s - ta) / (tb - ta)
                        cx = xa + (xb - xa) * (1 - math.cos(math.pi * k)) / 2
                cx = min(max(cx, 288), 1280 - 288)
                box = (cx - 288, 0, cx + 288, 720)
            if m.get("sin_cam") and zoom > 1:  # sin cámara, el zoom de las reacciones se hace sobre la partida
                bx0, by0, bx1, by1 = box
                mx, my, hw, hh = (bx0 + bx1) / 2, (by0 + by1) / 2 - 40 * (zoom - 1), (bx1 - bx0) / 2 / zoom, (by1 - by0) / 2 / zoom
                box = (mx - hw, my - hh, mx + hw, my + hh)
            juego = src.resize((W, H_J2), Image.LANCZOS, box=box)
            frame.paste(juego.filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=2)), (0, Y_J2))
        if FORMATO == "juego" and not m.get("sin_cam"):
            # cámara en miniatura; crece un poco en las reacciones (voz grave / zoom)
            esc = 1 + 0.45 * min(1.0, (zoom - 1) / 0.22)
            pw, ph = int(PIP_W * esc), int(PIP_H * esc)
            x0, y0, x1, y1 = CAM
            pip = src.resize((pw, ph), Image.LANCZOS, box=(x0, y0 + (y1 - y0 - (x1 - x0) * PIP_H / PIP_W) / 2,
                                                         x1, y0 + (y1 - y0 + (x1 - x0) * PIP_H / PIP_W) / 2))
            borde = Image.new("RGB", (pw + 12, ph + 12), ROSA)
            mk = self.pip_mask.resize((pw + 12, ph + 12))
            px, py = W - pw - 28 - 6, Y_J2 + 20
            frame.paste(borde, (px, py), mk)
            frame.paste(pip.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2)), (px + 6, py + 6),
                        self.pip_mask.resize((pw, ph)))
        elif FORMATO != "juego":
            frame.paste(cam.filter(ImageFilter.UnsharpMask(radius=2.2, percent=90, threshold=2)), (0, Y_CAM))
            juego = src.resize((W, H_JUEGO), Image.LANCZOS, box=JUEGO)
            frame.paste(juego.filter(ImageFilter.UnsharpMask(radius=1.4, percent=50, threshold=2)), (0, Y_JUEGO))
        frame = frame.convert("RGBA")
        pegar_centrado(frame, self.titulo1, W / 2, 125, escala=1 + 0.03 * max(0, math.sin(u * 5)), angulo=-2)
        pegar_centrado(frame, self.titulo2, W / 2, 222)
        for st in m["stickers"]:
            us = self.L.u_de(m["id"], st["s"])
            uh = self.L.u_de(m["id"], st["hasta"]) if st.get("hasta") else None
            if us is None or u < us or (uh is not None and u > uh):
                continue
            b = u - us
            if st["tipo"] == "chat":
                pegar_centrado(frame, self._chat(st["texto"]), W / 2, 1080, escala=ease_out_back(b / 0.3, 2.0),
                               angulo=-2)
            elif st["tipo"] == "ventilador":
                giro = 1 + 0.04 * math.sin(b * 8)
                pegar_centrado(frame, self.st["ventilador"], W / 2, 1060, escala=ease_out_back(b / 0.35, 2.2) * giro,
                               angulo=-3)
            elif st["tipo"] == "texto":
                pegar_centrado(frame, self._texto(st["lineas"]), W / 2, 1060,
                               escala=ease_out_back(b / 0.35, 2.2) * (1 + 0.04 * math.sin(b * 8)), angulo=-3)
            elif st["tipo"] == "var":
                pegar_centrado(frame, self.st["var"], W / 2, 1060,
                               escala=ease_out_back(b / 0.35, 2.2) * (1 + 0.05 * math.sin(b * 9)), angulo=-4)
        self._subs(frame, u)
        rgb = frame.convert("RGB")
        flash, sac, glitch = 0.0, 0.0, 0.0
        for g in ([m["golpe"]] if m.get("golpe") else []) + m.get("golpes", []):
            ug = self.L.u_de(m["id"], g)
            b = u - ug if ug is not None else -1
            if 0 <= b < 0.3:
                flash, sac = 0.28 * (1 - b / 0.3) ** 2, 26 * (1 - b / 0.3)
        for c in self.L.cortes:
            if 0 <= u - c < TRANS:
                glitch = 1 - (u - c) / TRANS
                flash = max(flash, 0.35 * glitch ** 2)
        arr = None
        if sac > 0:
            arr = np.roll(np.roll(np.asarray(rgb), int(math.cos(u * 77) * sac), 0), int(math.sin(u * 90) * sac), 1)
        if glitch > 0 or flash > 0.01:
            arr = (np.asarray(rgb) if arr is None else arr).astype(np.int16)
            if glitch > 0:
                off = int(30 * glitch)
                arr[:, :, 0] = np.roll(arr[:, :, 0], off, axis=1)
                arr[:, :, 2] = np.roll(arr[:, :, 2], -off, axis=1)
            arr = arr + int(170 * flash)
        if arr is not None:
            rgb = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        return rgb.tobytes()


def leer_wav(ruta):
    with wave.open(ruta) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return x.reshape(-1, ch).mean(1), sr


def audio(ed, salida):
    L = ed.L
    sr = 48000
    N = int(L.total * sr)
    out = np.zeros(N, np.float32)
    cache = {}
    for u0, m, s0, s1, v in L.tramos:
        if m["wav"] not in cache:
            cache[m["wav"]] = leer_wav(os.path.join(ed.dir, m["wav"]))[0]
        x = cache[m["wav"]]
        w0 = m.get("wav_inicio", 0.0)
        seg = x[int((s0 - w0) * sr):int((s1 - w0) * sr)]
        if v != 1.0:
            seg = voz_grave(seg, sr)
        i = int(u0 * sr)
        k = min(len(seg), N - i)
        if k > 0:
            out[i:i + k] += seg[:k]
    rng = np.random.default_rng(4)
    for c in L.cortes:  # whoosh en cada corte
        Lw = int(0.35 * sr)
        t = np.arange(Lw) / sr
        r = rng.standard_normal(Lw)
        wv = np.convolve(r, np.ones(30) / 30, "same") * np.sin(np.pi * t / 0.35) ** 2 * 0.5
        i = int((c - 0.2) * sr)
        out[i:i + Lw] += wv[:max(0, N - i)]
    for m in MOMENTOS:
        for g in ([m["golpe"]] if m.get("golpe") else []) + m.get("golpes", []):
            ug = L.u_de(m["id"], g)
            Lb = int(0.6 * sr)
            tb = np.arange(Lb) / sr
            boom = np.sin(2 * np.pi * (45 * tb + 30 * (1 - np.exp(-tb * 8)))) * np.exp(-tb * 6) * 0.5
            i = int(ug * sr)
            out[i:i + Lb] += boom[:max(0, N - i)]
        for st in m["stickers"]:  # "ding" al aparecer cada sticker
            us = L.u_de(m["id"], st["s"])
            Ld = int(0.5 * sr)
            td = np.arange(Ld) / sr
            i = int(us * sr)
            out[i:i + Ld] += ((np.sin(2 * np.pi * 1320 * td) + 0.5 * np.sin(2 * np.pi * 1760 * td))
                              * np.exp(-td * 7) * 0.13)[:max(0, N - i)]
    clic = int(0.004 * sr)
    out[:clic] *= np.linspace(0, 1, clic)
    out[-clic:] *= np.linspace(1, 0, clic)
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.9
    crudo = salida + ".crudo.wav"
    with wave.open(crudo, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", crudo, "-af",
                    "highpass=f=80,equalizer=f=3000:t=q:w=1.2:g=3,acompressor=threshold=-20dB:ratio=3:attack=5:release=150,"
                    "loudnorm=I=-14:TP=-1.5:LRA=9", "-ar", "48000", "-ac", "2", salida], check=True)
    os.remove(crudo)


_E = None


def _init(dir_, config=None):
    global _E
    if config:
        cargar_config(config)
    _E = Editor(dir_)


def _render(n):
    return _E.render(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--preview", type=float, nargs="*")
    ap.add_argument("--config")
    a = ap.parse_args()
    if a.config:
        cargar_config(a.config)
    os.makedirs(a.salida, exist_ok=True)
    ed = Editor(a.dir)
    print(f"Duración: {ed.L.total:.1f} s · lentos: {[(round(x, 2), round(y, 2)) for x, y in ed.L.lentos]}")
    if a.preview:
        for u in a.preview:
            Image.frombytes("RGB", (W, H), ed.render(int(u * FPS))).save(os.path.join(a.salida, f"prev_{u:05.2f}.jpg"),
                                                                         quality=88)
        return
    wav = os.path.join(a.salida, "audio.wav")
    audio(ed, wav)
    out = os.path.join(a.salida, "clip.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", "-c:a", "aac",
                           "-b:a", "192k", "-shortest", out], stdin=subprocess.PIPE)
    with Pool(os.cpu_count(), initializer=_init, initargs=(a.dir, a.config)) as pool:
        for datos in pool.imap(_render, range(int(ed.L.total * FPS)), chunksize=8):
            ff.stdin.write(datos)
    ff.stdin.close()
    ff.wait()
    if ff.returncode:
        sys.exit(f"ffmpeg falló: {ff.returncode}")
    Image.frombytes("RGB", (W, H), ed.render(int(0.5 * FPS))).save(os.path.join(a.salida, "portada.jpg"), quality=92)
    print("Listo:", out)


if __name__ == "__main__":
    main()
