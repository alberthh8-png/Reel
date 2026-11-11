#!/usr/bin/env python3
"""Reels del drift con fotos macro realistas y una cámara que "entra" en el mando.

Añade al motor de reel.py:
  - "camara": dibuja una o varias fotos con zoom continuo, temblor opcional y
    transición de zoom que atraviesa una foto y entra en la siguiente.
  - Capas encima de la foto: marcas con etiqueta, partículas, carbono, lecturas,
    un probador de joystick (drift / calibrar / zona muerta), spray de aire,
    tarjeta de garantía, campo magnético y flechas.

Las fotos están en imagenes/drift/ (generadas con IA: mando genérico sin marca).

Uso:
    python3 drift2.py --guion guion_drift_causas.json --salida salida/drift_causas
"""
import math
import random
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter

import reel
import drift  # reutiliza etiqueta(), lectura() y brillo()
from reel import W, H, clamp, ease_out_back, ease_out_cubic, ease_in_out, fuente

CIAN, ROSA, AMARILLO = (45, 226, 230), (255, 61, 139), (255, 210, 63)
ROJO, VERDE, BLANCO = (255, 60, 70), (60, 220, 140), (255, 255, 255)

ESC = 1.5  # resolución interna de las fotos respecto a la pantalla
BW, BH = int(W * ESC), int(H * ESC)
ESTADO = {"crop": (0, 0, BW, BH)}  # transformación de la foto en el fotograma actual


@lru_cache(maxsize=16)
def foto_base(ruta):
    img = Image.open(reel.os.path.join(reel.RAIZ, ruta)).convert("RGB")
    e = max(BW / img.width, BH / img.height)
    img = img.resize((int(img.width * e) + 1, int(img.height * e) + 1), Image.LANCZOS)
    x, y = (img.width - BW) // 2, (img.height - BH) // 2
    return img.crop((x, y, x + BW, y + BH))


def recorte(z, foco):
    w, h = BW / z, BH / z
    cx = clamp(foco[0] * BW, w / 2, BW - w / 2)
    cy = clamp(foco[1] * BH, h / 2, BH - h / 2)
    return (cx - w / 2, cy - h / 2, w, h)


def render_foto(ruta, z, foco, desenfoque=0.0, temblor=(0, 0)):
    base = foto_base(ruta)
    zs = [z] if desenfoque < 0.01 else [z, z * (1 + desenfoque), z * (1 + 2 * desenfoque)]
    capas = []
    for zz in zs:
        x, y, w, h = recorte(zz, foco)
        x = clamp(x + temblor[0] * w / W, 0, BW - w)
        y = clamp(y + temblor[1] * h / H, 0, BH - h)
        capas.append(base.resize((W, H), Image.BILINEAR, box=(x, y, x + w, y + h)))
    if len(capas) == 1:
        img = capas[0]
    else:
        img = Image.blend(Image.blend(capas[0], capas[1], 0.5), capas[2], 0.33)
    ESTADO["crop"] = recorte(z, foco)
    return img.convert("RGBA")


def a_pantalla(fx, fy):
    x, y, w, h = ESTADO["crop"]
    return ((fx * BW - x) / w * W, (fy * BH - y) / h * H)


def mezcla_foco(a, b, k):
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)


class Camara(reel.Efecto):
    """Planos de foto con empuje de cámara y zoom que atraviesa de un plano al siguiente."""

    SALIDA = 0.42  # duración del zoom que atraviesa
    ENTRADA = 0.25

    def __init__(self, ev, semilla):
        self.planos = ev["planos"]
        self.dur = ev["dur"]
        self.sale = ev.get("sale")  # foco hacia el que se atraviesa al final de la escena
        self.entra = ev.get("entra", True)

    def dibujar(self, frame, t, mapa):
        i = 0
        for k, p in enumerate(self.planos):
            if t >= p.get("desde", 0):
                i = k
        p = self.planos[i]
        ini = p.get("desde", 0)
        fin = self.planos[i + 1]["desde"] if i + 1 < len(self.planos) else self.dur
        a, pd = t - ini, max(0.01, fin - ini)
        z0, z1 = p.get("z", [1.0, 1.2])
        u = clamp(a / pd)
        z = z0 + (z1 - z0) * (1 - (1 - u) ** 2)
        foco = tuple(p.get("foco", [0.5, 0.5]))
        if "foco_fin" in p:
            foco = mezcla_foco(foco, p["foco_fin"], ease_in_out(u))
        desenfoque = 0.0
        objetivo = None
        if i + 1 < len(self.planos):
            objetivo = p.get("sale", foco)
        elif self.sale:
            objetivo = self.sale
        if objetivo is not None and a > pd - self.SALIDA:
            k = ((a - (pd - self.SALIDA)) / self.SALIDA) ** 2
            z *= 1 + 2.6 * k
            foco = mezcla_foco(foco, objetivo, min(1, k * 2))
            desenfoque = 0.06 * k
        if a < self.ENTRADA and (i > 0 or self.entra):
            desenfoque = max(desenfoque, 0.06 * (1 - a / self.ENTRADA))
        tem = p.get("temblor", 0)
        temblor = (math.sin(t * 31) * tem, math.cos(t * 27) * tem * 0.6) if tem else (0, 0)
        frame.alpha_composite(render_foto(p["foto"], z, foco, desenfoque, temblor))
        if objetivo is not None and a > pd - 0.12:  # destello de luz al "atravesar"
            k = (a - (pd - 0.12)) / 0.12
            velo = Image.new("RGBA", (W, H), (255, 255, 255, int(110 * k)))
            frame.alpha_composite(velo)


