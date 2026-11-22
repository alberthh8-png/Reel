import sys; sys.path.insert(0,'/home/user/Reel')
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
from reel import ajustar_fuente, texto_con_estilo
V='/tmp/claude-0/-home-user-Reel/3efe04a8-bc52-519f-9bff-2b639dd9ba8e/scratchpad/vod4/'
W,H=1280,720
rng=np.random.default_rng(11)
img=np.asarray(Image.open(V+'base_mini.png').convert('RGB')).astype(np.float32)/255
yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
def fbm(esc,oct=6):
    n=np.zeros((H,W),np.float32); a=1; t=0
    for o in range(oct):
        s=max(1,esc/(2**o)); gh,gw=int(H/s)+3,int(W/s)+3
        g=rng.random((gh,gw)).astype(np.float32)
        up=np.asarray(Image.fromarray((g*255).astype(np.uint8)).resize((int(gw*s),int(gh*s)),Image.BICUBIC),np.float32)[:H,:W]/255
        n+=a*up; t+=a; a*=0.55
    return n/t
def mapa(t):  # temperatura -> color de fuego
    t=np.clip(t,0,1)[...,None]
    c0=np.array([0.25,0.03,0.0]); c1=np.array([0.95,0.25,0.02]); c2=np.array([1.0,0.62,0.1]); c3=np.array([1.0,0.95,0.7])
    return np.where(t<0.33,c0+(c1-c0)*(t/0.33),np.where(t<0.66,c1+(c2-c1)*((t-0.33)/0.33),c2+(c3-c2)*((t-0.66)/0.34)))
def explosion(cx,cy,r):
    global img
    n=fbm(r*0.45)
    d=np.sqrt(((xx-cx)/r)**2+((yy-cy)/(r*0.8))**2)
    forma=1.15-d+0.55*(n-0.5)*2
    # humo negro por fuera (sube)
    ds=np.sqrt(((xx-cx)/(r*1.5))**2+((yy-(cy-r*0.55))/(r*1.1))**2)
    humo=np.clip((1.1-ds+0.6*(fbm(r*0.7)-0.5)*2)*1.6,0,1)*0.85
    img=img*(1-humo[...,None])+np.array([0.07,0.06,0.06])*humo[...,None]
    fuego=np.clip(forma*2.2,0,1)
    temp=np.clip(forma*1.3+0.25*(n-0.5),0,1)
    img=img*(1-fuego[...,None])+mapa(temp)*fuego[...,None]
    gl=np.exp(-((xx-cx)**2+(yy-cy)**2)/(2*(r*1.8)**2))*0.28
    img=img+np.stack([gl,gl*0.42,gl*0.08],-1)
img=img*np.array([0.9,0.82,0.78])
explosion(1110,210,150)   # detrás, a la derecha
explosion(250,260,115)    # izquierda, junto al hotel
explosion(640,330,70)     # al fondo de la calle
for cx,cy,c in [(462,390,(1,0.08,0.08)),(492,391,(0.1,0.3,1))]:  # luces del coche del fondo
    g=np.exp(-((xx-cx)**2+(yy-cy)**2)/(2*14**2)); img=img+np.array(c)*g[...,None]*1.3
img=np.clip(img,0,1)
im=Image.fromarray((img*255).astype(np.uint8))
d=ImageDraw.Draw(im)
for _ in range(90):  # chispas cortas
    cx,cy=[(1110,210),(250,260),(640,330)][rng.integers(3)]
    ang=rng.random()*2*np.pi; r0=60+rng.random()*120; L=6+rng.random()*22
    x0,y0=cx+np.cos(ang)*r0,cy+np.sin(ang)*r0*0.8
    d.line((x0,y0,x0+np.cos(ang)*L,y0+np.sin(ang)*L),fill=(255,200,90),width=2)
im=ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(1.25)).enhance(1.12).filter(ImageFilter.UnsharpMask(2,60,2))
v=np.clip(1-(((xx-W/2)/(W*0.8))**2+((yy-H/2)/(H*0.85))**2)*0.55,0.45,1)
im=Image.fromarray((np.asarray(im,np.float32)*v[...,None]).astype(np.uint8)).convert('RGBA')
cara=Image.open(V+'cara_12501.png').convert('RGB').resize((400,224),Image.LANCZOS)
marco=Image.new('RGBA',(412,236),(255,61,139,255)); marco.paste(cara,(6,6))
im.alpha_composite(marco.rotate(-4,expand=True,resample=Image.BICUBIC),(24,462))
AM,BL=(255,210,63,255),(255,255,255,255)
for txt,y,c,tam in [("LLEVANDO GTA 6",22,BL,110),("AL LÍMITE",142,AM,150)]:
    t=texto_con_estilo(txt,ajustar_fuente(txt,1180,tam,tam_min=60,borde=12),c,borde=12,color_borde=(0,0,0))
    im.alpha_composite(t,((W-t.width)//2,y))
im.convert('RGB').save('/home/user/Reel/salida/albertesonrrei/gta6_directo3_largo/miniatura.jpg',quality=92)
