import json, re, subprocess, sys, numpy as np
D, S = sys.argv[1], sys.argv[2]
SR = 44100
def rd(f):
    b = subprocess.run(['ffmpeg','-v','error','-i',f,'-ac','2','-ar',str(SR),'-f','f32le','-'],capture_output=True,check=True).stdout
    return np.frombuffer(b,np.float32).reshape(-1,2).copy()
EN = re.compile(r"^(it's|okay|come|grab|me|i'll|drop|a|pin|get|back|here)$", re.I)
for clip, n in [('policia','a'),('tienda','b'),('apolo','c')]:
    orig, nv = rd(f'{D}/{n}.mp4'), rd(f'{S}/st_{n}_no_vocals.flac')
    L = min(len(orig), len(nv)); orig, nv = orig[:L], nv[:L]
    mask = np.zeros(L, np.float32)
    for w in json.load(open(f'{D}/{n}.json'))['words']:
        t = w['text'].strip('.,¿?¡!')
        if w['type'] == 'word' and not EN.match(t) or w['type'] == 'audio_event' and re.search(r'ri|ríe|grit|llor|resopl|sorprend|chasquido', w['text']):
            mask[int(max(0, w['start']-0.2)*SR):int((w['end']+0.25)*SR)] = 1
    r = int(0.06*SR); k = np.sin(np.linspace(0, np.pi, 2*r))**2; k /= k.sum()
    mask = np.clip(np.convolve(mask, k, 'same'), 0, 1)[:, None]
    mix = orig*(1-mask) + nv*mask           # el audio original intacto salvo donde habla Albert
    cfg = json.load(open(f'{D}/cfg_{clip}_sinvoz.json'))
    trozos = []
    for m in cfg['momentos']:
        seg = mix[int(m['s0']*SR):int(m['s1']*SR)].copy()
        f = int(0.03*SR); seg[:f] *= np.linspace(0,1,f)[:,None]; seg[-f:] *= np.linspace(1,0,f)[:,None]
        trozos.append(seg)
    out = np.concatenate(trozos)
    print(clip, 'voz quitada en %.1f s de %.1f' % (float(mask.sum())/SR, L/SR), 'duración', round(len(out)/SR,2))
    subprocess.run(['ffmpeg','-v','error','-y','-f','f32le','-ar',str(SR),'-ac','2','-i','-','-af','loudnorm=I=-14:TP=-1.5:LRA=11',
                    '-ar','48000','-c:a','pcm_s16le',f'{D}/final_{clip}.wav'], input=out.astype(np.float32).tobytes(), check=True)
