import json, os, subprocess, sys
D=sys.argv[1]; grupo=sys.argv[2]; os.chdir(D); os.makedirs('cfg',exist_ok=True)
def ini(v): return json.load(open(f'ts/{v}.json'))['inicio']
def M(id_,vid,s0,s1,graves=(),zooms=(),stickers=()):
    c=int(s0//1800)
    m=dict(id=id_,frames=f"p_{id_}",s_frames=round(s0-0.3,2),wav=f"{vid}.wav",wav_inicio=ini(vid),
           palabras=f"completo/c{c}.json",stt=float(c*1800),s0=s0,s1=s1,graves=list(graves),stickers=list(stickers),zooms=list(zooms))
    fd=m['frames']
    if not os.path.isdir(fd):
        os.makedirs(fd)
        subprocess.run(['ffmpeg','-v','error','-ss',f'{m["s_frames"]-ini(vid):.3f}','-i',f'{vid}.mp4','-t',f'{s1-m["s_frames"]+0.6:.2f}','-q:v','3',fd+'/f_%05d.jpg'],check=True)
    if not os.path.exists(f'{vid}.wav'):
        subprocess.run(['ffmpeg','-v','error','-i',f'{vid}.mp4','-vn','-ac','1','-ar','48000',f'{vid}.wav'],check=True)
    return m
CAM=[45,221,261,384]
if grupo=='gta':
    clips={
     "borracho":(["POV: TE PERSIGUE LA POLI","POR BEBER CERVEZA EN LA CALLE"],[M("k_b1","borracho",10922.0,10941.0,[[10926.05,10927.82]],[10934.8]),M("k_b2","borracho",10977.8,10986.2,zooms=[10981.0])]),
     "fiesta":(["POV: TE CUELAS EN UNA FIESTA","EN HELICÓPTERO"],[M("k_f1","fiesta",13105.5,13121.0,zooms=[13109.2]),M("k_f2","cripto",13284.0,13294.5,[[13290.96,13293.51]],[13289.1])]),
     "tyson":(["\"LLAMA A SEGURIDAD…","ES MIKE TYSON\""],[M("k_t1","aeropuerto",12064.0,12090.0,[[12080.04,12081.73]],[12080.1])]),
     "camioneta":(["LE METO NITRO","A LA CAMIONETA"],[M("k_c1","camioneta",10467.0,10496.0,[[10480.29,10482.16]],[10480.3])]),
     "yonqui":(["\"A LO MEJOR","SE LO MERECÍA\""],[M("k_y1","yonqui",12180.0,12208.0,[[12194.1,12196.19]],[12189.4])]),
    }
else:
    clips={
     "hidra":(["EL MEJOR TIRO DE MI VIDA…","Y ME LO PARAN"],[M("k_h1","hidra",6880.5,6909.0,[[6892.8,6895.05]],[6886.0,6896.7])]),
     "pelicano":(["\"NO HAY CALMA, SOLO HAY","UN PELÍCANO CON RABIA\""],[M("k_p2","pelicano",9500.2,9529.0,[[9524.65,9527.34]],[9500.7])]),
     "baneo":(["ME BANEAN POR CULPA","DE MI AMIGO"],[M("k_n1","baneo",1716.0,1745.0,[[1740.66,1742.33]],[1724.3,1743.3])]),
     "electro":(["EL TIRO ELECTRO","PATRIARCAL DE LA MUERTE"],[M("k_e1","electro",5822.0,5845.0,[[5837.95,5840.9]],[5831.0])]),
     "futuro":(["\"DEJA DE VER EL FUTURO,","HIJO DE…\""],[M("k_u1","futuro",3041.5,3069.0,[[3066.45,3068.48]],[3046.0])]),
    }
for n,(tit,moms) in clips.items():
    json.dump({"titulos":tit,"formato":"juego","cam":CAM,"momentos":moms},open(f'cfg/cfg_{n}.json','w'),ensure_ascii=False,indent=1)
    tot=sum(m['s1']-m['s0']+sum(b-a for a,b in m['graves'])*(1/0.78-1) for m in moms)
    print(n,round(tot,1))
