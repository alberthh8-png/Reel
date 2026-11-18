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
 ("l1", LEO, "¡¡Eeeeh, tú!! Me parece que no te has dado cuenta de que..."),
 ("l2", LEO, "...alguien desapareció sin avisar. Pero hay cosas que no se olvidan."),
 ("l3", LEO, "¡¡El pedazo de mierda de Alberte sonrreí... ha vuelto!!"),
 ("l4", LEO, "¡¡Hoy a medianoche... la luna... [inhales deeply] ¡impacta contra la Tierra! ...como los huevos de este hombre!!"),
 ("l5", LEO, "Directo en Twitch, jugando a GTA 6, a las once y media de la noche, hora española."),
 ("l6", LEO, "¿Os venís, pelotuditos?"),
 ("l7", LEO, "¡¡Quien no venga... come miembros!!"),
]
# fragmentos de Albert con SU voz normal (sin voz grave): (clave, wav, inicio_wav, [(desde, hasta), ...])
FRAG = [("a_hugo", "m7410.wav", 7410.0, [(7459.30, 7462.05)]),
        ("a_joaquin", "m4092.wav", 4092.0, [(4094.18, 4094.75), (4099.74, 4101.50)])]

def tts(clave, voz, txt):
    out = f"{OUT}/{clave}"
    if os.path.exists(out + ".mp3"): return
    PRE = "... "
    grito = txt.startswith("¡¡")
    vs = {"stability": 0.3 if grito else 0.4, "similarity_boost": 0.85, "style": 0.8 if grito else 0.6, "use_speaker_boost": True}
    r = S.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voz}/with-timestamps", headers={"xi-api-key": "proxy-injected"},
               json={"text": PRE + txt, "model_id": "eleven_v3" if "[" in txt else "eleven_multilingual_v2", "voice_settings": vs if "[" not in txt else {"stability": 0.5, "similarity_boost": 0.85, "style": 0.8, "use_speaker_boost": True}}, timeout=120)
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

def fragmento(clave, wav, ini, tramos):
    import wave
    w = wave.open(TW + wav); sr = w.getframerate(); n = w.getnframes()
    y = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768
    if w.getnchannels() == 2: y = y.reshape(-1, 2).mean(1)
    partes = []
    for a, b in tramos:
        seg = y[int((a - ini) * sr):int((b - ini) * sr)].copy()
        k = int(0.02 * sr); seg[:k] *= np.linspace(0, 1, k); seg[-k:] *= np.linspace(1, 0, k)
        partes.append(seg)
    g = np.concatenate(partes)
    tmp = f"{OUT}/{clave}.raw"; g.astype(np.float32).tofile(tmp)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", tmp, "-af", "loudnorm=I=-16", "-ar", "44100", f"{OUT}/{clave}.wav"], check=True)
    os.remove(tmp)

for c, v, t in LINEAS: tts(c, v, t); print("ok", c)
for fr in FRAG: fragmento(*fr); print("ok", fr[0])
