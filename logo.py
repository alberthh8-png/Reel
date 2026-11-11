#!/usr/bin/env python3
"""Identidad visual de GNews: logo, foto de perfil y banner de YouTube.

Todo se dibuja por código (tipografía Inter Display Black Itálica, licencia OFL).
Los iconos de plataformas son genéricos y originales: no se usan logos de marcas.

Uso:  python3 logo.py      -> archivos en marca/
"""
import math
import os
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
FUENTE = os.path.join(RAIZ, "fonts", "InterDisplay-BlackItalic.otf")
FUENTE_TXT = os.path.join(RAIZ, "fonts", "Inter-ExtraBold.otf")
SALIDA = os.path.join(RAIZ, "marca")

MORADO = (150, 60, 255)
MAGENTA = (255, 61, 200)
AZUL = (40, 140, 255)
CIAN = (45, 226, 230)
OSCURO = (8, 6, 22)


def gradiente_vertical(w, h, paradas):
    y = np.linspace(0, 1, h)
    out = np.zeros((h, 3))
    for (p0, c0), (p1, c1) in zip(paradas, paradas[1:]):
        m = (y >= p0) & (y <= p1)
        t = np.clip((y - p0) / max(p1 - p0, 1e-6), 0, 1)[m]
        for k in range(3):
            out[m, k] = c0[k] + (c1[k] - c0[k]) * t
    return Image.fromarray(np.repeat(out[:, None, :], w, 1).astype(np.uint8), "RGB")


def gradiente_horizontal(w, h, c0, c1):
    x = np.linspace(0, 1, w)[None, :, None]
    arr = np.array(c0)[None, None, :] * (1 - x) + np.array(c1)[None, None, :] * x
    return Image.fromarray(np.repeat(arr, h, 0).astype(np.uint8), "RGB")


def mascara_texto(texto, tam):
    f = ImageFont.truetype(FUENTE, tam)
    x0, y0, x1, y1 = f.getbbox(texto)
    pad = int(tam * 0.35)
    m = Image.new("L", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), 0)
    ImageDraw.Draw(m).text((pad - x0, pad - y0), texto, font=f, fill=255)
    return m


def dilatar(m, r):
    return m.filter(ImageFilter.MaxFilter(r * 2 + 1)) if r > 0 else m


def relleno_cromo(m, paradas):
    """Relleno metálico: degradado vertical + franja de brillo + bisel superior."""
    w, h = m.size
    caja = m.getbbox()
    capa = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if not caja:
        return capa
    y0, y1 = caja[1], caja[3]
    grad = gradiente_vertical(w, y1 - y0, paradas)
    base = Image.new("RGB", (w, h), paradas[-1][1])
    base.paste(grad, (0, y0))
    capa = base.convert("RGBA")
    capa.putalpha(m)
    # bisel: borde superior claro, inferior oscuro
    a = np.asarray(m).astype(int)
    arriba = np.clip(a - np.roll(a, 6, 0), 0, 255).astype(np.uint8)
    abajo = np.clip(a - np.roll(a, -6, 0), 0, 255).astype(np.uint8)
    luz = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    luz.putalpha(Image.fromarray(arriba, "L").point(lambda v: int(v * 0.85)))
    sombra = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sombra.putalpha(Image.fromarray(abajo, "L").point(lambda v: int(v * 0.55)))
    capa.alpha_composite(luz)
    capa.alpha_composite(sombra)
    return capa


