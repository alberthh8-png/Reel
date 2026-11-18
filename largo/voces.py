"""Genera la voz de Dan párrafo a párrafo (con marcas de tiempo por carácter)."""
import json, base64, sys, os, requests
from concurrent.futures import ThreadPoolExecutor
VOZ = "9F4C8ztpNUmXkdDDbz3J"
PRON = {"MrBeast": "Mister Bist", "Sensor Tower": "Sénsor Táuer", "Cyberpunk 2077": "Cyberpunk dos mil setenta y siete",
        "Grassrivers": "Grass Rívers", "Port Gellhorn": "Port Guélhorn", "Bonnie y Clyde": "Boni y Claid",
        "Red Dead Redemption 2": "Red Ded Redémpshon dos", " X,": " equis,", "GTA Online": "GTA Online",
        "Kick": "Kik", "Warzone": "Guórsoun", "Deadpool y Lobezno": "Dédpul y Lobezno"}
def pron(t):
    for a, b in PRON.items(): t = t.replace(a, b)
    return t
S = requests.Session()
S.verify = "/root/.ccr/ca-bundle.crt"
def gen(args):
    cid, i, txt, prev, nxt, out = args
    if os.path.exists(out + ".mp3") and "--forzar" not in sys.argv: return out
    body = {"text": pron(txt), "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True, "speed": 0.96},
            "previous_text": pron(prev), "next_text": pron(nxt)}
    for _ in range(4):
        r = S.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ}/with-timestamps", json=body,
                   headers={"xi-api-key": "proxy-injected"}, timeout=180)
        if r.ok: break
        print("reintento", out, r.status_code, r.text[:200])
    r.raise_for_status(); d = r.json()
    open(out + ".mp3", "wb").write(base64.b64decode(d["audio_base64"]))
    json.dump({"texto": txt, "alineacion": d["alignment"]}, open(out + ".json", "w"), ensure_ascii=False)
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
