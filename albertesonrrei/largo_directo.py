#!/usr/bin/env python3
"""Vídeo largo de YouTube (1920x1080, 60 fps) con lo mejor de un directo de Twitch de Albertesonrrei.

Entrada (en DIR): segmentos.json  -> [[nombre, titulo_capitulo, inicio, fin], ...] (segundos del directo)
                  ts/NOMBRE.json  -> {"inicio": segundo del directo donde empieza NOMBRE.mp4}
                  NOMBRE.mp4      -> trozo del directo (1280x720, 60 fps)
                  extras.json     -> {"chat": [[nombre, t_directo, duracion], ...],   zoom al chat
                                      "graves": [[nombre, t0, t1], ...],              voz grave E (vídeo y audio lentos)
                                      "avance": [[nombre, t0, t1], ...],              avance del principio
                                      "titulo": "...", "subtitulo": "..."}
Uso: python3 albertesonrrei/largo_directo.py DIR SALIDA_DIR [--solo NOMBRE ...] [--unir]
"""
import argparse, json, os, subprocess, sys
from multiprocessing import Pool
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reel  # noqa: E402
from reel import ajustar_fuente, texto_con_estilo  # noqa: E402
from albertesonrrei.efectos import VEL_GRAVE  # noqa: E402

W, H, FPS = 1920, 1080, 60
ROSA, AMARILLO, BLANCO, OSCURO = (255, 61, 139), (255, 210, 63), (255, 255, 255), (12, 8, 24)
# zona del chat en el directo (1280x720) y zoom al que se acerca la cámara
CHAT_CX, CHAT_CY, ZOOM_CHAT = 175, 545, 2.3
GRAVE_AF = f"asetrate=48000*{VEL_GRAVE},aresample=48000,bass=g=14:f=90,acrusher=bits=10:mix=0.25,alimiter"
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def tarjeta(texto, ruta):
    """Rótulo de capítulo: franja oscura con el título (PNG transparente 1920x1080)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    banda = Image.new("RGBA", (W, 230), OSCURO + (215,))
    d = ImageDraw.Draw(banda)
    d.rectangle((0, 0, W, 6), fill=ROSA)
    d.rectangle((0, 224, W, 230), fill=ROSA)
    im.alpha_composite(banda, (0, H - 330))
    f = ajustar_fuente(texto, 1500, 110, tam_min=60, borde=10)
    t = texto_con_estilo(texto, f, AMARILLO + (255,), borde=10, color_borde=(0, 0, 0), brillo=ROSA)
    im.alpha_composite(t, ((W - t.width) // 2, H - 330 + 115 - t.height // 2))
    im.save(ruta)


def portada(titulo, subtitulo, ruta):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    banda = Image.new("RGBA", (W, 360), OSCURO + (225,))
    ImageDraw.Draw(banda).rectangle((0, 0, W, 8), fill=ROSA)
    ImageDraw.Draw(banda).rectangle((0, 352, W, 360), fill=ROSA)
    im.alpha_composite(banda, (0, (H - 360) // 2))
    t1 = texto_con_estilo(titulo, ajustar_fuente(titulo, 1700, 120, tam_min=60, borde=10), AMARILLO + (255,),
                          borde=10, color_borde=(0, 0, 0), brillo=ROSA)
    t2 = texto_con_estilo(subtitulo, ajustar_fuente(subtitulo, 1600, 70, tam_min=40, borde=8), BLANCO + (255,),
                          borde=8, color_borde=(0, 0, 0))
    im.alpha_composite(t1, ((W - t1.width) // 2, H // 2 - 60 - t1.height // 2))
    im.alpha_composite(t2, ((W - t2.width) // 2, H // 2 + 85 - t2.height // 2))
    im.save(ruta)


def partes(nombre, a, b, graves):
    """Divide [a, b] en tramos normales y lentos (voz grave)."""
    cortes = sorted([(g0, g1) for n, g0, g1 in graves if n == nombre and a <= g0 < b])
    out, s = [], a
    for g0, g1 in cortes:
        g1 = min(g1, b)
        if g0 > s:
            out.append((s, g0, False))
        out.append((g0, g1, True))
        s = g1
    if s < b:
        out.append((s, b, False))
    return out


def zoom_expr(zonas):
    """Expresión de zoom (sobre el tiempo de salida del tramo) para acercarse al chat en cada zona."""
    if not zonas:
        return None
    partes_ = []
    for u0, u1 in zonas:
        # sube en 0,45 s, se mantiene y baja en 0,45 s (curva suave)
        partes_.append(f"if(between(t,{u0:.3f},{u1:.3f}),"
                       f"min(1,min((t-{u0:.3f})/0.45,({u1:.3f}-t)/0.45)),0)")
    k = "max(" + ",".join(partes_) + ")" if len(partes_) > 1 else partes_[0]
    k = f"(0.5-0.5*cos(PI*min(1,{k})))"
    return k


def render_tramo(args):
    dir_, salida, seg, extras, es_avance = args
    nombre, titulo, a, b = seg
    ini = json.load(open(os.path.join(dir_, "ts", f"{nombre}.json")))["inicio"]
    src = os.path.join(dir_, f"{nombre}.mp4")
    out = os.path.join(salida, "tramos", f"{'av_' if es_avance else ''}{nombre}_{a:.0f}.mp4")
    if os.path.exists(out):
        return out
    trozos = partes(nombre, a, b, [] if es_avance else extras.get("graves", []))
    # tiempo de salida de cada instante del directo (para colocar los zooms al chat)
    def u_de(t):
        u = 0.0
        for s0, s1, lento in trozos:
            if t <= s1:
                return u + (t - s0) / (VEL_GRAVE if lento else 1)
            u += (s1 - s0) / (VEL_GRAVE if lento else 1)
        return u
    zonas = [(u_de(t), u_de(t) + d) for n, t, d in extras.get("chat", []) if n == nombre and a <= t < b and not es_avance]
    fc, vs = [], []
    for i, (s0, s1, lento) in enumerate(trozos):
        vt = f"[0:v]trim={s0 - ini:.3f}:{s1 - ini:.3f},setpts=PTS-STARTPTS"
        at = f"[0:a]atrim={s0 - ini:.3f}:{s1 - ini:.3f},asetpts=PTS-STARTPTS"
        if lento:
            vt += f",setpts=PTS/{VEL_GRAVE}"
            at += "," + GRAVE_AF
        fc.append(vt + f",fps={FPS}[v{i}]")
        fc.append(at + f",aresample=48000[a{i}]")
        vs.append(f"[v{i}][a{i}]")
    fc.append("".join(vs) + f"concat=n={len(trozos)}:v=1:a=1[vc][ac]")
    k = zoom_expr(zonas)
    if k:
        kt = k.replace("t,", "it,").replace("-t)", "-it)").replace("(t-", "(it-")
        # zoompan (tamaño de salida fijo): se escala a 4K para que el movimiento sea suave y se acerca al chat
        cx = f"(({CHAT_CX})*{kt}+640*(1-{kt}))"
        cy = f"(({CHAT_CY})*{kt}+360*(1-{kt}))"
        fc.append(f"[vc]scale=3840:2160:flags=bicubic,"
                  f"zoompan=z='1+({ZOOM_CHAT}-1)*{kt}':d=1:fps={FPS}:s={W}x{H}:"
                  f"x='max(0,min(iw-iw/zoom,{cx}*iw/1280-iw/zoom/2))':y='max(0,min(ih-ih/zoom,{cy}*ih/720-ih/zoom/2))'[vz]")
        vlast = "[vz]"
    else:
        fc.append(f"[vc]scale={W}:{H}:flags=lanczos[vz]")
        vlast = "[vz]"
    if nombre in extras.get("tapar_chat", []):
        # chat difuminado (p. ej. si se queda fijo un mensaje ofensivo de un espectador)
        fc.append(f"{vlast}split[tc0][tc1];[tc1]crop=500:500:15:572,boxblur=18:3[tcb];[tc0][tcb]overlay=15:572[vtc]")
        vlast = "[vtc]"
    dur = sum((s1 - s0) / (VEL_GRAVE if l else 1) for s0, s1, l in trozos)
    entradas = ["-i", src]
    if titulo and not es_avance:
        png = os.path.join(salida, "tramos", f"tit_{nombre}.png")
        tarjeta(titulo, png)
        entradas += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
        fc.append(f"[1:v]format=rgba,fade=t=in:st=0.2:d=0.35:alpha=1,fade=t=out:st=2.9:d=0.4:alpha=1[tc];"
                  f"{vlast}[tc]overlay=0:0:shortest=1[vt]")
        vlast = "[vt]"
    fd = 0.12
    fc.append(f"{vlast}unsharp=5:5:0.5,fade=t=in:d={fd},fade=t=out:st={max(0, dur - fd):.3f}:d={fd},format=yuv420p[vf]")
    fc.append(f"[ac]afade=t=in:d={fd},afade=t=out:st={max(0, dur - fd):.3f}:d={fd}[af]")
    cmd = ["ffmpeg", "-y", "-v", "error"] + entradas + ["-filter_complex", ";".join(fc), "-map", "[vf]", "-map", "[af]",
                                                         "-t", f"{dur:.3f}"] + ENC + [out]
    subprocess.run(cmd, check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("salida")
    ap.add_argument("--solo", nargs="*")
    ap.add_argument("--unir", action="store_true")
    ap.add_argument("--procesos", type=int, default=3)
    a = ap.parse_args()
    S = json.load(open(os.path.join(a.dir, "segmentos.json")))
    extras = json.load(open(os.path.join(a.dir, "extras.json")))
    os.makedirs(os.path.join(a.salida, "tramos"), exist_ok=True)
    trabajos = []
    for n, t0, t1 in extras.get("avance", []):
        trabajos.append((a.dir, a.salida, [n, "", t0, t1], extras, True))
    for seg in S:
        if not a.solo or seg[0] in a.solo:
            trabajos.append((a.dir, a.salida, seg, extras, False))
    if not a.unir:
        with Pool(a.procesos) as p:
            for r in p.imap_unordered(render_tramo, trabajos):
                print("ok", os.path.basename(r), flush=True)
    if a.unir or not a.solo:
        # portada del avance -> se pega sobre el primer tramo del avance
        orden = [render_tramo(t) for t in trabajos]
        av = [o for o, t in zip(orden, trabajos) if t[4]]
        resto = [o for o, t in zip(orden, trabajos) if not t[4]]
        portada_png = os.path.join(a.salida, "tramos", "portada.png")
        portada(extras.get("titulo", ""), extras.get("subtitulo", ""), portada_png)
        lista = os.path.join(a.salida, "tramos", "lista.txt")
        with open(lista, "w") as f:
            for o in av + resto:
                f.write(f"file '{os.path.abspath(o)}'\n")
        crudo = os.path.join(a.salida, "tramos", "_unido.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", crudo],
                       check=True)
        dur_av = sum(t1 - t0 for _, t0, t1 in extras.get("avance", []))
        # portada al final del avance (2,8 s) + sonido normalizado a -14 LUFS
        fc = (f"[1:v]format=rgba,fade=t=in:st={dur_av - 3.2:.2f}:d=0.3:alpha=1,fade=t=out:st={dur_av - 0.3:.2f}:d=0.3:alpha=1[p];"
              f"[0:v][p]overlay=0:0:enable='between(t,{dur_av - 3.2:.2f},{dur_av:.2f})',format=yuv420p[v];"
              f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", crudo, "-loop", "1", "-t", f"{dur_av + 0.1:.2f}", "-i",
                        portada_png, "-filter_complex", fc, "-map", "[v]", "-map", "[a]"] + ENC +
                       ["-movflags", "+faststart", os.path.join(a.salida, "video.mp4")], check=True)
        os.remove(crudo)
        print("listo", os.path.join(a.salida, "video.mp4"))


if __name__ == "__main__":
    main()
