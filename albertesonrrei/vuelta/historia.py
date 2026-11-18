#!/usr/bin/env python3
"""Historia vertical "La vuelta" de Albertesonrrei (1080x1920, 30 fps).

Voz: Leónidas (voz/vuelta/l0..l7). Fondo: solo clips de los directos de Albert, sin su audio.
Uso: python3 albertesonrrei/vuelta/historia.py  ->  salida/albertesonrrei/vuelta/historia.mp4
"""
import json, os, random, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RAIZ = "/home/user/Reel"
sys.path.insert(0, RAIZ)
import reel  # noqa: E402
from reel import fuente, ajustar_fuente, texto_con_estilo, SR  # noqa: E402

TW = "/tmp/claude-0/-home-user-Reel/3efe04a8-bc52-519f-9bff-2b639dd9ba8e/scratchpad/twitch/"
VOZ = f"{RAIZ}/voz/vuelta"
SAL = f"{RAIZ}/salida/albertesonrrei/vuelta"
W, H, FPS = 1080, 1920, 30
CAM = (46, 230, 314, 378)
JUEGO = (335, 0, 1145, 720)
Y_CAM, H_CAM = 300, 597
Y_JUEGO, H_JUEGO = 900, 960
ROSA, AMARILLO, BLANCO, CIAN = (255, 46, 196), (255, 214, 0), (255, 255, 255), (0, 229, 255)
CENSURA = {"mierda": "m•••da"}

# (clave de voz, silencio después)
ORDEN = [("l0", 0.15), ("l1", 0.35), ("l2", 0.7), ("l3", 0.35), ("l4", 0.7), ("l5", 0.35), ("l6", 0.35), ("l7", 1.3)]

# planos por tramo de voz: (archivo, segundo del directo donde empieza)
PLANOS = {
    "l0": [("m4092.mp4", 4097.0)],
    "l1": [("m8787.mp4", 8800.0)],
    "l2": [("m3110.mp4", 3122.6), ("m7410.mp4", 7411.8), ("m8430.mp4", 8433.7), ("m8705.mp4", 8706.0)],
    "l3": [("m4092.mp4", 4099.6)],
    "l4": [("m8430.mp4", 8434.5)],
    "l5": [("m7410.mp4", 7440.0)],
    "l6": [("m8787.mp4", 8850.0)],
    "l7": [("m8787.mp4", 8852.5)],
}
INICIO_ARCHIVO = {"m3110.mp4": 3110.0, "m4092.mp4": 4092.0, "m7410.mp4": 7410.0, "m8430.mp4": 8430.0,
                  "m8705.mp4": 8705.0, "m8787.mp4": 8786.0}
TITULOS = {"l0": ("¡EH, TÚ!", AMARILLO), "l1": ("UN VIEJO AMIGO…", BLANCO), "l2": ("RECUERDOS", CIAN),
           "l3": ("HA VUELTO", AMARILLO), "l4": ("HOY · 00:00", AMARILLO), "l5": ("DIRECTO EN TWITCH", CIAN),
           "l6": ("¿OS VENÍS?", AMARILLO), "l7": ("QUIEN NO VENGA…", ROSA)}


def dur(ruta):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta]))


def palabras(clave, t0):
    al = json.load(open(f"{VOZ}/{clave}.json"))["alineacion"]
    txt = "".join(al["characters"])
    ws, cur, a, b = [], "", None, None
    dentro = False
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if ch == "[":
            dentro = True
        if dentro:
            if ch == "]":
                dentro = False
            continue
        if ch.isspace():
            if cur:
                ws.append([cur, a + t0, b + t0])
            cur, a = "", None
            continue
        if a is None:
            a = s
        cur, b = cur + ch, e
    if cur:
        ws.append([cur, a + t0, b + t0])
    out = []
    for w, a, b in ws:
        w = w.replace("sonrreí", "sonrrei").replace("Alberte", "Albertesonrrei") if "sonrre" in w or w == "Alberte" else w
        if w.strip(".…!¡¿?,") == "":
            continue
        out.append([w, a, b])
    # "Albertesonrrei" + "sonrrei..." -> una sola palabra
    res = []
    for w in out:
        if res and res[-1][0] == "Albertesonrrei" and w[0].lower().lstrip("¡¿.…").startswith("sonrrei"):
            res[-1] = ["Albertesonrrei" + w[0][len("sonrrei"):], res[-1][1], w[2]]
        else:
            res.append(w)
    return res, txt


