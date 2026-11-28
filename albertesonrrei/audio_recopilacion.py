import json, subprocess, sys, os, numpy as np
os.chdir(sys.argv[1]); c=json.load(open('cfg_recop.json')); SR=48000
def rd(f,a,b):
    x=np.frombuffer(subprocess.run(['ffmpeg','-v','error','-ss',f'{a}','-t',f'{b-a}','-i',f,'-vn','-ac','2','-ar',str(SR),'-f','f32le','-'],capture_output=True,check=True).stdout,np.float32).reshape(-1,2).copy()
    n=int(round((b-a)*SR)); x=np.pad(x,((0,max(0,n-len(x))),(0,0)))[:n]
    f=int(0.04*SR); x[:f]*=np.linspace(0,1,f)[:,None]; x[-f:]*=np.linspace(1,0,f)[:,None]
    return x
out=np.concatenate([rd(m['wav'].replace('.wav','.mp4'),m['s0'],m['s1']) for m in c['momentos']])
subprocess.run(['ffmpeg','-v','error','-y','-f','f32le','-ar',str(SR),'-ac','2','-i','-','-af','loudnorm=I=-14:TP=-1.5:LRA=11','-ar','48000','juego.wav'],input=out.tobytes(),check=True)
