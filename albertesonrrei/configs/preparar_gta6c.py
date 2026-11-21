import json, os, re, subprocess
D=os.getcwd()+'/'
W=[]
for i in range(7):
    d=json.load(open(f'completo/c{i}.json')); off=d.get('inicio',i*1800)
    W+=[(w['start']+off,w['end']+off,w['text']) for w in d['words'] if w['type']=='word']
W.sort()
L=lambda x: re.sub(r'[^\wáéíóúñ]','',x.lower())
def fr(t,p1,p2):  # frase que empieza en la palabra p1 (después de t) y acaba en p2
    i=next(k for k,w in enumerate(W) if w[0]>=t-0.5 and L(w[2])==p1)
    j=next(k for k in range(i,len(W)) if L(W[k][2])==p2)
    return [round(W[i][0]-0.05,2),round(W[j][1]+0.12,2)]
def ini(v): return json.load(open(f'ts/{v}.json'))['inicio']
def M(id_,vid,s0,s1,graves=(),**k):
    c=int(s0//1800)
    m=dict(id=id_,frames=f"p_{id_}",s_frames=round(s0-0.3,2),wav=f"{vid}.wav",wav_inicio=ini(vid),
           palabras=f"completo/c{c}.json",stt=float(c*1800),s0=s0,s1=s1,graves=list(graves),
           stickers=k.get('stickers',[]),zooms=k.get('zooms',[]))
    fd=D+m['frames']
    if not os.path.isdir(fd):
        os.makedirs(fd)
        subprocess.run(['ffmpeg','-v','error','-ss',f'{m["s_frames"]-ini(vid):.3f}','-i',f'{vid}.mp4','-t',f'{s1-m["s_frames"]+0.6:.2f}','-q:v','3',fd+'/f_%05d.jpg'],check=True)
    if not os.path.exists(f'{vid}.wav'):
        subprocess.run(['ffmpeg','-v','error','-i',f'{vid}.mp4','-vn','-ac','1','-ar','48000',f'{vid}.wav'],check=True)
    return m
T=lambda s,h,l: dict(tipo="texto",s=s,hasta=h,lineas=l)
clips={
 "oso":(["¡PARAD AL OSO!","GTA 6"],[M("q_o1","n_oso",5579.5,5608.5,[fr(5602,"tú","gilipollas")],zooms=[5597.2],stickers=[T(5597.1,5600.0,["¡PARAD","AL OSO!"])])]),
 "caza":(["SACA EL TREN","DE ATERRIZAJE"],[M("q_c1","n_caza",4422.9,4448.6,[fr(4442,"fui","puerco")],zooms=[4434.2]),M("q_c2","n_caza",4453.4,4456.8,zooms=[4454.3])]),
 "lambo":(["\"NO VOY A DURAR","NI 2 MINUTOS\""],[M("q_l1","n_coche",3640.0,3656.1,zooms=[3649.5]),M("q_l2","n_coche",3662.3,3665.2),
          M("q_l3","n_coche",3693.9,3702.6,[fr(3698,"ah","coche")],stickers=[T(3700.4,3702.6,["HE DURADO LO QUE","HE PODIDO DURAR"])])]),
 "escobar":(["ME TIROTEAN COMO","A PABLO ESCOBAR"],[M("q_e1","n_tirotear",4596.7,4625.0,[fr(4618,"me","yugular")],zooms=[4608.5])]),
 "ley":(["ROBO UN COCHE DE POLICÍA","PARA COLARME"],[M("q_y1","n_ley",4722.5,4751.0,[fr(4746.5,"albert","mierda")],zooms=[4742.6],stickers=[T(4736.9,4740.0,["SOY LA LEY"])])]),
 "parking":(["ATRAPADO","EN UN PARKING"],[M("q_p1","n_parking",3744.9,3758.4,zooms=[3748.5]),
          M("q_p2","n_parking",3784.9,3800.6,[fr(3792.5,"tenía","menores")],zooms=[3796.5])]),
 "perro":(["EL PERRO ME MUERDE","EL CUELLO"],[M("q_r1","n_perro",6013.2,6034.5,zooms=[6030.0]),
          M("q_r2","n_perro",6046.1,6053.6,[fr(6046,"el","cuello")])]),
}
for n,(tit,moms) in clips.items():
    json.dump({"titulos":tit,"formato":"juego","momentos":moms},open(f'cfg/cfg30_{n}.json','w'),ensure_ascii=False,indent=1)
    tot=sum(m['s1']-m['s0']+sum(b-a for a,b in m['graves'])*(1/0.78-1) for m in moms)
    print(n,round(tot,1),[m['graves'] for m in moms])
