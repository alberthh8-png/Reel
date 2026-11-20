#!/usr/bin/env python3
"""Clip vertical "POV: intentas robar un camión para ir a ver a Lucía" (bug del camión en GTA 6).

Fuente: vídeo de Albert (1920x1080, 60 fps) pasado por Google Drive. Sin su voz: música original y efectos.
Uso: python3 albertesonrrei/pov_camion.py VIDEO.mp4 SALIDA_DIR
"""
import os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reel  # noqa: E402
from reel import ajustar_fuente, texto_con_estilo, SR  # noqa: E402

W, H, FPS = 1080, 1920, 30
Y_J, H_J = 290, 1350                        # partida 4:5 a todo el ancho (mismo formato que los clips de directo)
CROP = (528, 0, 864, 1080)                  # x, y, ancho, alto del recorte 4:5 en el 1920x1080 (centrado en Jason)
CROP_BUG = (780, 0, 864, 1080)              # durante el bug el encuadre se va hacia el camión
ROSA, AMARILLO, BLANCO, OSCURO = (255, 61, 139), (255, 210, 63), (255, 255, 255), (12, 8, 24)
TITULO = ("POV: INTENTAS ROBAR UN CAMIÓN", "PARA IR A VER A LUCÍA")

# (inicio, fin, velocidad, zoom) en segundos del vídeo original
TRAMOS = [
    (17.40, 20.00, 1.0, 1.04),   # gancho: el camión ya se ha vuelto loco
    ("rebobinar", 0.6),
    (9.00, 17.40, 1.0, 1.00),    # 10 segundos antes: todo normal
    (17.40, 19.00, 0.5, 1.12),   # el bug a cámara lenta
    (19.00, 22.80, 1.0, 1.05),
    (22.80, 24.40, 0.5, 1.12),   # el remolque sale volando
    (24.40, 27.60, 1.0, 1.00),   # se queda de pie
]
if os.environ.get("SOLO_GANCHO"):          # solo el gancho + rebobinado (para pegarlo delante del clip original)
    TRAMOS = TRAMOS[:2]
GOLPES_SRC = [17.75, 23.20]      # momentos del original con golpe de sonido


def extraer(video, dir_, crop=CROP):
    os.makedirs(dir_, exist_ok=True)
    if not os.path.exists(os.path.join(dir_, "f_00001.jpg")):
        x, y, w, h = crop
        subprocess.run(["ffmpeg", "-v", "error", "-ss", "8.5", "-i", video, "-t", "20", "-vf",
                        f"fps=60,crop={w}:{h}:{x}:{y},scale={W}:{H_J}:flags=lanczos,unsharp=5:5:0.6", "-q:v", "2",
                        os.path.join(dir_, "f_%05d.jpg")], check=True)
    return lambda t: os.path.join(dir_, f"f_{max(1, int(round((t - 8.5) * 60)) + 1):05d}.jpg")


def linea_tiempo():
    """Lista de (t_salida, t_origen, zoom, tipo) por fotograma de salida."""
    frames, u = [], 0.0
    for tr in TRAMOS:
        if tr[0] == "rebobinar":
            n = int(tr[1] * FPS)
            for k in range(n):   # rebobinado rápido desde el final del gancho hasta el inicio del siguiente tramo
                frames.append((20.0 - (20.0 - 9.0) * k / max(1, n - 1), 1.0, "rebobinar"))
            continue
        a, b, v, z = tr
        n = int(round((b - a) / v * FPS))
        for k in range(n):
            frames.append((a + (b - a) * k / n, z, "lento" if v < 1 else "normal"))
    return frames