def logo_wordmark(tam=520):
    """Logo horizontal 'GNews' en PNG transparente."""
    mg, mn = mascara_texto("G", tam), mascara_texto("News", tam)
    bg, bn = mg.getbbox(), mn.getbbox()  # borde real de la tinta de cada parte
    hueco = int(tam * 0.035)
    desp = bg[2] + hueco - bn[0]          # "News" justo a continuación de la "G"
    w = desp + mn.width
    h = max(mg.height, mn.height)
    lienzo = Image.new("RGBA", (w + 200, h + 200), (0, 0, 0, 0))
    ox, oy = 100, 100
    pos_g, pos_n = (ox, oy), (ox + desp, oy)
    m_total = Image.new("L", lienzo.size, 0)
    m_total.paste(mg, pos_g, mg)
    m_total.paste(mn, pos_n, mn)
    # halo exterior: morado a la izquierda y azul a la derecha
    halo_m = dilatar(m_total, 10).filter(ImageFilter.GaussianBlur(38))
    halo = gradiente_horizontal(lienzo.width, lienzo.height, MAGENTA, AZUL).convert("RGBA")
    halo.putalpha(halo_m.point(lambda v: int(v * 0.95)))
    lienzo.alpha_composite(halo)
    # contorno grueso oscuro y contorno neón interior
    borde = Image.new("RGBA", lienzo.size, OSCURO + (0,))
    borde.putalpha(dilatar(m_total, 16))
    lienzo.alpha_composite(borde)
    neon = gradiente_horizontal(lienzo.width, lienzo.height, MAGENTA, CIAN).convert("RGBA")
    neon.putalpha(dilatar(m_total, 7))
    lienzo.alpha_composite(neon)
    interior = Image.new("RGBA", lienzo.size, OSCURO + (0,))  # fino contorno oscuro entre el neón y el relleno
    interior.putalpha(dilatar(m_total, 3))
    lienzo.alpha_composite(interior)
    # rellenos: G morado/magenta metálico, News cromo plateado
    mg_l = Image.new("L", lienzo.size, 0)
    mg_l.paste(mg, pos_g, mg)
    mn_l = Image.new("L", lienzo.size, 0)
    mn_l.paste(mn, pos_n, mn)
    lienzo.alpha_composite(relleno_cromo(mg_l, [(0, (240, 170, 255)), (0.42, (175, 80, 255)), (0.5, (120, 30, 220)),
                                               (0.56, (200, 90, 255)), (1, (90, 20, 170))]))
    lienzo.alpha_composite(relleno_cromo(mn_l, [(0, (255, 255, 255)), (0.4, (220, 228, 245)), (0.5, (150, 160, 185)),
                                               (0.56, (235, 240, 252)), (1, (175, 185, 210))]))
    return lienzo.crop(lienzo.getbbox())


# --------------------------------------------------------------------------
# iconos genéricos de plataformas (dibujos originales, sin marcas)
# --------------------------------------------------------------------------

def icono(tipo, s, col):
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    g = max(4, s // 16)
    c = col + (255,)
    if tipo == "mando":
        d.rounded_rectangle((s * 0.12, s * 0.3, s * 0.88, s * 0.62), radius=int(s * 0.16), outline=c, width=g)
        d.ellipse((s * 0.06, s * 0.42, s * 0.36, s * 0.86), outline=c, width=g)
        d.ellipse((s * 0.64, s * 0.42, s * 0.94, s * 0.86), outline=c, width=g)
        d.rectangle((s * 0.13, s * 0.42, s * 0.87, s * 0.6), fill=(0, 0, 0, 0))
        d.line((s * 0.24, s * 0.4, s * 0.24, s * 0.52), fill=c, width=g)
        d.line((s * 0.18, s * 0.46, s * 0.3, s * 0.46), fill=c, width=g)
        for dx, dy in ((0.74, 0.41), (0.8, 0.47), (0.68, 0.47)):
            d.ellipse((s * dx - g, s * dy - g, s * dx + g, s * dy + g), fill=c)
    elif tipo == "portatil":
        d.rounded_rectangle((s * 0.05, s * 0.3, s * 0.95, s * 0.7), radius=int(s * 0.12), outline=c, width=g)
        d.rectangle((s * 0.3, s * 0.36, s * 0.7, s * 0.64), outline=c, width=g)
        d.ellipse((s * 0.12, s * 0.42, s * 0.22, s * 0.52), outline=c, width=g)
        d.ellipse((s * 0.78, s * 0.48, s * 0.88, s * 0.58), outline=c, width=g)
    elif tipo == "pc":
        d.rounded_rectangle((s * 0.1, s * 0.2, s * 0.9, s * 0.68), radius=int(s * 0.05), outline=c, width=g)
        d.line((s * 0.5, s * 0.68, s * 0.5, s * 0.8), fill=c, width=g)
        d.line((s * 0.3, s * 0.82, s * 0.7, s * 0.82), fill=c, width=g)
    elif tipo == "movil":
        d.rounded_rectangle((s * 0.32, s * 0.12, s * 0.68, s * 0.88), radius=int(s * 0.08), outline=c, width=g)
        d.line((s * 0.44, s * 0.8, s * 0.56, s * 0.8), fill=c, width=g)
    halo = img.getchannel("A").filter(ImageFilter.GaussianBlur(s * 0.06))
    out = Image.new("RGBA", (s, s), col + (0,))
    out.putalpha(halo)
    out.alpha_composite(img)
    return out


# --------------------------------------------------------------------------
# fondo neón original
# --------------------------------------------------------------------------

def fondo_neon(w, h, semilla=3):
    rnd = random.Random(semilla)
    img = gradiente_vertical(w, h, [(0, (10, 6, 30)), (0.5, (16, 10, 46)), (1, (6, 4, 18))]).convert("RGBA")
    # resplandores laterales
    luz = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dl = ImageDraw.Draw(luz)
    dl.ellipse((-w * 0.25, -h * 0.2, w * 0.45, h * 1.2), fill=MORADO + (110,))
    dl.ellipse((w * 0.55, -h * 0.2, w * 1.25, h * 1.2), fill=AZUL + (110,))
    img.alpha_composite(luz.filter(ImageFilter.GaussianBlur(min(w, h) * 0.18)))
    # rejilla en perspectiva
    rej = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(rej)
    hz = h * 0.62
    for i in range(-24, 25):
        dr.line((w / 2 + i * w * 0.012, hz, w / 2 + i * w * 0.09, h), fill=CIAN + (40,), width=2)
    for i in range(1, 14):
        y = hz + (h - hz) * (i / 13) ** 2
        dr.line((0, y, w, y), fill=CIAN + (35,), width=2)
    img.alpha_composite(rej)
    # trazos diagonales de luz (estilo propio)
    trazos = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dt = ImageDraw.Draw(trazos)
    for _ in range(26):
        lado = rnd.choice((-1, 1))
        x = w / 2 + lado * rnd.uniform(w * 0.18, w * 0.5)
        y = rnd.uniform(0, h)
        L = rnd.uniform(w * 0.06, w * 0.22)
        col = MAGENTA if lado < 0 else CIAN
        dt.line((x, y, x + lado * L, y - L * 0.35), fill=col + (rnd.randrange(60, 200),), width=rnd.choice((3, 4, 6)))
    img.alpha_composite(trazos.filter(ImageFilter.GaussianBlur(2)))
    img.alpha_composite(trazos)
    # partículas
    dp = ImageDraw.Draw(img)
    for _ in range(int(w * h / 9000)):
        x, y, r = rnd.uniform(0, w), rnd.uniform(0, h), rnd.choice((1, 1, 2, 3))
        dp.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rnd.randrange(60, 200)))
    return img