def linea_tiempo():
    t, tramos = 0.25, []
    for clave, pausa in ORDEN:
        d = dur(f"{VOZ}/{clave}.wav")
        ws, _ = palabras(clave, t)
        tramos.append({"clave": clave, "t0": t, "t1": t + d, "fin": t + d + pausa, "ws": ws})
        t += d + pausa
    return tramos, t


class Fuente:
    """Decodifica un clip del directo ya montado en vertical (cámara arriba, partida abajo)."""

    def __init__(self, archivo, seg, n):
        ss = seg - INICIO_ARCHIVO[archivo]
        cx0, cy0, cx1, cy1 = CAM
        cw, ch = cx1 - cx0, cy1 - cy0
        asp = W / H_CAM
        if cw / ch > asp:
            nw, nh = ch * asp, ch
        else:
            nw, nh = cw, cw / asp
        ccx, ccy = (cx0 + cx1) / 2, (cy0 + cy1) / 2
        crop_cam = f"crop={int(nw)}:{int(nh)}:{int(ccx - nw / 2)}:{int(ccy - nh / 2)}"
        gx0, gy0, gx1, gy1 = JUEGO
        fc = (f"[0:v]fps={FPS},split=3[a][b][c];"
              f"color=c=0x0c0618:s={W}x{H}:r={FPS}[fondo];"
              f"[a]{crop_cam},scale={W}:{H_CAM}:flags=lanczos,unsharp=5:5:0.8[cam];"
              f"[b]crop={gx1 - gx0}:{gy1 - gy0}:{gx0}:{gy0},scale={W}:{H_JUEGO}:flags=lanczos,unsharp=5:5:0.5[juego];"
              f"[c]scale=270:-2,crop=270:120,boxblur=10:2,scale={W}:300,eq=brightness=-0.35[arriba];"
              f"[fondo][arriba]overlay=0:0:shortest=1[f1];[f1][cam]overlay=0:{Y_CAM}[f2];[f2][juego]overlay=0:{Y_JUEGO}")
        self.n, self.leidos, self.ult = n, 0, None
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}", "-i", TW + archivo, "-filter_complex", fc,
                                   "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

    def leer(self):
        if self.leidos < self.n:
            b = self.p.stdout.read(W * H * 3)
            if len(b) == W * H * 3:
                self.ult = np.frombuffer(b, np.uint8).reshape(H, W, 3)
            self.leidos += 1
        return self.ult

    def cerrar(self):
        try:
            self.p.stdout.close(); self.p.kill()
        except Exception:
            pass


def planos_de(tramos, total):
    out = []
    for k, tr in enumerate(tramos):
        ini = tr["t0"] if k else 0.0
        fin = tramos[k + 1]["t0"] if k + 1 < len(tramos) else total
        lista = PLANOS[tr["clave"]]
        paso = (fin - ini) / len(lista)
        for i, (arch, seg) in enumerate(lista):
            out.append((ini + i * paso, ini + (i + 1) * paso, arch, seg, tr["clave"]))
    return out


def cabecera(texto, color):
    f = ajustar_fuente(texto, 980, 120, tam_min=60)
    return texto_con_estilo(texto, f, color, borde=8, color_borde=(0, 0, 0), brillo=(120, 30, 200))