def cabecera():
    im = Image.new("RGBA", (W, Y_J), OSCURO + (255,))
    f1 = ajustar_fuente(TITULO[0], 980, 70, tam_min=44, borde=10)
    f2 = ajustar_fuente(TITULO[1], 980, 70, tam_min=44, borde=10)
    t1 = texto_con_estilo(TITULO[0], f1, BLANCO + (255,), borde=9, color_borde=(0, 0, 0))
    t2 = texto_con_estilo(TITULO[1], f2, AMARILLO + (255,), borde=9, color_borde=(0, 0, 0), brillo=ROSA)
    im.alpha_composite(t1, ((W - t1.width) // 2, 70 - t1.height // 2 + 20))
    im.alpha_composite(t2, ((W - t2.width) // 2, 180 - t2.height // 2 + 15))
    ImageDraw.Draw(im).rectangle((0, Y_J - 6, W, Y_J), fill=ROSA)
    return im


def caja_texto(lineas, colores):
    f = reel.fuente(66)
    w = max(int(f.getlength(l)) for l in lineas) + 90
    h = 50 + 84 * len(lineas)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, w - 6, h - 6), 28, fill=(255, 255, 255, 255), outline=(20, 20, 30, 255), width=6)
    for i, (l, c) in enumerate(zip(lineas, colores)):
        d.text((w // 2, 50 + 84 * i), l, font=f, fill=c + (255,), anchor="mt")
    return im


def render(video, salida):
    base = os.environ.get("FR_DIR", os.path.join(salida, "_fr"))
    fr_j = extraer(video, base)
    fr_b = extraer(video, base + "_bug", CROP_BUG)

    def fr(t, tipo=None):
        # encuadre en el camión durante el bug (y en el gancho), en Jason el resto
        return fr_b(t) if t >= 17.25 else fr_j(t)
    tl = linea_tiempo()
    cab = cabecera()
    st_normal = caja_texto(["Todo normal…", "de momento 🙂".replace("🙂", "")], [(20, 12, 30), (230, 40, 70)])
    st_antes = caja_texto([os.environ.get("TEXTO_ANTES", "10 SEGUNDOS ANTES")], [(230, 40, 70)])
    st_loco = caja_texto(["EL CAMIÓN SE", "VOLVIÓ LOCO"], [(20, 12, 30), (230, 40, 70)])
    pie = Image.new("RGB", (W, H - Y_J - H_J), OSCURO)
    ImageDraw.Draw(pie).rectangle((0, 0, W, 5), fill=ROSA)
    golpes_u = []
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                            "-pix_fmt", "yuv420p", os.path.join(salida, "_video.mp4")], stdin=subprocess.PIPE)
    rnd = np.random.default_rng(3)
    previo = None
    for i, (t, z, tipo) in enumerate(tl):
        u = i / FPS
        if previo is not None and tipo != "rebobinar":
            for g in GOLPES_SRC:
                if previo < g <= t:
                    golpes_u.append(u)
        previo = t if tipo != "rebobinar" else None
        src = Image.open(fr(t)).convert("RGB")
        # golpe: zoom extra + temblor que se apaga en 0,4 s
        gk = max([0.0] + [max(0.0, 1 - (u - gu) / 0.4) for gu in golpes_u if u >= gu])
        zz = z + 0.08 * gk
        if zz > 1.001:
            cw, ch = W / zz, H_J / zz
            dx, dy = rnd.uniform(-1, 1) * 22 * gk, rnd.uniform(-1, 1) * 22 * gk
            src = src.resize((W, H_J), Image.BILINEAR, box=((W - cw) / 2 + dx, (H_J - ch) / 2 + dy,
                                                          (W + cw) / 2 + dx, (H_J + ch) / 2 + dy))
        if tipo == "rebobinar":   # efecto VHS: líneas, color corrido y desenfoque de movimiento
            a = np.asarray(src).astype(np.int16)
            a = np.stack([np.roll(a[:, :, 0], 10, 1), a[:, :, 1], np.roll(a[:, :, 2], -10, 1)], 2)
            a[::6] = a[::6] * 0.5
            src = Image.fromarray(a.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))
        if gk > 0.6:
            a = np.asarray(src).astype(np.float32)
            src = Image.fromarray((a + (255 - a) * (gk - 0.6) * 1.1).clip(0, 255).astype(np.uint8))
        frame = Image.new("RGBA", (W, H), OSCURO + (255,))
        frame.paste(src, (0, Y_J))
        frame.paste(pie, (0, Y_J + H_J))
        frame.alpha_composite(cab)
        # rótulos
        n_gancho = int(2.6 * FPS)
        n_rebob = n_gancho + int(0.6 * FPS)
        if i < n_gancho and i > 6:
            q = reel.ease_out_back(reel.clamp((i - 6) / 9), 2.0)
            reel.pegar_centrado(frame, st_loco, W / 2, Y_J + H_J + 140 - 40, escala=0.85 * q, angulo=-3)
        elif n_gancho <= i < n_rebob + int(1.6 * FPS):
            reel.pegar_centrado(frame, st_antes, W / 2, Y_J + H_J + 140 - 40, escala=0.85, angulo=-3)
        elif tipo == "normal" and 10.0 <= t < 13.0:
            q = reel.ease_out_back(reel.clamp((t - 10.0) / 0.3), 2.0)
            reel.pegar_centrado(frame, st_normal, W / 2, Y_J + H_J + 140 - 40, escala=0.85 * q, angulo=-3)
        if tipo == "lento":
            d = ImageDraw.Draw(frame)
            d.rounded_rectangle((40, Y_J + 30, 300, Y_J + 100), 20, fill=(0, 0, 0, 170))
            d.text((170, Y_J + 65), "CÁMARA LENTA", font=reel.fuente(30), fill=AMARILLO, anchor="mm")
        enc.stdin.write(frame.convert("RGB").tobytes())
    enc.stdin.close()
    enc.wait()
    return len(tl) / FPS, golpes_u, n_gancho / FPS


def audio(total, golpes_u, t_rebob, salida):
    n = int(total * SR) + SR
    mus = reel.musica(total + 1, 140)[:n]
    mus = mus / (np.abs(mus).max() + 1e-9) * 0.5
    env = np.ones(n)
    a, b = int(t_rebob * SR), int((t_rebob + 0.6) * SR)
    env[a:b] = 0.15                                   # la música se corta en el rebobinado
    fx = np.zeros(n)
    rng = np.random.default_rng(5)
    for g in golpes_u:
        reel.pegar(fx, g * SR, reel.sfx_explosion(rng, 1.6), 0.9)
    L = b - a                                        # rebobinado: barrido de cinta hacia atrás
    tt = np.arange(L) / SR
    reel.pegar(fx, a, np.sin(2 * np.pi * (1800 * tt - 1500 * tt ** 2)) * 0.25 * np.sin(np.pi * tt / (L / SR)), 1.0)
    reel.pegar(fx, a - 0.1 * SR, reel.sfx_whoosh(rng, 0.5), 0.6)
    k = int(0.6 * SR)
    env[-k - SR:] = np.minimum(env[-k - SR:], np.linspace(1, 0, len(env[-k - SR:])))
    mezcla = mus * env + fx
    mezcla /= np.abs(mezcla).max() / 0.95
    tmp = os.path.join(salida, "_audio.wav")
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mezcla * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", os.path.join(salida, "_video.mp4"), "-i", tmp, "-af",
                    "loudnorm=I=-14:TP=-1.5,volume=6.8dB,alimiter=limit=0.75:level=false", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                    "-movflags", "+faststart", os.path.join(salida, "clip.mp4")], check=True)
    os.remove(tmp)
    os.remove(os.path.join(salida, "_video.mp4"))


