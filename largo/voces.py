"""Genera la voz de Dan párrafo a párrafo (con marcas de tiempo por carácter)."""
import json, base64, sys, os, subprocess, requests
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recortar_finales import recortar
from concurrent.futures import ThreadPoolExecutor
VOZ = "9F4C8ztpNUmXkdDDbz3J"
PRON = {"MrBeast": "Mister Bist", "Sensor Tower": "Sénsor Táuer", "Cyberpunk 2077": "Cyberpunk dos mil setenta y siete",
        "Grassrivers": "Grass Rívers", "Port Gellhorn": "Port Guélhorn", "Bonnie y Clyde": "Boni y Claid",
        "Red Dead Redemption 2": "Red Ded Redémpshon dos", " X,": " equis,", "GTA Online": "GTA Online",
        "Kick": "Kik", "Leonida": "Leónida", "GNews": "Yi Nius", "Brian,": "Bráian,", "Brian ": "Bráian ", "Warzone": "Guórsoun", "Deadpool y Lobezno": "Dédpul y Lobezno", "Boobie Ike": "Búbi Áik", "Brian Heder": "Bráian Jéder", "Phil Cassidy": "Fil Cásidi", "Take-Two": "Teik Tú", "Cal Hampton": "Cal Jámpton", "CJ": "Ci Yei"}
def pron(t):
    for a, b in PRON.items(): t = t.replace(a, b)
    return t
S = requests.Session()
S.verify = "/root/.ccr/ca-bundle.crt"
def gen(args):
    cid, i, txt, prev, nxt, out = args
    if os.path.exists(out + ".mp3") and "--forzar" not in sys.argv: return out
    PRE = "... "   # arranque natural: sin esto Dan empieza la frase de golpe (se oye entrecortado)
    body = {"text": PRE + pron(txt), "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True, "speed": 0.96},
            "previous_text": pron(prev)}   # sin next_text: con él, Dan alarga el final y se cuela la frase siguiente
    for _ in range(4):
        r = S.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ}/with-timestamps", json=body,
                   headers={"xi-api-key": "proxy-injected"}, timeout=180)
        if r.ok: break
        print("reintento", out, r.status_code, r.text[:200])
    r.raise_for_status(); d = r.json()
    al = d["alignment"]
    crudo = out + "_crudo.mp3"
    open(crudo, "wb").write(base64.b64decode(d["audio_base64"]))
    # arranque real de la voz medido en el audio (la alineación a veces va adelantada)
    x = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", crudo, "-f", "f32le", "-ac", "1", "-ar", "44100", "-"]), np.float32)
    env = np.convolve(np.abs(x), np.ones(220) / 220, mode="same")
    t_al = al["character_start_times_seconds"][len(PRE)]
    i0 = int(max(0.0, t_al - 0.25) * 44100)
    sobre = np.nonzero(env[i0:] > 0.004)[0]
    onset = (i0 + sobre[0]) / 44100 if len(sobre) else t_al
    corte = max(0.0, min(onset, t_al) - 0.13)   # 130 ms de aire antes de la voz
    # final: cortar justo después de la última letra (si no, se cuela el arranque de la frase siguiente)
    fin = al["character_end_times_seconds"][-1] + 0.18
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", crudo, "-af", f"atrim=start={corte:.3f}:end={fin:.3f},asetpts=N/SR/TB,afade=t=in:d=0.015,areverse,afade=t=in:d=0.06,areverse",
                    "-b:a", "192k", out + ".mp3"], check=True)
    os.remove(crudo)
    al = {k: (v[len(PRE):] if k == "characters" else [max(0.0, x - corte) for x in v[len(PRE):]]) for k, v in al.items()}
    json.dump({"texto": txt, "alineacion": al}, open(out + ".json", "w"), ensure_ascii=False)
    recortar(out)   # quita el trozo de la frase siguiente que se cuela al final
    return out
g = json.load(open(sys.argv[1]))
solo = [a for a in sys.argv[2:] if not a.startswith("--")]
tareas = []
for c in g["capitulos"]:
    if solo and c["id"] not in solo: continue
    P = c["parrafos"]
    for i, t in enumerate(P):
        tareas.append((c["id"], i, t, " ".join(P[max(0, i-2):i]), P[i+1] if i+1 < len(P) else "", f"/home/user/Reel/voz/largo/{c['id']}_{i:02d}"))
with ThreadPoolExecutor(3) as ex:
    for o in ex.map(gen, tareas): print("ok", os.path.basename(o))
