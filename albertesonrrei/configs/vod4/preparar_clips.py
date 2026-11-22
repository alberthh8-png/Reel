import json, os, re, subprocess
D=os.getcwd()+'/'
W=[]
for i in range(8):
    d=json.load(open(f'completo/c{i}.json'))
    W+=[(w['start']+i*1800,w['end']+i*1800,w['text']) for w in d['words'] if w['type']=='word']
W.sort()
L=lambda x: re.sub(r'[^\wáéíóúñ]','',x.lower())
def fr(t,p1,p2):
    i=next(k for k,w in enumerate(W) if w[0]>=t-0.6 and L(w[2])==p1)
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
C=lambda s,h,t: dict(tipo="chat",s=s,hasta=h,texto=t)
clips={
 "porsche":(["POV: EL CHAT TE DICE","QUE PERSIGAS UNOS COCHES"],[
    M("c_p0b","porsche",12617.5,12620.2,zooms=[12618.3]),
    M("c_p1b","porsche",12645.2,12660.4,[fr(12657,"ese","coche")],stickers=[C(12645.3,12650.5,"UN PORSHE GRATIS SI LOS SIGUES")],zooms=[12658.0]),
    M("c_p2b","porsche",12727.8,12736.4,stickers=[C(12731.5,12736.3,"Te vas a quedar sin combustible encima")],zooms=[12728.0]),
    M("c_p3b","porsche",12777.4,12778.5,zooms=[12777.6])]),
 "contenedor":(["POV: HUYES DE LA POLI Y UN RANDOM","TE ESCONDE EN SU CONTENEDOR"],[
    M("c_c1","contenedor",9310.3,9335.0,[fr(9310,"tú","eres")],zooms=[9325.5]),M("c_c2","contenedor",9351.4,9356.0,zooms=[9351.6])]),
 "perro":(["POV: ATROPELLAS AL PERRO","E INTENTAS LLEVARLO AL VETERINARIO"],[
    M("c_r1","perro",8407.6,8436.0,[fr(8431,"mira","perro")],zooms=[8412.8,8426.5])]),
 "helicoptero":(["\"YO SOLO QUERÍA","COGER UN HELICÓPTERO\""],[
    M("c_h1","helicoptero",9137.0,9164.4,[fr(9147,"abre","ya")],zooms=[9161.0])]),
 "tyson":(["\"¿TÚ QUIÉN ERES,","MIKE TYSON?\""],[
    M("c_t1","tyson",8841.5,8869.6,[fr(8851,"me","tyson")],zooms=[8866.6])]),
 "moto":(["\"AL DE LA MOTO NO QUERÍA","HACERLE NADA, TE LO JURO\""],[
    M("c_m1","moto",12474.6,12502.6,[fr(12478,"la","ahora")],zooms=[12486.3,12497.5])]),
 "desnudo":(["POV: PERSIGUES","A UN HOMBRE DESNUDO"],[
    M("c_d1","neandertal",7137.6,7146.2),M("c_d2","neandertal",7182.0,7190.0,[fr(7185,"tiene","mandíbula")],zooms=[7185.5]),
    M("c_d3","bici",7554.0,7566.4,zooms=[7563.9])]),
 "citas":(["POV: LE DAS BESITOS A LUCÍA","Y CADA VEZ TE QUIERE MENOS"],[
    M("c_l1","citas",11879.8,11909.0,zooms=[11903.3])]),
 "nuclear":(["\"LA NUCLEAR…","AH, QUE TENÍAS UN CUCHILLO\""],[
    M("c_n1","nuclear",9599.5,9623.6,zooms=[9619.0])]),
 "rl_defensa":(["\"GUAU, ALBERT,","QUÉ DEFENSA\""],[
    M("c_q1","rl1",1335.2,1358.6,zooms=[1346.8])]),
 "rl_parado":(["\"¿CÓMO QUE NO","LA HE PARADO?\""],[
    M("c_q2","rl2",4399.2,4428.6,[fr(4402,"mi","también")],zooms=[4425.0])]),
}
for n,(tit,moms) in clips.items():
    json.dump({"titulos":tit,"formato":"juego","momentos":moms},open(f'cfg/cfg_{n}.json','w'),ensure_ascii=False,indent=1)
    tot=sum(m['s1']-m['s0']+sum(b-a for a,b in m['graves'])*(1/0.78-1) for m in moms)
    print(n,round(tot,1),[m['graves'] for m in moms])
