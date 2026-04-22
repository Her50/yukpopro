"""
YukpoPro Visual Generator — Agent Marketing Professionnel
Génération locale de visuels marketing (PIL/Pillow) sans API externe.
Types : poster, flyer, invitation, banner, social_post, certificate, business_card, ticket
"""
from __future__ import annotations
import base64, io, math, os
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ─── Palettes thématiques ────────────────────────────────────────────────────
THEMES: dict[str, dict] = {
    "blue":      {"bg1":(5,18,55),"bg2":(0,60,130),"bg3":(0,100,200),"accent1":(0,190,255),"accent2":(255,200,0),"text":(255,255,255),"text2":(180,215,255),"text3":(130,170,230),"card":(15,45,100,210),"overlay":(0,10,40,180),"badge_bg":(255,200,0),"badge_text":(10,20,50),"divider":(0,190,255)},
    "green":     {"bg1":(5,30,15),"bg2":(10,80,35),"bg3":(20,140,65),"accent1":(50,230,120),"accent2":(255,220,30),"text":(255,255,255),"text2":(180,255,210),"text3":(130,210,160),"card":(10,55,25,210),"overlay":(0,20,10,180),"badge_bg":(255,220,30),"badge_text":(5,30,15),"divider":(50,230,120)},
    "purple":    {"bg1":(20,5,50),"bg2":(70,10,130),"bg3":(120,30,200),"accent1":(200,110,255),"accent2":(255,180,50),"text":(255,255,255),"text2":(220,190,255),"text3":(180,150,230),"card":(50,15,100,210),"overlay":(15,5,40,180),"badge_bg":(255,180,50),"badge_text":(20,5,50),"divider":(200,110,255)},
    "orange":    {"bg1":(40,12,0),"bg2":(150,50,0),"bg3":(220,90,0),"accent1":(255,160,20),"accent2":(255,255,100),"text":(255,255,255),"text2":(255,225,175),"text3":(230,185,130),"card":(80,30,0,210),"overlay":(30,10,0,180),"badge_bg":(255,255,100),"badge_text":(40,12,0),"divider":(255,160,20)},
    "dark":      {"bg1":(8,8,16),"bg2":(18,18,35),"bg3":(30,30,55),"accent1":(0,220,255),"accent2":(160,255,100),"text":(235,235,250),"text2":(165,180,220),"text3":(120,140,185),"card":(22,22,45,220),"overlay":(5,5,15,200),"badge_bg":(0,220,130),"badge_text":(8,8,16),"divider":(0,220,255)},
    "light":     {"bg1":(240,243,255),"bg2":(210,220,250),"bg3":(180,200,245),"accent1":(40,90,210),"accent2":(255,120,30),"text":(20,25,60),"text2":(60,85,160),"text3":(100,120,190),"card":(220,228,255,210),"overlay":(180,200,240,150),"badge_bg":(255,120,30),"badge_text":(255,255,255),"divider":(40,90,210)},
    "gold":      {"bg1":(12,8,2),"bg2":(55,38,5),"bg3":(100,70,10),"accent1":(255,215,0),"accent2":(255,255,180),"text":(255,245,200),"text2":(220,195,120),"text3":(180,155,90),"card":(40,28,5,220),"overlay":(12,8,2,190),"badge_bg":(255,215,0),"badge_text":(12,8,2),"divider":(255,215,0)},
    "elegant":   {"bg1":(10,10,12),"bg2":(22,20,18),"bg3":(38,34,28),"accent1":(195,165,100),"accent2":(235,210,160),"text":(240,235,222),"text2":(195,182,155),"text3":(155,145,125),"card":(28,25,20,220),"overlay":(10,8,6,200),"badge_bg":(195,165,100),"badge_text":(10,10,12),"divider":(195,165,100)},
    "red":       {"bg1":(40,5,5),"bg2":(120,10,10),"bg3":(190,20,20),"accent1":(255,80,60),"accent2":(255,220,50),"text":(255,255,255),"text2":(255,200,195),"text3":(230,165,160),"card":(80,12,12,210),"overlay":(30,5,5,185),"badge_bg":(255,220,50),"badge_text":(40,5,5),"divider":(255,80,60)},
    "corporate": {"bg1":(245,247,250),"bg2":(225,232,245),"bg3":(200,215,240),"accent1":(25,65,140),"accent2":(200,30,30),"text":(15,25,60),"text2":(50,75,140),"text3":(90,115,175),"card":(210,220,245,220),"overlay":(185,205,235,160),"badge_bg":(200,30,30),"badge_text":(255,255,255),"divider":(25,65,140)},
}