class Ventana(reel.Efecto):
    """Base para capas que sólo se ven entre t0 y t1."""

    def __init__(self, ev, semilla):
        self.ev = ev
        self.t0 = ev.get("t", 0.0)
        self.t1 = ev.get("hasta", 99)

    def vis(self, t):
        if t < self.t0 or t > self.t1:
            return 0.0
        return clamp((t - self.t0) / 0.25) * clamp((self.t1 - t) / 0.15)


class Marca(Ventana):
    """Anillo sobre un punto de la foto con etiqueta y línea guía."""

    def dibujar(self, frame, t, mapa):
        v = self.vis(t)
        if v <= 0:
            return
        col = tuple(self.ev.get("color", CIAN))
        x, y = a_pantalla(*self.ev["punto"])
        a = t - self.t0
        r = self.ev.get("radio", 70) * (0.6 + 0.4 * ease_out_back(a / 0.35)) + 6 * math.sin(a * 8)
        d = ImageDraw.Draw(frame)
        al = int(255 * v)
        d.ellipse((x - r, y - r, x + r, y + r), outline=col + (al,), width=7)
        d.ellipse((x - r - 14, y - r - 14, x + r + 14, y + r + 14), outline=col + (int(al * 0.35),), width=3)
        if self.ev.get("texto"):
            lx, ly = self.ev.get("etiqueta", (x + 200, y - 160))
            ang = math.atan2(ly - y, lx - x)
            drift.etiqueta(frame, self.ev["texto"], x + math.cos(ang) * r, y + math.sin(ang) * r, (lx, ly),
                           (a - 0.15) / 0.3 * v, col)


class Particulas(Ventana):
    """Motas en suspensión con desenfoque (polvo, humedad...)."""

    def __init__(self, ev, semilla):
        super().__init__(ev, semilla)
        rnd = random.Random(semilla)
        self.p = [(rnd.uniform(0, W), rnd.uniform(0, 1100), rnd.uniform(3, ev.get("tam", 9)), rnd.uniform(-1, 1),
                   rnd.uniform(0.3, 1.0)) for _ in range(ev.get("n", 70))]

    def dibujar(self, frame, t, mapa):
        v = self.vis(t)
        if v <= 0:
            return
        col = tuple(self.ev.get("color", (230, 210, 170)))
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(capa)
        for x, y, r, dx, al in self.p:
            px = (x + dx * 40 * t + math.sin(t * 1.3 + y) * 18) % W
            py = (y - 25 * t * al) % 1100
            d.ellipse((px - r, py - r, px + r, py + r), fill=col + (int(200 * al * v),))
        frame.alpha_composite(capa.filter(ImageFilter.GaussianBlur(1.6)))


class Carbono(Ventana):
    """Escamas de carbono que salen despedidas del punto de roce."""

    def __init__(self, ev, semilla):
        super().__init__(ev, semilla)
        rnd = random.Random(semilla)
        self.p = [(rnd.uniform(0, 1.5), rnd.uniform(-2.8, -0.3), rnd.uniform(120, 420), rnd.uniform(4, 11))
                  for _ in range(90)]

    def dibujar(self, frame, t, mapa):
        v = self.vis(t)
        if v <= 0:
            return
        x0, y0 = a_pantalla(*self.ev["punto"])
        a = t - self.t0
        d = ImageDraw.Draw(frame)
        for nace, ang, vel, r in self.p:
            b = (a - nace) % 1.5
            px = x0 + math.cos(ang) * vel * b
            py = y0 + math.sin(ang) * vel * b + 380 * b * b
            al = int(255 * v * clamp(1 - b / 1.5))
            d.polygon([(px - r, py), (px, py - r * 0.6), (px + r * 0.8, py + r * 0.4), (px - r * 0.2, py + r * 0.8)],
                      fill=(12, 10, 14, al), outline=(90, 90, 100, al))


