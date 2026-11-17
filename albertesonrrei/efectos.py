"""Utilidades compartidas de los clips de Albertesonrrei."""


def frase_lenta(ws, k, max_antes=2.0, max_despues=2.4, pausa=1.0):
    """Tramo (inicio, fin) en segundos de la transcripción para ralentizar la FRASE que contiene la palabra k.

    La frase se corta en los puntos (. ? !) y en las pausas largas; si es muy larga, se queda con
    ~1,4 s antes y ~2,2 s después de la palabra malsonante, siempre en límites de palabra.
    """
    fin_frase = (".", "?", "!", "»")
    i = k
    while i > 0:
        prev = ws[i - 1]
        if prev["text"].strip().endswith(fin_frase) or ws[i]["start"] - prev["end"] > pausa:
            break
        if ws[k]["start"] - prev["start"] > max_antes:
            break
        i -= 1
    j = k
    while j < len(ws) - 1:
        if ws[j]["text"].strip().endswith(fin_frase) or ws[j + 1]["start"] - ws[j]["end"] > pausa:
            break
        if ws[j + 1]["end"] - ws[k]["end"] > max_despues:
            break
        j += 1
    return ws[i]["start"], ws[j]["end"], i, j


VEL_GRAVE, TONO_GRAVE = 0.85, 0.66  # voz "A1": 85 % de velocidad y bastante más grave (elegida por Albert)


def voz_grave(seg, sr, vel=VEL_GRAVE, tono=TONO_GRAVE):
    """Ralentiza y agrava un trozo de audio mono (float32) con rubberband; devuelve len/vel muestras."""
    import os
    import subprocess
    import tempfile
    import wave

    import numpy as np
    n = int(len(seg) / vel)
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        with wave.open(a, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((np.clip(seg, -1, 1) * 32767).astype(np.int16).tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a, "-af", f"rubberband=tempo={vel}:pitch={tono}",
                        "-ar", str(sr), "-ac", "1", b], check=True)
        with wave.open(b) as w:
            out = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if len(out) < n:
        out = np.pad(out, (0, n - len(out)))
    return out[:n] * 1.15
