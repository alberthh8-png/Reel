#!/usr/bin/env python3
"""Versión "original" del clip del camión: el vídeo entero tal cual (sin cortes, sin cámara lenta, sin rótulos),
en vertical con el título POV arriba y el sonido del juego. El encuadre se desliza suave hacia el camión en el bug.
Uso: python3 albertesonrrei/pov_camion_original.py VIDEO.mp4 SALIDA_DIR
"""
import os, subprocess, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pov_camion import cabecera, W, H, Y_J, H_J, ROSA, OSCURO  # noqa: E402

video, salida = sys.argv[1], sys.argv[2]
os.makedirs(salida, exist_ok=True)
fondo = Image.new("RGBA", (W, H), OSCURO + (255,))
fondo.alpha_composite(cabecera())
ImageDraw.Draw(fondo).rectangle((0, Y_J + H_J, W, Y_J + H_J + 5), fill=ROSA)
capa = os.path.join(salida, "_marco.png")
# el marco es opaco salvo la ventana de la partida
a = Image.new("L", (W, H), 255)
ImageDraw.Draw(a).rectangle((0, Y_J, W, Y_J + H_J - 1), fill=0)
fondo.putalpha(a)
fondo.save(capa)
# encuadre 864x1080: centrado en Jason (x=528) y, del 16,6 al 17,6, se desliza suave hasta el camión (x=780)
x = "if(lt(t,16.6),528,if(lt(t,17.6),528+252*(1-cos(PI*(t-16.6)))/2,780))"
fc = (f"[0:v]crop=864:1080:'{x}':0,scale={W}:{H_J}:flags=lanczos,unsharp=5:5:0.6,"
      f"pad={W}:{H}:0:{Y_J}:color=0x0c0818[v];[v][1:v]overlay=0:0,format=yuv420p[out]")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-i", capa, "-filter_complex", fc, "-map", "[out]", "-map", "0:a",
                "-r", "60", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-af", "loudnorm=I=-14:TP=-1.5",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
                os.path.join(salida, "clip.mp4")], check=True)
os.remove(capa)
print("ok")