class Lectura(Ventana):
    """Valor que lee la consola. modo: drift (sube a valor, rojo) | ok (0.00 verde) | baila."""

    def dibujar(self, frame, t, mapa):
        v = self.vis(t)
        if v <= 0:
            return
        a = t - self.t0
        modo = self.ev.get("modo", "drift")
        if modo == "drift":
            val = self.ev.get("valor", 0.14) * ease_out_cubic(a / 0.8) + 0.01 * math.sin(a * 23)
            col = ROJO if a > 0.4 else VERDE
        elif modo == "ok":
            val, col = 0.0, VERDE
        else:
            val, col = math.sin(a * 2.5) * 0.8, VERDE
        x, y = self.ev.get("pos", (250, 960))
        drift.lectura(frame, x, y, self.ev.get("eje", "X"), val, col)


class Probador(Ventana):
    """Probador de joystick: círculo con el punto que marca la posición del stick."""

    def dibujar(self, frame, t, mapa):
        v = self.vis(t)
        if v <= 0:
            return
        a = t - self.t0
        x, y = self.ev.get("pos", (800, 330))
        r = self.ev.get("radio", 130)
        modo = self.ev.get("modo", "drift")
        d = ImageDraw.Draw(frame)
        al = int(240 * v)
        d.rounded_rectangle((x - r - 34, y - r - 34, x + r + 34, y + r + 90), radius=26, fill=(6, 10, 26, int(225 * v)),
                            outline=CIAN + (al,), width=4)
        d.ellipse((x - r, y - r, x + r, y + r), outline=(120, 140, 180, al), width=4)
        d.line((x - r, y, x + r, y), fill=(70, 90, 130, al), width=2)
        d.line((x, y - r, x, y + r), fill=(70, 90, 130, al), width=2)
        deriva = (0.32 + 0.04 * math.sin(a * 17), -0.12 + 0.03 * math.cos(a * 13))
        col, dx, dy, txt = ROJO, deriva[0] * ease_out_cubic(a / 0.6), deriva[1] * ease_out_cubic(a / 0.6), "DRIFT"
        f = fuente(max(26, int(r * 0.26)))
        if modo == "calibrar":
            prog = clamp((a - 0.5) / 1.4)
            if 0 < prog < 1:
                d.rounded_rectangle((x - r, y + r + 30, x + r, y + r + 58), radius=12, outline=CIAN + (al,), width=3)
                d.rounded_rectangle((x - r + 4, y + r + 34, x - r + 4 + (2 * r - 8) * prog, y + r + 54), radius=10,
                                    fill=CIAN + (al,))
                txt, col = "CALIBRANDO…", AMARILLO
            elif prog >= 1:
                k = ease_out_cubic((a - 1.9) / 0.3)
                dx, dy = deriva[0] * (1 - k), deriva[1] * (1 - k)
                col, txt = VERDE, "CENTRO = 0.00"
        elif modo == "zona_muerta":
            k = ease_out_back((a - 0.6) / 0.6)
            rz = r * (0.08 + 0.32 * clamp(k, 0, 1.2))
            d.ellipse((x - rz, y - rz, x + rz, y + rz), fill=AMARILLO + (int(70 * v),), outline=AMARILLO + (al,), width=4)
            if math.hypot(dx, dy) * r < rz:
                col, txt = VERDE, "IGNORADO = 0.00"
        px, py = x + dx * r, y + dy * r
        d.ellipse((px - 18, py - 18, px + 18, py + 18), fill=col + (al,))
        d.text((x, y + r + (74 if modo == "calibrar" and col == AMARILLO else 50)), txt, font=f, fill=col + (al,),
               anchor="mm")


class Spray(Ventana):
    """Chorro de aire comprimido (de origen a destino, en coordenadas de la foto)."""

    def __init__(self, ev, semilla):
        super().__init__(ev, semilla)
        rnd = random.Random(semilla)
        self.p = [(rnd.uniform(0, 1), rnd.uniform(-1, 1), rnd.uniform(0.5, 1.2)) for _ in range(120)]

    def dibujar(self, frame, t, mapa):
        v = self.vis(t)
        if v <= 0:
            return
        x0, y0 = a_pantalla(*self.ev["desde"])
        x1, y1 = a_pantalla(*self.ev["hacia"])
        L = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(capa)
        for fase, lat, vel in self.p:
            k = (fase + t * 2.2 * vel) % 1
            px = x0 + ux * L * k - uy * lat * 40 * k
            py = y0 + uy * L * k + ux * lat * 40 * k
            d.line((px, py, px - ux * 40, py - uy * 40), fill=(230, 245, 255, int(170 * v * (1 - k * 0.5))), width=3)
        for k in range(14):  # polvo que sale despedido
            ang = k * 0.45 + t * 3
            b = (t * 1.5 + k * 0.07) % 1
            px, py = x1 + math.cos(ang) * 260 * b, y1 + math.sin(ang) * 160 * b - 120 * b
            d.ellipse((px - 6, py - 6, px + 6, py + 6), fill=(220, 200, 160, int(200 * v * (1 - b))))
        frame.alpha_composite(capa.filter(ImageFilter.GaussianBlur(1)))