def pegar_centro(base, capa, cx, cy):
    base.alpha_composite(capa, (int(cx - capa.width / 2), int(cy - capa.height / 2)))


def ajustar_ancho(img, ancho):
    e = ancho / img.width
    return img.resize((int(img.width * e), int(img.height * e)), Image.LANCZOS)


# --------------------------------------------------------------------------
# piezas
# --------------------------------------------------------------------------

def foto_perfil(logo, S=1080):
    img = fondo_neon(S, S, 7)
    d = ImageDraw.Draw(img)
    cx = cy = S / 2
    # aro neón (todo lo importante dentro del círculo de recorte)
    aro = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    da = ImageDraw.Draw(aro)
    R = S * 0.43
    for k in range(360):
        t = 1 - abs(k / 180 - 1)  # magenta -> cian -> magenta, sin corte
        col = tuple(int(a + (b - a) * t) for a, b in zip(MAGENTA, CIAN))
        da.arc((cx - R, cy - R, cx + R, cy + R), k - 90, k - 89, fill=col + (255,), width=int(S * 0.018))
    img.alpha_composite(aro.filter(ImageFilter.GaussianBlur(S * 0.02)))
    img.alpha_composite(aro)
    # monograma G grande + "NEWS" debajo
    g = logo_g(int(S * 0.62))
    pegar_centro(img, g, cx, cy - S * 0.06)
    f = ImageFont.truetype(FUENTE, int(S * 0.115))
    tx = "NEWS"
    bb = f.getbbox(tx)
    capa = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dc = ImageDraw.Draw(capa)
    dc.text((cx - (bb[2] + bb[0]) / 2, cy + S * 0.2 - (bb[3] + bb[1]) / 2), tx, font=f, fill=(245, 248, 255, 255),
            stroke_width=int(S * 0.012), stroke_fill=OSCURO + (255,))
    img.alpha_composite(capa)
    return img.convert("RGB")


