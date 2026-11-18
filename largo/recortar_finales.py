"""Quita el arranque de la frase siguiente que ElevenLabs cuela al final de cada audio."""
import json, subprocess, sys, glob
import numpy as np
SR = 44100


def fin_real(x, al):
    chars, ends = al["characters"], al["character_end_times_seconds"]
    k = max(i for i, c in enumerate(chars) if c.isalnum())
    t = ends[k]
    env = np.sqrt(np.convolve(x.astype(np.float64) ** 2, np.ones(441) / 441, mode="same"))
    i = int(t * SR)
    silencio = int(0.08 * SR)
    while i < len(x) - silencio:          # buscar el primer hueco de silencio tras la última letra
        if env[i:i + silencio].max() < 0.004:
            return min(len(x) / SR, i / SR + 0.10)
        i += 220
    return min(len(x) / SR, t + 0.15)


def recortar(base):
    x = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", base + ".mp3", "-f", "f32le", "-ac", "1",
                                               "-ar", str(SR), "-"]), np.float32)
    al = json.load(open(base + ".json"))["alineacion"]
    fin = fin_real(x, al)
    if fin >= len(x) / SR - 0.01:
        return None
    tmp = base + "_tmp.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", base + ".mp3", "-af",
                    f"atrim=end={fin:.3f},areverse,afade=t=in:d=0.04,areverse", "-ar", str(SR), "-ac", "1", tmp], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp, "-b:a", "192k", base + ".mp3"], check=True)
    subprocess.run(["mv", tmp, base + ".wav"])
    return round(len(x) / SR - fin, 3)


if __name__ == "__main__":
    for f in sorted(glob.glob(sys.argv[1] + "/*.json")):
        r = recortar(f[:-5])
        if r:
            print(f.split("/")[-1][:-5], "recortados", r, "s")