class Garantia(Ventana):
    """Ticket de compra con sello de 3 años."""

    def dibujar(self, frame, t, mapa):
        v = self.vis(t)
        if v <= 0:
            return
        a = t - self.t0
        tk = Image.new("RGBA", (440, 560), (0, 0, 0, 0))
        d = ImageDraw.Draw(tk)
        d.rectangle((0, 0, 439, 540), fill=(248, 248, 244, 255))
        for k in range(12):
            d.polygon([(k * 37, 540), (k * 37 + 18, 559), (k * 37 + 37, 540)], fill=(248, 248, 244, 255))
        d.text((220, 50), "TICKET DE COMPRA", font=fuente(30), fill=(30, 30, 40, 255), anchor="mm")
        for k, ancho in enumerate((300, 250, 330, 200, 280, 310)):
            d.rounded_rectangle((40, 110 + k * 46, 40 + ancho, 124 + k * 46), radius=6, fill=(180, 180, 190, 255))
        d.line((40, 420, 400, 420), fill=(60, 60, 70, 255), width=3)
        d.text((40, 470), "MANDO", font=fuente(34), fill=(30, 30, 40, 255), anchor="lm")
        p = ease_out_back(a / 0.4)
        reel.pegar_centrado(frame, tk, 540, 560, escala=p * 0.95, alfa=v, angulo=-6)
        if a > 0.5:
            s = ease_out_back((a - 0.5) / 0.25, 3)
            sello = Image.new("RGBA", (420, 230), (0, 0, 0, 0))
            ds = ImageDraw.Draw(sello)
            ds.rounded_rectangle((10, 10, 410, 220), radius=24, outline=ROJO + (255,), width=12)
            ds.text((210, 95), "3 AÑOS", font=fuente(104), fill=ROJO + (255,), anchor="mm")
            ds.text((210, 178), "DE GARANTÍA", font=fuente(40), fill=ROJO + (255,), anchor="mm")
            reel.pegar_centrado(frame, sello, 560, 560, escala=(2.2 - 1.2 * s), alfa=v * clamp(s), angulo=14)


class Campo(Ventana):
    """Líneas de campo magnético alrededor de un punto de la foto."""

    def dibujar(self, frame, t, mapa):
        v = self.vis(t)
        if v <= 0:
            return
        x, y = a_pantalla(*self.ev["punto"])
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(capa)
        for k in range(1, 7):
            fase = (t * 1.2 + k * 0.17) % 1
            ancho, alto = 70 + k * 40, 30 + k * 22
            for lado in (-1, 1):
                d.arc((x + lado * ancho * 0.5 - ancho * 0.5, y - alto, x + lado * ancho * 0.5 + ancho * 0.5, y + alto),
                      0, 360, fill=CIAN + (int(170 * v * (1 - 0.5 * fase)),), width=3)
        frame.alpha_composite(drift.brillo(capa, CIAN, 8, 0.8))
        frame.alpha_composite(capa)


class Flechas(Ventana):
    """Dos flechas que se separan (estirar) o vibran (holgura) alrededor de un punto."""

    def dibujar(self, frame, t, mapa):
        v = self.vis(t)
        if v <= 0:
            return
        x, y = a_pantalla(*self.ev["punto"])
        a = t - self.t0
        sep = self.ev.get("sep", 150)
        if self.ev.get("modo") == "holgura":
            off = math.sin(a * 22) * 20
        else:
            off = 40 * ease_in_out((a % 1.2) / 1.2)
        d = ImageDraw.Draw(frame)
        col = tuple(self.ev.get("color", AMARILLO)) + (int(255 * v),)
        for lado in (-1, 1):
            bx = x + lado * (sep + off)
            d.line((bx - lado * 70, y, bx, y), fill=col, width=12)
            d.polygon([(bx + lado * 34, y), (bx, y - 26), (bx, y + 26)], fill=col)


reel.FX.update({"camara": Camara, "marca": Marca, "particulas": Particulas, "carbono": Carbono,
                "lectura": Lectura, "probador": Probador, "spray": Spray, "garantia": Garantia,
                "campo": Campo, "flechas": Flechas})

if __name__ == "__main__":
    reel.main()