def audio_juego(video, salida):
    """Solo el sonido original del juego, siguiendo los tramos (sin música ni efectos añadidos).
    Tramos lentos: el audio va a la mitad de velocidad (atempo, mismo tono). Rebobinado: el audio al revés y rápido."""
    partes, filtros = [], []
    for k, tr in enumerate(TRAMOS):
        if tr[0] == "rebobinar":
            f = f"[0:a]atrim=18.8:20.0,asetpts=PTS-STARTPTS,areverse,atempo=2.0,afade=t=in:d=0.02,afade=t=out:st=0.56:d=0.04[p{k}]"
        else:
            a, b, v, _ = tr
            d = (b - a) / v
            lento = ",atempo=0.5" if v < 1 else ""
            f = (f"[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS{lento},afade=t=in:d=0.02,"
                 f"afade=t=out:st={max(0.0, d - 0.03):.3f}:d=0.03[p{k}]")
        filtros.append(f)
        partes.append(f"[p{k}]")
    fc = ";".join(filtros) + ";" + "".join(partes) + f"concat=n={len(partes)}:v=0:a=1[mez];[mez]loudnorm=I=-14:TP=-1.5[out]"
    tmp = os.path.join(salida, "_audio.m4a")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-filter_complex", fc, "-map", "[out]", "-ar", "48000",
                    "-c:a", "aac", "-b:a", "192k", tmp], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", os.path.join(salida, "_video.mp4"), "-i", tmp, "-map", "0:v",
                    "-map", "1:a", "-c", "copy", "-shortest", "-movflags", "+faststart", os.path.join(salida, "clip.mp4")],
                   check=True)
    os.remove(tmp)
    os.remove(os.path.join(salida, "_video.mp4"))


if __name__ == "__main__":
    video, salida = sys.argv[1], sys.argv[2]
    os.makedirs(salida, exist_ok=True)
    total, golpes_u, t_rebob = render(video, salida)
    if os.environ.get("AUDIO") == "musica":
        audio(total, golpes_u, t_rebob, salida)
    else:   # por defecto: sonido original del juego (pedido por Albert)
        audio_juego(video, salida)
    print("ok", round(total, 2), "s · golpes", [round(g, 2) for g in golpes_u])