FORMATS: dict[str, tuple[int,int]] = {
    "square":        (1080,1080),
    "portrait":      (1080,1350),
    "landscape":     (1200,630),
    "story":         (1080,1920),
    "banner_wide":   (1500,500),
    "a4":            (2480,3508),
    "business_card": (1050,600),
    "ticket":        (1400,650),
}

_FONT_CACHE: dict[tuple, Any] = {}
FONT_FAMILIES = {
    "bold":    ["C:/Windows/Fonts/calibrib.ttf","C:/Windows/Fonts/arialbd.ttf","C:/Windows/Fonts/georgiab.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf","/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    "regular": ["C:/Windows/Fonts/calibri.ttf","C:/Windows/Fonts/arial.ttf","C:/Windows/Fonts/georgia.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
    "italic":  ["C:/Windows/Fonts/calibrii.ttf","C:/Windows/Fonts/ariali.ttf","C:/Windows/Fonts/georgiai.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"],
}

def _font(size: int, style: str = "regular"):
    key = (size, style)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    for p in FONT_FAMILIES.get(style, FONT_FAMILIES["regular"]):
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _FONT_CACHE[key] = f
                return f
            except Exception:
                pass
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f

# ─── Helpers ────────────────────────────────────────────────────────────────
def _lerp(a, b, t): return a + (b-a)*t
def _lerp_color(c1, c2, t): return tuple(max(0,min(255,int(_lerp(c1[i],c2[i],t)))) for i in range(len(c1)))
def _hex_rgb(h: str):
    h = h.lstrip("#"); h = h*2 if len(h)==3 else h
    return (int(h[0:2],16),int(h[2:4],16),int(h[4:6],16))
def _tsize(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font)
    return (bb[2]-bb[0], bb[3]-bb[1])
def _load_b64(s: str):
    if not s: return None
    try:
        d = s.strip()
        if "," in d: d = d.split(",",1)[1]
        return Image.open(io.BytesIO(base64.b64decode(d))).convert("RGBA")
    except Exception:
        return None

def _gradient(W, H, c1, c2, c3=None, direction="vertical"):
    # Génération rapide via une ligne/colonne de pixels redimensionnée (évite la boucle Python O(W×H))
    if direction in ("vertical", "horizontal"):
        steps = H if direction == "vertical" else W
        strip_data = bytearray(steps * 4)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            t = max(0.0, min(1.0, t))
            if c3 and t > 0.5:
                c = _lerp_color(c2, c3, (t - 0.5) * 2)
            else:
                c = _lerp_color(c1, c2, t * (2 if c3 else 1))
            strip_data[i*4:i*4+4] = [*c, 255]
        if direction == "vertical":
            strip = Image.frombytes("RGBA", (1, steps), bytes(strip_data))
            return strip.resize((W, H), Image.BILINEAR)
        else:
            strip = Image.frombytes("RGBA", (steps, 1), bytes(strip_data))
            return strip.resize((W, H), Image.BILINEAR)
    # Diagonal / radial : boucle pixel par pixel (formats compacts uniquement)
    img = Image.new("RGBA", (W, H), (*c1, 255))
    px  = img.load()
    for y in range(H):
        for x in range(W):
            if direction == "diagonal": t = x/W*0.4 + y/H*0.6
            else:                       t = min(1.0, math.sqrt(((x-W/2)/W)**2+((y-H/2)/H)**2)*1.6)
            t = max(0.0, min(1.0, t))
            c = _lerp_color(c2, c3, (t-0.5)*2) if (c3 and t>0.5) else _lerp_color(c1, c2, t*(2 if c3 else 1))
            px[x, y] = (*c, 255)
    return img

def _glow(img, cx, cy, r, color, intensity=0.6):
    layer = Image.new("RGBA", img.size, (0,0,0,0))
    d = ImageDraw.Draw(layer)
    for i in range(8,0,-1):
        a = int(intensity*255*(1-i/8)**2*0.5)
        rr = r + i*(r//4)
        d.ellipse([cx-rr,cy-rr,cx+rr,cy+rr], fill=(*color[:3],a))
    d.ellipse([cx-r,cy-r,cx+r,cy+r], fill=(*color[:3],int(intensity*200)))
    img.alpha_composite(layer)

def _circles(img, T, W, H, seed=0):
    layer = Image.new("RGBA",(W,H),(0,0,0,0))
    configs = [(0.85,0.12,0.25,"accent1",30),(0.10,0.88,0.30,"bg3",50),(0.75,0.75,0.18,"accent2",20),(0.05,0.15,0.15,"accent1",20),(0.55,0.05,0.10,"accent2",25)]
    for i,(cfx,cfy,rfrac,ckey,alpha) in enumerate(configs):
        cx = int((cfx+seed*0.03*(i%3-1))*W); cy=int(cfy*H); r=int(rfrac*min(W,H))
        _glow(layer, cx, cy, r, T.get(ckey,T["accent1"]), alpha/255)
    img.alpha_composite(layer)

def _geom(draw, T, W, H, vtype="poster"):
    a1, a2 = T["accent1"], T["accent2"]
    if vtype in ("invitation","certificate"):
        cs = int(min(W,H)*0.08); lw = max(2,int(min(W,H)*0.003))
        for (cx,cy),(ox,oy) in zip([(cs,cs),(W-cs,cs),(cs,H-cs),(W-cs,H-cs)],[(1,1),(-1,1),(1,-1),(-1,-1)]):
            draw.line([(cx,cy),(cx+ox*cs*0.6,cy)], fill=(*a1,180), width=lw)
            draw.line([(cx,cy),(cx,cy+oy*cs*0.6)], fill=(*a1,180), width=lw)
    elif vtype in ("poster","flyer","social_post"):
        lw = max(2,int(W*0.003))
        for i in range(3):
            off = i*int(W*0.04)
            draw.line([(W-off,0),(W,off)], fill=(*a1,60-i*15), width=lw)
        draw.line([(0,H),(int(W*0.05),H-int(W*0.05))], fill=(*a2,30), width=lw)
    elif vtype == "banner":
        lw = max(3,int(H*0.02))
        for i in range(4):
            x = int(W*(0.22+i*0.18))
            draw.line([(x,int(H*0.15)),(x,int(H*0.85))], fill=(*a1,20+i*5), width=lw)

def _wrapped(draw, text, font, x, y, max_w, fill, align="left", spacing=1.3, shadow=False, max_lines=0, max_y=0):
    words = text.split(); lines, cur = [], ""
    for w in words:
        test = (cur+" "+w).strip()
        if _tsize(draw,test,font)[0] <= max_w: cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    if not lines: lines=[text]
    if max_lines and len(lines)>max_lines:
        lines=lines[:max_lines]
        last=lines[-1]
        while last and _tsize(draw,last+"...",font)[0]>max_w: last=last[:-1]
        lines[-1]=last+"..."
    fh=_tsize(draw,"Ag",font)[1]; lh=int(fh*spacing)
    for line in lines:
        if max_y and y+fh>max_y: break
        lw2=_tsize(draw,line,font)[0]
        lx = x+(max_w-lw2)//2 if align=="center" else (x+max_w-lw2 if align=="right" else x)
        if shadow: draw.text((lx+2,y+2), line, font=font, fill=(0,0,0,120))
        draw.text((lx,y), line, font=font, fill=fill)
        y+=lh
    return y

def _badge(draw, text, font, x, y, bg, fg, radius=12, pad=16):
    tw,th = _tsize(draw,text,font); bw=tw+pad*2; bh=th+pad
    draw.rounded_rectangle([x,y,x+bw,y+bh], radius=radius, fill=bg)
    draw.text((x+pad,y+pad//2), text, font=font, fill=fg)
    return bw,bh

def _logo(img, b64, x, y, max_h, shadow=False):
    logo = _load_b64(b64)
    if not logo: return 0
    scale = max_h/logo.height; nw=int(logo.width*scale)
    logo = logo.resize((nw,max_h), Image.LANCZOS)
    if shadow:
        sh=Image.new("RGBA",img.size,(0,0,0,0))
        for dx,dy,a in [(4,4,60),(3,3,40),(2,2,25)]:
            sh.paste((0,0,0,a),[x+dx,y+dy,x+dx+nw,y+dy+max_h])
        img.alpha_composite(sh)
    img.paste(logo,(x,y),logo)
    return nw

def _apply_bg(img, b64, opacity=0.3):
    bg = _load_b64(b64)
    if not bg: return img
    W,H=img.size; bg=bg.convert("RGB").resize((W,H),Image.LANCZOS)
    base=img.copy(); bg_rgba=bg.convert("RGBA")
    overlay=Image.new("RGBA",(W,H),(0,0,0,int((1-opacity)*200)))
    base.alpha_composite(bg_rgba); base.alpha_composite(overlay)
    return img

def _center(draw, text, font, cx, y, fill, shadow=False):
    w,_ = _tsize(draw,text,font); x=cx-w//2
    if shadow: draw.text((x+3,y+3),text,font=font,fill=(0,0,0,120))
    draw.text((x,y),text,font=font,fill=fill)
    return y+_tsize(draw,text,font)[1]

# ─── Renderers ───────────────────────────────────────────────────────────────

def _render_poster(data, T, W, H):
    img = _gradient(W,H,T["bg1"],T["bg2"],T["bg3"],"diagonal")
    _circles(img,T,W,H)
    if bg:=data.get("bg_image_base64"): img=_apply_bg(img,bg,float(data.get("bg_opacity",0.28)))
    draw = ImageDraw.Draw(img,"RGBA")
    _geom(draw,T,W,H,"poster")
    pad=int(W*0.065); cw=W-2*pad; cy=0

    # Top bar
    draw.rectangle([0,0,W,int(H*0.007)], fill=(*T["accent1"],255))
    # Logo
    lh=int(H*0.075); ly=int(H*0.007)+int(H*0.022); lw2=0
    if lb:=data.get("logo_base64"): lw2=_logo(img,lb,pad,ly,lh,True); draw=ImageDraw.Draw(img,"RGBA")
    if bn:=data.get("brand_name"):
        bf=_font(int(H*0.027),"bold"); bx=pad+lw2+12 if lw2 else W//2
        _bh=_tsize(draw,bn,bf)[1]; by=ly+(lh-_bh)//2
        if lw2: draw.text((bx,by),bn,font=bf,fill=(*T["accent1"],255))
        else: _center(draw,bn,bf,W//2,by,(*T["accent1"],255))
    # Badge
    if bdg:=data.get("badge"):
        bdf=_font(int(H*0.022),"bold"); bc=T["badge_bg"]
        if bch:=data.get("badge_color"):
            try: bc=_hex_rgb(bch)
            except: pass
        bw2,_=_badge(draw,"",bdf,0,0,bc,T["badge_text"])
        bw2,bh2=_badge(draw,bdg,bdf,0,0,bc,T["badge_text"])
        _badge(draw,bdg,bdf,W-pad-bw2,ly,bc,T["badge_text"])
    cy=ly+lh+int(H*0.04)
    # Title
    tf=_font(max(int(W*0.072),52),"bold")
    draw.rectangle([pad,cy,pad+int(cw*0.12),cy+int(H*0.006)],fill=(*T["accent2"],255)); cy+=int(H*0.018)
    cy=_wrapped(draw,data.get("title",""),tf,pad,cy,cw,(*T["text"],255),"left",1.1,True); cy+=int(H*0.012)
    # Subtitle
    if sub:=data.get("subtitle"):
        sf=_font(int(H*0.032),"italic"); cy=_wrapped(draw,sub,sf,pad,cy,cw,(*T["text2"],230),"left",1.2); cy+=int(H*0.016)
    # Divider
    draw.rectangle([pad,cy,pad+int(cw*0.5),cy+int(H*0.003)],fill=(*T["accent1"],200)); cy+=int(H*0.024)
    # Description
    if desc:=data.get("description"):
        df=_font(int(H*0.027),"regular"); cy=_wrapped(draw,desc,df,pad,cy,cw,(*T["text2"],200),"left",1.4); cy+=int(H*0.02)
    # Info card
    infos=[(l,v) for l,k in [("DATE","date"),("HEURE","time"),("LIEU","location"),("TARIF","price")] if (v:=data.get(k))]
    if infos:
        cp=int(W*0.045); lbf=_font(int(H*0.018),"bold"); vf=_font(int(H*0.028),"regular")
        lh2=int(H*0.065); ch2=len(infos)*lh2+cp*2
        draw.rounded_rectangle([pad,cy,pad+cw,cy+ch2],radius=18,fill=T["card"])
        draw.rounded_rectangle([pad,cy,pad+6,cy+ch2],radius=3,fill=(*T["accent1"],255))
        for i,(lbl,val) in enumerate(infos):
            iy=cy+cp+i*lh2; draw.text((pad+cp,iy),lbl,font=lbf,fill=(*T["accent1"],255))
            lw3,lh3=_tsize(draw,lbl,lbf); draw.text((pad+cp+lw3+12,iy+(lh3-_tsize(draw,val,vf)[1])//2),val,font=vf,fill=(*T["text"],240))
        cy+=ch2+int(H*0.018)
    # Bullets
    for b in data.get("bullets",[]):
        bf2=_font(int(H*0.026),"regular"); bh3=_tsize(draw,b,bf2)[1]; dr=int(H*0.008)
        draw.ellipse([pad+4,cy+bh3//2-dr,pad+4+dr*2,cy+bh3//2+dr],fill=(*T["accent1"],220))
        draw.text((pad+dr*2+14,cy),b,font=bf2,fill=(*T["text2"],220)); cy+=int(bh3*1.5)
    # Footer
    fy=H-int(H*0.085); draw.rectangle([0,fy,W,fy+int(H*0.003)],fill=(*T["accent1"],100))
    if ct:=data.get("contact"): draw.text((pad,fy+int(H*0.016)),ct,font=_font(int(H*0.026),"bold"),fill=(*T["accent1"],255))
    if ht:=data.get("hashtags",[]):
        hf=_font(int(H*0.022),"regular"); htxt="  ".join(str(h) for h in ht[:4])
        hw,_=_tsize(draw,htxt,hf); draw.text((W-pad-hw,fy+int(H*0.018)),htxt,font=hf,fill=(*T["text3"],200))
    if org:=data.get("organizer"): draw.text((pad,fy+int(H*0.048)),"Organisé par : "+org,font=_font(int(H*0.020),"italic"),fill=(*T["text3"],180))
    draw.rectangle([0,H-int(H*0.005),W,H],fill=(*T["accent1"],255))
    return img.convert("RGB")


def _render_banner(data, T, W, H):
    img = _gradient(W,H,T["bg1"],T["bg2"],direction="horizontal")
    draw = ImageDraw.Draw(img,"RGBA")
    _geom(draw,T,W,H,"banner")
    bw=max(8,int(W*0.006)); draw.rectangle([0,0,bw,H],fill=(*T["accent1"],255))
    _glow(img, W+int(W*0.33)//3, -int(H*1.2)//4, int(H*1.2), T["bg3"], 0.5)
    draw=ImageDraw.Draw(img,"RGBA")
    pad=int(H*0.15); lx=bw+pad; ls=0
    if lb:=data.get("logo_base64"):
        lh=int(H*0.60); ls=_logo(img,lb,lx,(H-lh)//2,lh,True); draw=ImageDraw.Draw(img,"RGBA"); ls+=int(H*0.12)
    tx=lx+ls; tw2=int(W*0.60)-ls; ty=int(H*0.18)
    tf=_font(int(H*0.36),"bold"); ty=_wrapped(draw,data.get("title",""),tf,tx,ty,tw2,(*T["text"],255),"left",1.05,True)
    if sub:=data.get("subtitle"): _wrapped(draw,sub,_font(int(H*0.18),"regular"),tx,ty+int(H*0.04),tw2,(*T["text2"],210),"left")
    cta=data.get("badge") or data.get("price") or data.get("date") or ""
    if cta:
        cw2=int(W*0.22); cx2=W-cw2-pad
        draw.rounded_rectangle([cx2,int(H*0.12),cx2+cw2,H-int(H*0.12)],radius=16,fill=(*T["badge_bg"],255))
        cf=_font(int(H*0.22),"bold"); cw3,ch3=_tsize(draw,cta,cf)
        draw.text((cx2+(cw2-cw3)//2,(H-ch3)//2),cta,font=cf,fill=(*T["badge_text"],255))
    if ct:=data.get("contact"): draw.text((tx,H-pad-_tsize(draw,ct,_font(int(H*0.14),"bold"))[1]),ct,font=_font(int(H*0.14),"bold"),fill=(*T["accent1"],255))
    draw.rectangle([0,H-max(4,int(H*0.025)),W,H],fill=(*T["accent1"],255))
    return img.convert("RGB")


def _render_social_post(data, T, W, H):
    img = _gradient(W,H,T["bg1"],T["bg2"],T["bg3"],"diagonal")
    _circles(img,T,W,H,1)
    if bg:=data.get("bg_image_base64"): img=_apply_bg(img,bg,float(data.get("bg_opacity",0.32)))
    draw=ImageDraw.Draw(img,"RGBA"); _geom(draw,T,W,H,"social_post")
    pad=int(W*0.07); cw=W-2*pad; cy=int(H*0.06)
    if lb:=data.get("logo_base64"): _logo(img,lb,pad,cy,int(H*0.07),True); draw=ImageDraw.Draw(img,"RGBA")
    if bdg:=data.get("badge"):
        bc=T["badge_bg"]; bf2=_font(int(H*0.026),"bold")
        bw2,_=_badge(draw,bdg,bf2,0,0,bc,T["badge_text"]); _badge(draw,bdg,bf2,W-pad-bw2,cy,bc,T["badge_text"])
    cy=int(H*0.22); tf=_font(int(H*0.068),"bold")
    ty=_wrapped(draw,data.get("title",""),tf,pad,cy,cw,(*T["text"],255),"center",1.1,True)
    sw2=int(cw*0.25); sx=(W-sw2)//2; draw.rectangle([sx,ty+10,sx+sw2,ty+14],fill=(*T["accent1"],255)); ty+=int(H*0.032)
    if sub:=data.get("subtitle"): ty=_wrapped(draw,sub,_font(int(H*0.033),"italic"),pad,ty,cw,(*T["text2"],225),"center"); ty+=int(H*0.012)
    if desc:=data.get("description"):
        ch2=int(H*0.18); draw.rounded_rectangle([pad,ty,W-pad,ty+ch2],radius=16,fill=T["card"])
        draw.rounded_rectangle([pad,ty,pad+6,ty+ch2],radius=3,fill=(*T["accent1"],255))
        _wrapped(draw,desc,_font(int(H*0.026),"regular"),pad+20,ty+int(H*0.02),cw-24,(*T["text"],215),"left",1.4)
        ty+=ch2+int(H*0.018)
    for b in data.get("bullets",[]):
        bf3=_font(int(H*0.028),"regular"); bh4=_tsize(draw,b,bf3)[1]; dr=int(H*0.007)
        draw.ellipse([pad+4,ty+bh4//2-dr,pad+4+dr*2,ty+bh4//2+dr],fill=(*T["accent1"],220))
        draw.text((pad+dr*2+14,ty),b,font=bf3,fill=(*T["text2"],215)); ty+=int(bh4*1.55)
    fy=H-int(H*0.10); draw.rectangle([pad,fy,W-pad,fy+2],fill=(*T["accent1"],100)); fy+=int(H*0.012)
    if ct:=data.get("contact"): draw.text((pad,fy),ct,font=_font(int(H*0.026),"bold"),fill=(*T["accent1"],255))
    if ht:=data.get("hashtags",[]):
        hf=_font(int(H*0.022),"regular"); htxt="  ".join(str(h) for h in ht[:4])
        hw,_=_tsize(draw,htxt,hf); draw.text((W-pad-hw,fy),htxt,font=hf,fill=(*T["text3"],200))
    if org:=data.get("organizer"): draw.text((pad,fy+int(H*0.038)),org,font=_font(int(H*0.020),"italic"),fill=(*T["text3"],170))
    return img.convert("RGB")


def _render_invitation(data, T, W, H):
    img=_gradient(W,H,T["bg1"],T["bg2"],T["bg3"],"radial"); _circles(img,T,W,H,2)
    draw=ImageDraw.Draw(img,"RGBA"); _geom(draw,T,W,H,"invitation")
    pad=int(W*0.08); cw=W-2*pad; cy=int(H*0.04)
    bw=max(3,int(min(W,H)*0.003))
    draw.rectangle([bw*2,bw*2,W-bw*2,H-bw*2],outline=(*T["accent1"],180),width=bw)
    draw.rectangle([bw*5,bw*5,W-bw*5,H-bw*5],outline=(*T["accent1"],70),width=max(1,bw//2))
    if lb:=data.get("logo_base64"):
        lh=int(H*0.10); logo2=_load_b64(lb)
        if logo2:
            scale=lh/logo2.height; nw=int(logo2.width*scale)
            logo2=logo2.resize((nw,lh),Image.LANCZOS); img.paste(logo2,((W-nw)//2,cy+int(H*0.02)),logo2)
            draw=ImageDraw.Draw(img,"RGBA"); cy+=lh+int(H*0.025)
    hf2=_font(int(H*0.028),"bold"); htxt="-  INVITATION  -"
    _center(draw,htxt,hf2,W//2,cy,(*T["accent1"],255)); cy+=_tsize(draw,htxt,hf2)[1]+int(H*0.012)
    sr=int(W*0.012); draw.ellipse([W//2-sr,cy-sr,W//2+sr,cy+sr],fill=(*T["accent2"],255))
    draw.rectangle([pad+40,cy+sr//2-1,W//2-sr-10,cy+sr//2+1],fill=(*T["accent1"],180))
    draw.rectangle([W//2+sr+10,cy+sr//2-1,W-pad-40,cy+sr//2+1],fill=(*T["accent1"],180))
    cy+=sr*2+int(H*0.018)
    ty=_wrapped(draw,data.get("title",""),_font(max(int(H*0.062),42),"bold"),pad,cy,cw,(*T["text"],255),"center",1.1,True)
    cy=ty+int(H*0.010)
    if sub:=data.get("subtitle"): cy=_wrapped(draw,sub,_font(int(H*0.030),"italic"),pad,cy,cw,(*T["text2"],230),"center",1.2); cy+=int(H*0.010)
    draw.rectangle([pad+60,cy+4,W-pad-60,cy+6],fill=(*T["accent1"],120)); cy+=int(H*0.026)
    for lbl,k in [("DATE","date"),("HEURE","time"),("LIEU","location"),("TARIF","price")]:
        if val:=data.get(k):
            lf=_font(int(H*0.020),"bold"); vf=_font(int(H*0.030),"regular")
            lw3,lh3=_tsize(draw,lbl,lf); draw.text(((W-lw3)//2,cy),lbl,font=lf,fill=(*T["accent1"],255)); cy+=lh3+3
            vw,vh=_tsize(draw,val,vf); draw.text(((W-vw)//2,cy),val,font=vf,fill=(*T["text"],240)); cy+=vh+int(H*0.018)
    if desc:=data.get("description"):
        draw.rectangle([pad+60,cy,W-pad-60,cy+2],fill=(*T["accent1"],60)); cy+=int(H*0.014)
        cy=_wrapped(draw,desc,_font(int(H*0.024),"italic"),pad+20,cy,cw-40,(*T["text2"],200),"center",1.4); cy+=int(H*0.010)
    fy=H-int(H*0.10); draw.rectangle([pad+40,fy,W-pad-40,fy+2],fill=(*T["accent1"],80)); fy+=int(H*0.016)
    if org:=data.get("organizer"):
        ow,_=_tsize(draw,"Organisé par : "+org,_font(int(H*0.022),"italic"))
        draw.text(((W-ow)//2,fy),"Organisé par : "+org,font=_font(int(H*0.022),"italic"),fill=(*T["text3"],200)); fy+=int(H*0.032)
    if ct:=data.get("contact"):
        cw2,_=_tsize(draw,ct,_font(int(H*0.024),"bold"))
        draw.text(((W-cw2)//2,fy),ct,font=_font(int(H*0.024),"bold"),fill=(*T["accent1"],255))
    for cx2,cy2 in [(pad,pad),(W-pad,pad),(pad,H-pad),(W-pad,H-pad)]:
        r=int(min(W,H)*0.012); pts=[(cx2+r*math.cos(math.pi/4+i*math.pi/2),cy2+r*math.sin(math.pi/4+i*math.pi/2)) for i in range(4)]
        draw.polygon(pts,fill=(*T["accent2"],200))
    return img.convert("RGB")


def _render_certificate(data, T, W, H):
    img=_gradient(W,H,T["bg1"],T["bg2"],T["bg3"]); draw=ImageDraw.Draw(img,"RGBA")
    _geom(draw,T,W,H,"certificate")
    m1=int(min(W,H)*0.025); m2=m1+int(min(W,H)*0.015); lw=max(3,int(min(W,H)*0.004))
    draw.rectangle([m1,m1,W-m1,H-m1],outline=(*T["accent1"],220),width=lw)
    draw.rectangle([m2,m2,W-m2,H-m2],outline=(*T["accent1"],80),width=max(1,lw//2))
    orn=int(min(W,H)*0.06)
    for cx2,cy2 in [(m1,m1),(W-m1,m1),(m1,H-m1),(W-m1,H-m1)]:
        pts8=[(cx2+orn//2*math.cos(math.pi/8+i*2*math.pi/8),cy2+orn//2*math.sin(math.pi/8+i*2*math.pi/8)) for i in range(8)]
        draw.polygon(pts8,fill=(*T["accent2"],180))
        pts4=[(cx2+orn//4*math.cos(math.pi/4+i*math.pi/2),cy2+orn//4*math.sin(math.pi/4+i*math.pi/2)) for i in range(4)]
        draw.polygon(pts4,fill=(*T["accent1"],220))
    pad=int(W*0.10); cw=W-2*pad; cy=m2+int(H*0.045)
    if lb:=data.get("logo_base64"):
        logo3=_load_b64(lb)
        if logo3:
            lh=int(H*0.09); scale=lh/logo3.height; nw=int(logo3.width*scale)
            logo3=logo3.resize((nw,lh),Image.LANCZOS); img.paste(logo3,((W-nw)//2,cy),logo3)
            draw=ImageDraw.Draw(img,"RGBA"); cy+=lh+int(H*0.02)
    ht2=data.get("badge","CERTIFICAT D'EXCELLENCE")
    _center(draw,ht2,_font(int(H*0.030),"bold"),W//2,cy,(*T["accent1"],255)); cy+=_tsize(draw,ht2,_font(int(H*0.030),"bold"))[1]+int(H*0.015)
    draw.rectangle([pad+80,cy+5,W-pad-80,cy+7],fill=(*T["accent1"],80)); cy+=int(H*0.028)
    ty=_wrapped(draw,data.get("title",""),_font(int(H*0.055),"bold"),pad,cy,cw,(*T["text"],255),"center",1.1,True); cy=ty+int(H*0.012)
    if sub:=data.get("subtitle"): cy=_wrapped(draw,sub,_font(int(H*0.030),"italic"),pad,cy,cw,(*T["text2"],225),"center"); cy+=int(H*0.010)
    draw.rectangle([pad+80,cy+5,W-pad-80,cy+7],fill=(*T["accent1"],80)); cy+=int(H*0.028)
    if desc:=data.get("description"): cy=_wrapped(draw,desc,_font(int(H*0.027),"regular"),pad+20,cy,cw-40,(*T["text"],210),"center",1.45); cy+=int(H*0.018)
    sy=H-m2-int(H*0.11)
    if d:=data.get("date"):
        dw,_=_tsize(draw,d,_font(int(H*0.024),"regular")); draw.text(((W-dw)//2,sy),d,font=_font(int(H*0.024),"regular"),fill=(*T["text3"],200)); sy+=int(H*0.038)
    if org:=data.get("organizer"):
        sl=int(cw*0.28); slx=pad+int(cw*0.08)
        draw.rectangle([slx,sy,slx+sl,sy+2],fill=(*T["accent1"],150))
        ow,_=_tsize(draw,org,_font(int(H*0.020),"bold")); draw.text((slx+(sl-ow)//2,sy+6),org,font=_font(int(H*0.020),"bold"),fill=(*T["text3"],200))
    return img.convert("RGB")


def _render_business_card(data, T, W, H):
    img=_gradient(W,H,T["bg1"],T["bg2"],direction="horizontal"); draw=ImageDraw.Draw(img,"RGBA")
    _glow(img,W-int(W*0.12),-int(H*0.2),int(H*0.9),T["bg3"],0.6); draw=ImageDraw.Draw(img,"RGBA")
    bar=max(8,int(W*0.008)); draw.rectangle([0,0,bar,H],fill=(*T["accent1"],255)); draw.rectangle([0,H-bar,W,H],fill=(*T["accent1"],140))
    pad=int(H*0.14); lx=bar+pad; ls=0
    if lb:=data.get("logo_base64"):
        lh=int(H*0.55); ls=_logo(img,lb,lx,(H-lh)//2,lh,True); draw=ImageDraw.Draw(img,"RGBA"); ls+=int(H*0.12)
    tx=lx+ls; ty=pad
    name=data.get("title") or data.get("organizer") or data.get("brand_name") or ""
    if name:
        nf=_font(int(H*0.22),"bold"); draw.text((tx,ty),name,font=nf,fill=(*T["text"],255)); ty+=_tsize(draw,name,nf)[1]+int(H*0.06)
    if sub:=data.get("subtitle") or data.get("brand_name"):
        sf=_font(int(H*0.14),"regular"); draw.text((tx,ty),sub,font=sf,fill=(*T["accent1"],255)); ty+=_tsize(draw,sub,sf)[1]+int(H*0.05)
    draw.rectangle([tx,ty,tx+int((W-tx-pad)*0.5),ty+2],fill=(*T["accent1"],200)); ty+=int(H*0.08)
    for item in [data.get("contact"),data.get("location"),data.get("date")]:
        if item:
            ifont=_font(int(H*0.12),"regular"); draw.text((tx,ty),item,font=ifont,fill=(*T["text2"],220)); ty+=_tsize(draw,item,ifont)[1]+int(H*0.05)
    return img.convert("RGB")


RENDERERS = {
    "poster": _render_poster, "flyer": _render_poster,
    "banner": _render_banner, "banner_wide": _render_banner,
    "social_post": _render_social_post, "social": _render_social_post,
    "invitation": _render_invitation,
    "certificate": _render_certificate, "attestation": _render_certificate,
    "business_card": _render_business_card, "carte_visite": _render_business_card,
}

# ─── Point d'entrée public ───────────────────────────────────────────────────
def generate_visual(data: dict[str, Any]) -> bytes:
    """Génère un visuel marketing et retourne les bytes PNG/JPEG."""
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow non installé. Lancez : pip install Pillow")
    vtype   = data.get("visual_type", "poster").lower()
    fmt_nm  = data.get("format", "portrait").lower()
    theme   = data.get("theme", "purple").lower()
    out_fmt = data.get("output_format", "png").lower()
    quality = int(data.get("quality", 92))
    W, H    = FORMATS.get(fmt_nm, FORMATS["portrait"])
    T       = THEMES.get(theme, THEMES["purple"]).copy()
    if bc := data.get("brand_color"):
        try: T["accent1"] = _hex_rgb(bc)
        except: pass
    renderer = RENDERERS.get(vtype, _render_poster)
    img = renderer(data, T, W, H)
    try:
        img = img.filter(ImageFilter.SHARPEN)
    except Exception:
        pass
    buf = io.BytesIO()
    if out_fmt in ("jpg","jpeg"):
        img.convert("RGB").save(buf,"JPEG",quality=quality,optimize=True,progressive=True)
    else:
        img.save(buf,"PNG",optimize=True)
    return buf.getvalue()


def formats_disponibles() -> list[dict]:
    return [{"id":k,"label":k.replace("_"," ").title(),"dimensions":f"{v[0]}×{v[1]}"} for k,v in FORMATS.items()]

def themes_disponibles() -> list[str]:
    return list(THEMES.keys())

def types_disponibles() -> list[str]:
    return list(RENDERERS.keys())