def logo_g(tam):
    m = mascara_texto("G", tam)
    w, h = m.size
    lienzo = Image.new("RGBA", (w + 160, h + 160), (0, 0, 0, 0))
    ml = Image.new("L", lienzo.size, 0)
    ml.paste(m, (80, 80), m)
    halo = gradiente_horizontal(*lienzo.size, MAGENTA, AZUL).convert("RGBA")
    halo.putalpha(dilatar(ml, 8).filter(ImageFilter.GaussianBlur(tam * 0.06)))
    lienzo.alpha_composite(halo)
    borde = Image.new("RGBA", lienzo.size, OSCURO + (0,))
    borde.putalpha(dilatar(ml, max(6, tam // 40)))
    lienzo.alpha_composite(borde)
    neon = gradiente_horizontal(*lienzo.size, MAGENTA, CIAN).convert("RGBA")
    neon.putalpha(dilatar(ml, max(3, tam // 90)))
    lienzo.alpha_composite(neon)
    lienzo.alpha_composite(relleno_cromo(ml, [(0, (240, 170, 255)), (0.42, (175, 80, 255)), (0.5, (120, 30, 220)),
                                             (0.56, (200, 90, 255)), (1, (90, 20, 170))]))
    return lienzo.crop(lienzo.getbbox())


def banner_youtube(logo, W=2560, H=1440):
    img = fondo_neon(W, H, 11)
    cx, cy = W / 2, H / 2
    # zona segura (visible en todos los dispositivos): 1546 x 423 centrada
    sw, sh = 1546, 423
    lg = ajustar_ancho(logo, 1150)
    pegar_centro(img, lg, cx, cy - 20)
    # iconos genéricos a los lados del logo, dentro de la zona segura
    s = 120
    iconos = [("mando", MAGENTA), ("portatil", MORADO), ("pc", AZUL), ("movil", CIAN)]
    for k, (tipo, col) in enumerate(iconos[:2]):
        pegar_centro(img, icono(tipo, s, col), cx - sw / 2 + 80, cy - 90 + k * 175)
    for k, (tipo, col) in enumerate(iconos[2:]):
        pegar_centro(img, icono(tipo, s, col), cx + sw / 2 - 80, cy - 90 + k * 175)
    # eslogan
    f = ImageFont.truetype(FUENTE_TXT, 50)
    tx = "NOTICIAS · TEORÍAS · TRUCOS GAMING"
    bb = f.getbbox(tx)
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dc = ImageDraw.Draw(capa)
    y = cy + sh / 2 - 42
    dc.rounded_rectangle((cx - bb[2] / 2 - 40, y - 40, cx + bb[2] / 2 + 40, y + 40), radius=40,
                         fill=(8, 6, 22, 200), outline=CIAN + (220,), width=3)
    dc.text((cx, y), tx, font=f, fill=(255, 255, 255, 255), anchor="mm")
    img.alpha_composite(capa)
    # cartel lateral (sólo visible en TV/escritorio): nuevo vídeo cada día
    f2 = ImageFont.truetype(FUENTE, 64)
    dc = ImageDraw.Draw(img)
    dc.text((cx, cy - sh / 2 - 120), "▶  NUEVO VÍDEO CADA DÍA", font=f2, fill=(255, 210, 63, 230), anchor="mm")
    return img.convert("RGB")


def vista_previa(perfil, banner):
    """Muestra cómo se ve: perfil recortado en círculo y pequeño, banner con su zona segura."""
    W, H = banner.size
    pv = banner.copy().convert("RGBA")
    d = ImageDraw.Draw(pv)
    sw, sh = 1546, 423
    d.rectangle((W / 2 - sw / 2, H / 2 - sh / 2, W / 2 + sw / 2, H / 2 + sh / 2), outline=(255, 255, 0, 255), width=6)
    d.rectangle((W / 2 - 2560 / 2, H / 2 - 423 / 2, W / 2 + 2560 / 2, H / 2 + 423 / 2), outline=(255, 120, 0, 200), width=4)
    lienzo = Image.new("RGB", (W // 2 + 700, H // 2), (30, 30, 36))
    lienzo.paste(pv.resize((W // 2, H // 2)).convert("RGB"), (0, 0))
    for k, tam in enumerate((400, 160, 64)):
        p = perfil.resize((tam, tam), Image.LANCZOS)
        m = Image.new("L", (tam, tam), 0)
        ImageDraw.Draw(m).ellipse((0, 0, tam - 1, tam - 1), fill=255)
        lienzo.paste(p, (W // 2 + 150 + (0 if k == 0 else (0 if k == 1 else 200)), 40 + (0 if k == 0 else 460)), m)
    return lienzo


def main():
    os.makedirs(SALIDA, exist_ok=True)
    logo = logo_wordmark()
    logo.save(os.path.join(SALIDA, "gnews_logo_transparente.png"))
    perfil = foto_perfil(logo)
    perfil.save(os.path.join(SALIDA, "gnews_perfil_1080.png"))
    banner = banner_youtube(logo)
    banner.save(os.path.join(SALIDA, "gnews_banner_youtube_2560x1440.jpg"), quality=95)
    vista_previa(perfil, banner).save(os.path.join(SALIDA, "vista_previa.jpg"), quality=90)
    print("Listo en", SALIDA)


if __name__ == "__main__":
    main()
