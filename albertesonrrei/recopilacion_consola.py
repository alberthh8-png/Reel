import json, os, subprocess, sys
D=sys.argv[1]; os.chdir(D)
# (id, video, s0, s1, extras)
T=[("r3b","v6",5.0,25.0,dict(alejar=1.25)),
   ("r1b","v1",1.0,16.0,dict(box=[320,0,720,500],alejar=1.25)),
   ("r2b","v2",12.8,19.8,dict(alejar=1.25)),
   ("r4","v3",0.0,18.0,dict(alejar=1.25)),
   ("r5","v4",51.0,70.0,dict(alejar=1.25)),
   ("r6","v5",16.0,28.0,dict(crop_x=[[16,770]],alejar=1.25))]
moms=[]
for i,v,a,b,ex in T:
    fd=f"f_{i}"
    if not os.path.isdir(fd):
        os.makedirs(fd)
        subprocess.run(['ffmpeg','-v','error','-ss',f'{max(0,a-0.3):.2f}','-i',f'{v}.mp4','-t',f'{b-a+0.9:.2f}','-vf','fps=60,scale=1280:720:flags=lanczos','-q:v','2',f'{fd}/f_%05d.jpg'],check=True)
    if not os.path.exists(f'{v}.wav'):
        subprocess.run(['ffmpeg','-v','error','-i',f'{v}.mp4','-vn','-ac','1','-ar','48000',f'{v}.wav'],check=True)
    m=dict(id=i,frames=fd,s_frames=max(0,a-0.3),wav=f'{v}.wav',wav_inicio=0.0,palabras='vacio.json',stt=0.0,
           s0=a,s1=b,graves=[],stickers=[],zooms=[],sin_cam=True,suave=True)
    m.update(ex); moms.append(m)
json.dump({"titulos":["ESTE JUEGO ME HACE FELIZ"," "],"formato":"juego","momentos":moms},open('cfg_recop.json','w'),ensure_ascii=False,indent=1)
print('total',sum(b-a for _,_,a,b,_ in T))