def subtitulo(ws_tr, k):
    f = fuente(64)
    palabras_ = [CENSURA.get(w[0].lower().strip(".,!¡¿?…"), w[0]).upper() for w in ws_tr]
    sp = f.getlength(" ")
    lineas, cur, ancho = [], [], 0
    for i, p in enumerate(palabras_):
        lw = f.getlength(p)
        if cur and ancho + sp + lw > 960:
            lineas.append(cur); cur, ancho = [], 0
        cur.append(i); ancho += (sp if len(cur) > 1 else 0) + lw
    if cur:
        lineas.append(cur)
    im = Image.new("RGBA", (W, 100 * len(lineas) + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for li, idx in enumerate(lineas):
        total = sum(f.getlength(palabras_[i]) for i in idx) + sp * (len(idx) - 1)
        x = (W - total) / 2
        for i in idx:
            d.text((x, 20 + li * 100), palabras_[i], font=f, fill=AMARILLO if i == k else BLANCO,
                   stroke_width=7, stroke_fill=(0, 0, 0))
            x += f.getlength(palabras_[i]) + sp
    return im


def trozos(ws):
    out, cur = [], []
    for w in ws:
        cur.append(w)
        if re.search(r"[.,!?…]$", w[0]) or len(cur) >= 4:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def tabla():
    filas = [("🇪🇸", "ESPAÑA", "23:30"), ("", "ARGENTINA · CHILE", "19:30"), ("", "VENEZUELA", "18:30"),
             ("", "COLOMBIA · PERÚ · ECUADOR", "17:30"), ("", "MÉXICO", "16:30")]
    im = Image.new("RGBA", (980, 640), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, 979, 639), 36, fill=(16, 8, 34, 235), outline=ROSA + (255,), width=6)
    d.text((490, 70), "HOY · 18 NOV · TWITCH", font=fuente(54), fill=AMARILLO, anchor="mm")
    for i, (_, pais, hora) in enumerate(filas):
        y = 150 + i * 96
        d.rounded_rectangle((30, y, 949, y + 82), 18, fill=(70, 30, 120, 230) if i == 0 else (35, 25, 60, 220))
        d.text((60, y + 41), pais, font=fuente(42 if len(pais) < 20 else 36), fill=BLANCO, anchor="lm")
        d.text((920, y + 41), hora, font=fuente(60), fill=AMARILLO if i == 0 else CIAN, anchor="rm")
    return im


def sello(texto, color=ROSA, tam=110):
    f = ajustar_fuente(texto, 860, tam, tam_min=40)
    t = texto_con_estilo(texto, f, BLANCO, borde=0, sombra=False)
    im = Image.new("RGBA", (t.width + 60, t.height + 20), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((10, 30, im.width - 10, im.height - 30), 24, fill=color + (255,))
    im.alpha_composite(t, (30, 10))
    return im.rotate(-7, expand=True, resample=Image.BICUBIC)


def render():
    os.makedirs(SAL, exist_ok=True)
    tramos, total = linea_tiempo()
    N = int(round(total * FPS))
    planos = planos_de(tramos, total)
    subs = []
    for tr in tramos:
        for tz in trozos(tr["ws"]):
            subs.append((tz[0][1], tz[-1][2] + 0.25, tz))
    cab = {k: cabecera(*v) for k, v in TITULOS.items()}
    tab = tabla()
    s_vuelto, s_twitch = sello("HA VUELTO"), sello("twitch.tv/albertesonrrei", (120, 50, 230), 78)
    final = texto_con_estilo("COME MIEMBROS", ajustar_fuente("COME MIEMBROS", 960, 140), ROSA, borde=10, brillo=(255, 0, 120))
    tr_de = {tr["clave"]: tr for tr in tramos}
    t_impacta = next(w[1] for w in tr_de["l4"]["ws"] if w[0].lower().lstrip("¡¿.…").startswith("impacta"))
    t_vuelto = next(w[1] for w in tr_de["l3"]["ws"] if w[0].lower().lstrip("¡¿.…").startswith("ha"))
    golpes = [tr_de["l0"]["t0"], t_vuelto, t_impacta, tr_de["l7"]["t0"]]
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            f"{SAL}/_video.mp4"], stdin=subprocess.PIPE)
    abiertos = {}
    rnd = random.Random(4)
    for fi in range(N):
        t = fi / FPS
        i = next(k for k, p in enumerate(planos) if p[0] - 1e-6 <= t < p[1] + 1e-6 or k == len(planos) - 1)
        a, b, arch, seg, clave = planos[i]
        if i not in abiertos:
            for j in list(abiertos):
                abiertos.pop(j).cerrar()
            abiertos[i] = Fuente(arch, seg, int((b - a) * FPS) + 3)
        fr = abiertos[i].leer()
        img = Image.fromarray(fr).convert("RGB") if fr is not None else Image.new("RGB", (W, H))
        # golpes: zoom + temblor + flash
        g = max([0] + [max(0.0, 1 - (t - tg) / 0.35) for tg in golpes if t >= tg])
        zoom = 1 + 0.10 * g
        if clave == "l4":
            zoom *= 1 + 0.08 * (t - a) / max(0.1, b - a)      # acercamiento lento en la luna
        if clave == "l2":
            zoom *= 1.04
        if zoom > 1.001:
            cw, ch = W / zoom, H / zoom
            dx = rnd.uniform(-1, 1) * 18 * g
            dy = rnd.uniform(-1, 1) * 18 * g
            img = img.resize((W, H), Image.BILINEAR, box=((W - cw) / 2 + dx, (H - ch) / 2 + dy, (W + cw) / 2 + dx, (H + ch) / 2 + dy))
        if clave == "l2":   # recuerdos: color tipo VHS
            arr = np.asarray(img).astype(np.int16)
            arr = np.stack([np.roll(arr[:, :, 0], 6, axis=1), arr[:, :, 1], np.roll(arr[:, :, 2], -6, axis=1)], 2)
            gris = arr.mean(2, keepdims=True)
            arr = (arr * 0.55 + gris * 0.45) * 0.9 + 10
            img = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
        if clave == "l5":
            arr = np.asarray(img).astype(np.float32) * 0.45
            img = Image.fromarray(arr.astype(np.uint8))
        if g > 0.6:
            arr = np.asarray(img).astype(np.float32)
            img = Image.fromarray((arr + (255 - arr) * (g - 0.6) * 1.2).clip(0, 255).astype(np.uint8))
        img = img.convert("RGBA")
        # cabecera
        c = cab[clave]
        q = reel.ease_out_back(reel.clamp((t - max(a, next(tr["t0"] for tr in tramos if tr["clave"] == clave) - 0.1)) / 0.3))
        if q > 0.02:
            cc = c.resize((max(1, int(c.width * q)), max(1, int(c.height * q))))
            img.alpha_composite(cc, ((W - cc.width) // 2, 150 - cc.height // 2))
        # elementos por tramo
        if clave == "l3" and t >= t_vuelto:
            q = reel.ease_out_back(reel.clamp((t - t_vuelto) / 0.25))
            s = s_vuelto.resize((max(1, int(s_vuelto.width * q)), max(1, int(s_vuelto.height * q))))
            img.alpha_composite(s, ((W - s.width) // 2, 1040 - s.height // 2))
        if clave == "l5":
            q = reel.ease_out_cubic(reel.clamp((t - tr_de["l5"]["t0"]) / 0.4))
            tb = tab.copy(); tb.putalpha(tb.getchannel("A").point(lambda v, q=q: int(v * q)))
            img.alpha_composite(tb, ((W - tab.width) // 2, 760 + int((1 - q) * 80)))
        if clave in ("l6", "l7"):
            img.alpha_composite(s_twitch, ((W - s_twitch.width) // 2, 1000 - s_twitch.height // 2))
        if clave == "l7":
            tm = next((w[1] for w in tr_de["l7"]["ws"] if w[0].lower().lstrip("¡¿.…").startswith("come")), tr_de["l7"]["t0"])
            if t >= tm:
                q = reel.ease_out_back(reel.clamp((t - tm) / 0.3))
                fm = final.resize((max(1, int(final.width * q)), max(1, int(final.height * q))))
                img.alpha_composite(fm, ((W - fm.width) // 2, 1250 - fm.height // 2))
        # subtítulos karaoke
        for sa, sb, tz in subs:
            if sa - 0.05 <= t < sb and not (clave == "l7" and t > tz[0][1] and any(w[0].lower().lstrip("¡¿.…").startswith("come") for w in tz)):
                k = sum(1 for w in tz if w[1] <= t) - 1
                st = subtitulo(tz, k)
                img.alpha_composite(st, (0, 1480 if clave not in ("l5",) else 1460))
                break
        enc.stdin.write(img.convert("RGB").tobytes())
    for p in abiertos.values():
        p.cerrar()
    enc.stdin.close(); enc.wait()
    return tramos, total, golpes


def audio(tramos, total, golpes):
    n = int(total * SR) + SR
    voz, fx = np.zeros(n), np.zeros(n)
    for tr in tramos:
        w = wave.open(f"{VOZ}/{tr['clave']}.wav")
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64) / 32768
        reel.pegar(voz, tr["t0"] * SR, x)
    mus = reel.musica(total + 1, 140)[:n]
    mus = mus / (np.abs(mus).max() + 1e-9)
    env = np.full(n, 0.20)
    env[: int(0.25 * SR)] = 0.0
    k = int(0.4 * SR)
    env[-k - SR:] = np.linspace(0.2, 0.0, len(env[-k - SR:]))
    rng = np.random.default_rng(2)
    for tg in golpes:
        reel.pegar(fx, tg * SR - 0.02 * SR, reel.sfx_explosion(rng, 1.4), 0.35)
    for tr in tramos[1:]:
        reel.pegar(fx, (tr["t0"] - 0.25) * SR, reel.sfx_whoosh(rng, 0.35), 0.25)
    voz_n = voz / (np.abs(voz).max() + 1e-9)
    mezcla = voz_n + mus * env + fx * 0.6
    mezcla /= np.abs(mezcla).max() / 0.95
    tmp = f"{SAL}/_mezcla.wav"
    with wave.open(tmp, "wb") as wv:
        wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(SR)
        wv.writeframes((mezcla * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", f"{SAL}/_video.mp4", "-i", tmp, "-af", "loudnorm=I=-14:TP=-1.5",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
                    f"{SAL}/historia.mp4"], check=True)
    os.remove(tmp); os.remove(f"{SAL}/_video.mp4")


if __name__ == "__main__":
    tr, tot, gl = render()
    audio(tr, tot, gl)
    print("ok", round(tot, 2), "s")
