"""Voces de la historia "La vuelta": Dan narra, Leónidas grita y fragmentos de Albert con voz grave."""
import base64, json, os, subprocess, sys
import numpy as np, requests
sys.path.insert(0, "/home/user/Reel/largo"); sys.path.insert(0, "/home/user/Reel/albertesonrrei")
from recortar_finales import recortar
from efectos import voz_grave
OUT = "/home/user/Reel/voz/vuelta"; os.makedirs(OUT, exist_ok=True)
TW = "/tmp/claude-0/-home-user-Reel/3efe04a8-bc52-519f-9bff-2b639dd9ba8e/scratchpad/twitch/"
DAN, LEO = "9F4C8ztpNUmXkdDDbz3J", "YKrm0N1EAM9Bw27j8kuD"
S = requests.Session(); S.verify = "/root/.ccr/ca-bundle.crt"
LINEAS = [
 ("d1", DAN, "Atención, pelotuditos."),
 ("d2", DAN, "Desapareció sin avisar. Pero hay cosas que no se olvidan."),
 ("d3", DAN, "El hombre que pidió que le secuestraran..."),
 ("d4", DAN, "El que fue humillado por un tal Hugo..."),
 ("d5", DAN, "Y el que juró dejar este juego para siempre..."),
 ("b1", LEO, "¡¡El pedazo de mierda de Albértesonrréi... ha vuelto!!"),
 ("b2", LEO, "¡¡Hoy a medianoche... el planeta explota!!"),
 ("d6", DAN, "Directo en Twitch, jugando a GTA 6, a las once y media de la noche, hora española."),
 ("d7", DAN, "¿Os venís, pelotuditos?"),
]
FRAG = [("f1", "m8787.wav", 8786.0, 8788.82, 8790.50), ("f2", "m7410.wav", 7410.0, 7459.30, 7462.05),
        ("f3", "m4092.wav", 4092.0, 4099.74, 4101.50)]

def tts(clave, voz, txt):
    out = f"{OUT}/{clave}"
    if os.path.exists(out + ".mp3"): return
    PRE = "... "
    vs = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.45, "use_speaker_boost": True, "speed": 1.0} if voz == DAN \
        else {"stability": 0.3, "similarity_boost": 0.85, "style": 0.8, "use_speaker_boost": True}
    r = S.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voz}/with-timestamps", headers={"xi-api-key": "proxy-injected"},
               json={"text": PRE + txt, "model_id": "eleven_multilingual_v2", "voice_settings": vs}, timeout=120)
    r.raise_for_status(); d = r.json(); al = d["alignment"]
    crudo = out + "_crudo.mp3"; open(crudo, "wb").write(base64.b64decode(d["audio_base64"]))
    x = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", crudo, "-f", "f32le", "-ac", "1", "-ar", "44100", "-"]), np.float32)
    env = np.convolve(np.abs(x), np.ones(220) / 220, mode="same")
    t_al = al["character_start_times_seconds"][len(PRE)]
    i0 = int(max(0.0, t_al - 0.25) * 44100); s = np.nonzero(env[i0:] > 0.004)[0]
    onset = (i0 + s[0]) / 44100 if len(s) else t_al
    corte = max(0.0, min(onset, t_al) - 0.13)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", crudo, "-af", f"atrim=start={corte:.3f},asetpts=N/SR/TB,afade=t=in:d=0.015", "-b:a", "192k", out + ".mp3"], check=True)
    os.remove(crudo)
    al = {k: (v[len(PRE):] if k == "characters" else [max(0.0, t - corte) for t in v[len(PRE):]]) for k, v in al.items()}
    json.dump({"texto": txt, "alineacion": al}, open(out + ".json", "w"), ensure_ascii=False)
    recortar(out)

def fragmento(clave, wav, ini, a, b):
    import wave
    w = wave.open(TW + wav); sr = w.getframerate(); n = w.getnframes()
    y = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768
    if w.getnchannels() == 2: y = y.reshape(-1, 2).mean(1)
    seg = y[int((a - ini) * sr):int((b - ini) * sr)]
    g = voz_grave(seg, sr)
    f = np.ones(len(g)); k = int(0.03 * sr); f[:k] = np.linspace(0, 1, k); f[-k:] = np.linspace(1, 0, k)
    tmp = f"{OUT}/{clave}.raw"; (g * f).astype(np.float32).tofile(tmp)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", tmp, "-af", "loudnorm=I=-16", "-ar", "44100", f"{OUT}/{clave}.wav"], check=True)
    os.remove(tmp)

for c, v, t in LINEAS: tts(c, v, t); print("ok", c)
for fr in FRAG: fragmento(*fr); print("ok", fr[0])
