#!/usr/bin/env python3
"""Clip vertical para Albertesonrrei: "Le está revisando el VAR" (Rocket League).

Montaje: arranque en frío con el gol del rival, rebobinado de 20 s y la jugada completa,
con la cámara de Albert arriba, la partida en el centro, subtítulos tipo karaoke con su voz
(lo muy malsonante se censura con puntitos), golpe en el gol, zoom a la cara y sticker de VAR.

Uso:
    python3 albertesonrrei/clip_var.py --fotogramas DIR --audio segC.wav --palabras tC.json --salida DIR
  DIR de fotogramas: JPG a 60 fps desde s=112 del tramo (f_00001.jpg = s 112,0).
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
import reel  # noqa: E402
from albertesonrrei.efectos import VEL_GRAVE, frase_lenta, voz_grave  # noqa: E402  (fuentes, texto con estilo, utilidades)
from reel import clamp, ease_out_back, ease_out_cubic, fuente, pegar_centrado, texto_con_estilo  # noqa: E402

W, H, FPS = 1080, 1920, 60
S0 = 112.0                       # segundo del tramo del primer fotograma extraído
CAM = (46, 230, 314, 378)        # caja de la cámara en el directo (1280x720)
JUEGO = (335, 0, 1145, 720)      # recorte de la partida (sin chat ni medidor de turbo)
Y_CAM, H_CAM = 300, 597
Y_JUEGO, H_JUEGO = 900, 960
ABS0 = 6045.0                    # segundo del directo donde empieza el tramo (1:40:45)
VENTANA_STT = 6020.0             # inicio de la ventana transcrita

# línea de tiempo (u = segundo del clip, s = segundo del tramo)
FRIO = (1.5, 132.7)              # arranque en frío: 1,5 s desde s=132,7 (gol del rival en s≈134)
REBOB = (0.8, 134.2, 116.0)      # rebobinado de 0,8 s de s=134,2 a s=116
MAIN0, MAIN1 = 116.0, 150.6      # la jugada completa
GOL_S = 134.0
ZOOM_S = 133.8                   # "ay, ay, ay, me sudan las manos"
VAR_S = 144.3                    # "adelantado anulado"
LENTO = VEL_GRAVE                # velocidad de las frases malsonantes (voz "A1": más grave y algo lenta)
MALSONANTES = {"culo", "mierda", "puta", "puto", "putas", "putos", "joder", "coño", "polla", "pinga", "verga",
               "cabrón", "cabron", "gilipollas", "hostia", "hostias", "pinche"}
CENSURA = {"culo": "c•lo", "mierda": "m•••da", "puta": "p•ta", "puto": "p•to", "putas": "p•tas", "putos": "p•tos",
           "joder": "j•der", "coño": "c•ño", "polla": "p•lla", "pinga": "p•nga", "verga": "v•rga",
           "cabrón": "c•brón", "gilipollas": "g•lipollas", "hostia": "h•stia", "hostias": "h•stias"}
ROSA, AMARILLO, BLANCO, OSCURO = (255, 61, 139), (255, 210, 63), (255, 255, 255), (12, 8, 24)
TRAMOS = []                      # (u0, s0, s1, velocidad, tipo); se rellena en preparar_tiempos()
TOTAL = 0.0
U_MAIN = FRIO[0] + REBOB[0]
LENTOS = []                      # (u0, u1) de cada palabra ralentizada


def limpia(txt):
    return txt.lower().strip(".,;:!?¡¿«»\"'")


def preparar_tiempos(palabras):
    """Corta la jugada en tramos normales y tramos lentos (una palabra malsonante cada uno)."""
    global TOTAL, TRAMOS, LENTOS
    feas = []
    ws = [w for w in palabras if w.get("type") == "word"]
    for k, w in enumerate(ws):
        if limpia(w["text"]) not in MALSONANTES:
            continue
        ini, fin, _, _ = frase_lenta(ws, k)  # la frase entera, no solo la palabra
        s0 = VENTANA_STT + ini - ABS0 - 0.04
        s1 = VENTANA_STT + fin - ABS0 + 0.1
        if MAIN0 < s0 < MAIN1:
            feas.append((s0, s1))
    TRAMOS = [(0.0, FRIO[1], FRIO[1] + FRIO[0], 1.0, "frio"), (FRIO[0], REBOB[1], REBOB[2], None, "rebob")]
    u, s = U_MAIN, MAIN0
    LENTOS = []
    for a, b in feas:
        if a > s:
            TRAMOS.append((u, s, a, 1.0, "main"))
            u += a - s
        TRAMOS.append((u, a, b, LENTO, "main"))
        LENTOS.append((u, u + (b - a) / LENTO))
        u += (b - a) / LENTO
        s = b
    TRAMOS.append((u, s, MAIN1, 1.0, "main"))
    u += MAIN1 - s
    TOTAL = u


def s_de_u(u):
    for u0, s0, s1, v, tipo in reversed(TRAMOS):
        if u >= u0:
            if tipo == "rebob":
                k = (u - u0) / REBOB[0]
                return s0 + (s1 - s0) * (min(k, 1) ** 0.7), tipo
            return min(s1, s0 + (u - u0) * v), tipo
    return FRIO[1], "frio"


def u_de_s(s):
    for u0, s0, s1, v, tipo in TRAMOS:
        if tipo == "main" and s0 <= s <= s1:
            return u0 + (s - s0) / v
    return TOTAL


class Clip:
    def __init__(self, dir_fr, palabras):
        self.dir = dir_fr
        self.hook = texto_con_estilo("EMPATE A 3 Y QUEDAN", fuente(64), BLANCO + (255,), borde=8, color_borde=OSCURO)
        self.hook2 = texto_con_estilo("24 SEGUNDOS...", fuente(96), AMARILLO + (255,), borde=10, color_borde=OSCURO,
                                      brillo=ROSA)
        self.antes = texto_con_estilo("20 SEGUNDOS ANTES", fuente(84), BLANCO + (255,), borde=10, color_borde=OSCURO)
        self.var = self._sticker_var()
        self.fondo = Image.new("RGB", (W, H), (13, 9, 24))
        d = ImageDraw.Draw(self.fondo)
        d.rectangle((0, Y_CAM - 6, W, Y_CAM - 1), fill=ROSA)
        d.rectangle((0, Y_JUEGO - 3, W, Y_JUEGO + 2), fill=ROSA)
        self.bloques = self._bloques(palabras)

    def _sticker_var(self):
        w, h = 560, 150
        img = Image.new("RGBA", (w + 40, h + 50), (0, 0, 0, 0))
        sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sombra).rounded_rectangle((26, 30, w + 26, h + 30), radius=30, fill=(0, 0, 0, 160))
        img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(10)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((20, 20, w + 20, h + 20), radius=30, fill=(20, 20, 30, 255), outline=BLANCO + (255,),
                            width=5)
        d.rounded_rectangle((45, 45, 165, 145), radius=12, outline=BLANCO + (255,), width=6)  # tele
        d.line((80, 145, 70, 160), fill=BLANCO + (255,), width=6)
        d.line((130, 145, 140, 160), fill=BLANCO + (255,), width=6)
        d.text((105, 95), "VAR", font=fuente(40), fill=AMARILLO + (255,), anchor="mm")
        d.text((195, 70), "VAR", font=fuente(56), fill=BLANCO + (255,), anchor="lm")
        d.text((195, 130), "REVISANDO", font=fuente(44), fill=(255, 80, 80, 255), anchor="lm")
        return img

    def _bloques(self, palabras):
        ws = []
        for w in palabras:
            if w.get("type") != "word":
                continue
            s0 = VENTANA_STT + w["start"] - ABS0
            s1 = VENTANA_STT + w["end"] - ABS0
            if s0 < MAIN0 - 0.2 or s0 > MAIN1:
                continue
            txt = w["text"].strip()
            base = limpia(txt)
            if base in CENSURA:
                txt = txt.lower().replace(base, CENSURA[base])
            ws.append((txt, u_de_s(s0), u_de_s(min(s1, MAIN1))))
        bloques, act = [], []
        for p in ws:
            act.append(p)
            fin_frase = p[0].endswith((".", "?", "!", ","))
            if len(act) >= 3 or fin_frase:
                bloques.append(act)
                act = []
        if act:
            bloques.append(act)
        return bloques

    def fotograma_fuente(self, s):
        i = int(round((s - S0) * FPS)) + 1
        i = max(1, min(i, 2400))
        return Image.open(os.path.join(self.dir, f"f_{i:05d}.jpg")).convert("RGB")

    def render(self, n):
        u = n / FPS
        s, tramo = s_de_u(u)
        src = self.fotograma_fuente(s)
        frame = self.fondo.copy()
        # cámara (con zoom de reacción)
        zoom = 1.0
        uz = u_de_s(ZOOM_S)
        if tramo == "main" and uz <= u < uz + 3.0:
            k = (u - uz) / 3.0
            zoom = 1 + 0.22 * math.sin(min(k * 4, 1) * math.pi / 2) * (1 - max(0, (k - 0.75) / 0.25))
        for a, b in LENTOS:
            if a - 0.05 <= u < b + 0.15:
                zoom = max(zoom, 1 + 0.3 * ease_out_cubic((u - a + 0.05) / 0.12))
        if tramo == "frio" and u > 0.9:
            zoom = 1 + 0.18 * ease_out_cubic((u - 0.9) / 0.4)
        x0, y0, x1, y1 = CAM
        cw, ch = (x1 - x0) / zoom, (y1 - y0) / zoom
        cx, cy = (x0 + x1) / 2 + 10 * (zoom - 1) / 0.22, (y0 + y1) / 2 - 8 * (zoom - 1) / 0.22
        cam = src.resize((W, H_CAM), Image.LANCZOS, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))
        cam = cam.filter(ImageFilter.UnsharpMask(radius=2.2, percent=90, threshold=2))
        frame.paste(cam, (0, Y_CAM))
        juego = src.resize((W, H_JUEGO), Image.LANCZOS, box=JUEGO)
        juego = juego.filter(ImageFilter.UnsharpMask(radius=1.4, percent=50, threshold=2))
        frame.paste(juego, (0, Y_JUEGO))
        frame = frame.convert("RGBA")
        # gancho arriba
        pegar_centrado(frame, self.hook, W / 2, 120)
        pulso = 1 + 0.04 * max(0, math.sin(u * 6))
        pegar_centrado(frame, self.hook2, W / 2, 215, escala=pulso, angulo=-2)
        # rebobinado
        if tramo == "rebob":
            k = (u - FRIO[0]) / REBOB[0]
            arr = np.asarray(frame.convert("RGB")).astype(np.int16)
            off = 18
            arr[:, :, 0] = np.roll(arr[:, :, 0], off, axis=1)
            arr[:, :, 2] = np.roll(arr[:, :, 2], -off, axis=1)
            arr[::6] = (arr[::6] * 0.55).astype(np.int16)
            frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
            d = ImageDraw.Draw(frame)
            for xx in (440, 500):  # icono de rebobinar
                d.polygon([(xx + 50, 1040), (xx + 50, 1140), (xx - 10, 1090)], fill=BLANCO + (230,))
            pegar_centrado(frame, self.antes, W / 2, 1230, escala=ease_out_back(min(1, k * 3)))
        if tramo == "main" and u < U_MAIN + 1.0:
            a = clamp(1 - (u - U_MAIN) / 1.0)
            pegar_centrado(frame, self.antes, W / 2, 1230, alfa=a)
        # sticker VAR
        uv = u_de_s(VAR_S)
        if tramo == "main" and u >= uv:
            b = u - uv
            parp = 1 + 0.05 * math.sin(b * 9)
            pegar_centrado(frame, self.var, W / 2, 1060, escala=ease_out_back(b / 0.35, 2.2) * parp, angulo=-4)
        # subtítulos
        if tramo == "main":
            self._subs(frame, u)
        rgb = frame.convert("RGB")
        # golpe del gol: destello + sacudida (en el arranque en frío y en la jugada)
        golpes = [FRIO[0] - (FRIO[1] + FRIO[0] - GOL_S), u_de_s(GOL_S)]
        flash, sac = 0.0, 0.0
        for g in golpes:
            b = u - g
            if 0 <= b < 0.3:
                flash = max(flash, 0.28 * (1 - b / 0.3) ** 2)
                sac = max(sac, 26 * (1 - b / 0.3))
        if sac > 0:
            dx, dy = int(math.sin(u * 90) * sac), int(math.cos(u * 77) * sac)
            rgb = Image.fromarray(np.roll(np.roll(np.asarray(rgb), dy, 0), dx, 1))
        if flash > 0.01:
            arr = np.asarray(rgb).astype(np.int16) + int(170 * flash)
            rgb = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        return rgb.tobytes()

    def _subs(self, frame, u):
        bloque = None
        for k, b in enumerate(self.bloques):
            sig = self.bloques[k + 1][0][1] if k + 1 < len(self.bloques) else TOTAL + 1
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
            col = AMARILLO if ac else BLANCO
            capa = texto_con_estilo(txt, f, col + (255,), borde=9, color_borde=(0, 0, 0))
            e2 = esc * (1.1 if ac else 1.0)
            pegar_centrado(frame, capa, x + w * esc / 2, 1400 - (6 if ac else 0), escala=e2)
            x += (w + esp) * esc


_C = None


def _init(dir_fr, palabras):
    global _C
    preparar_tiempos(palabras)
    _C = Clip(dir_fr, palabras)


def _render(n):
    return _C.render(n)


def leer_wav(ruta):
    with wave.open(ruta) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return x.reshape(-1, ch).mean(1), sr


def audio(ruta_wav, salida):
    x, sr = leer_wav(ruta_wav)
    N = int(TOTAL * sr)
    out = np.zeros(N, np.float32)

    def tramo(s0, s1, u0, g=1.0):
        a, b = int(s0 * sr), int(s1 * sr)
        seg = x[a:b] * g
        i = int(u0 * sr)
        out[i:i + len(seg)] += seg[:max(0, N - i)]

    for u0, s0, s1, v, tipo in TRAMOS:
        if tipo == "rebob":
            continue
        a, b = int(s0 * sr), int(s1 * sr)
        seg = x[a:b]
        if v != 1.0:  # cinta ralentizada: más lenta y más grave a la vez
            seg = voz_grave(seg, sr)
        i = int(u0 * sr)
        k = min(len(seg), N - i)
        if k > 0:
            out[i:i + k] += seg[:k]
    rng = np.random.default_rng(3)
    # rebobinado: barrido descendente con ruido de cinta
    L = int(REBOB[0] * sr)
    t = np.arange(L) / sr
    barrido = np.sin(2 * np.pi * np.cumsum(np.linspace(1800, 300, L)) / sr) * 0.25
    ruido = rng.standard_normal(L) * 0.08
    env = np.sin(np.pi * t / REBOB[0]) ** 0.5
    out[int(FRIO[0] * sr):int(FRIO[0] * sr) + L] += (barrido + ruido) * env
    # golpe grave en los goles
    for g in (FRIO[0] - (FRIO[1] + FRIO[0] - GOL_S), u_de_s(GOL_S)):
        Lb = int(0.6 * sr)
        tb = np.arange(Lb) / sr
        boom = np.sin(2 * np.pi * (45 * tb + 30 * (1 - np.exp(-tb * 8)))) * np.exp(-tb * 6) * 0.5
        i = int(g * sr)
        out[i:i + Lb] += boom[:max(0, N - i)]
    # "ding" del sticker del VAR
    i = int(u_de_s(VAR_S) * sr)
    Ld = int(0.5 * sr)
    td = np.arange(Ld) / sr
    out[i:i + Ld] += (np.sin(2 * np.pi * 1320 * td) + 0.5 * np.sin(2 * np.pi * 1760 * td)) * np.exp(-td * 7) * 0.15
    clic = int(0.004 * sr)
    out[:clic] *= np.linspace(0, 1, clic)
    out[-clic:] *= np.linspace(1, 0, clic)
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.9
    pcm = (out * 32767).astype(np.int16)
    crudo = salida + ".crudo.wav"
    with wave.open(crudo, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    # voz por delante: realce de presencia, compresión y volumen estándar de redes
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", crudo, "-af",
                    "highpass=f=80,equalizer=f=3000:t=q:w=1.2:g=3,acompressor=threshold=-20dB:ratio=3:attack=5:release=150,"
                    "loudnorm=I=-14:TP=-1.5:LRA=9", "-ar", "48000", "-ac", "2", salida], check=True)
    os.remove(crudo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fotogramas", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--palabras", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--preview", type=float, nargs="*")
    a = ap.parse_args()
    palabras = json.load(open(a.palabras))["words"]
    preparar_tiempos(palabras)
    os.makedirs(a.salida, exist_ok=True)
    if a.preview:
        c = Clip(a.fotogramas, palabras)
        for u in a.preview:
            Image.frombytes("RGB", (W, H), c.render(int(u * FPS))).save(os.path.join(a.salida, f"prev_{u:05.2f}.jpg"),
                                                                        quality=88)
        return
    wav = os.path.join(a.salida, "audio.wav")
    audio(a.audio, wav)
    n = int(TOTAL * FPS)
    out = os.path.join(a.salida, "clip.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", "-c:a", "aac",
                           "-b:a", "192k", "-shortest", out], stdin=subprocess.PIPE)
    with Pool(os.cpu_count(), initializer=_init, initargs=(a.fotogramas, palabras)) as pool:
        for i, datos in enumerate(pool.imap(_render, range(n), chunksize=8)):
            ff.stdin.write(datos)
    ff.stdin.close()
    ff.wait()
    if ff.returncode:
        sys.exit(f"ffmpeg falló: {ff.returncode}")
    Image.frombytes("RGB", (W, H), Clip(a.fotogramas, palabras).render(int(0.6 * FPS))).save(
        os.path.join(a.salida, "portada.jpg"), quality=92)
    print("Listo:", out, f"{TOTAL:.1f} s")


if __name__ == "__main__":
    main()
