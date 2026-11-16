#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
root=Path(__file__).resolve().parents[1]
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',13)
rows=[]
for c in range(128):
    im=Image.new('1',(8,16))
    if 32 <= c <127: ImageDraw.Draw(im).text((0,0),chr(c),font=font,fill=1)
    for y in range(16): rows.append(sum(im.getpixel((x,y))<<(7-x) for x in range(8)))
(root/'assets/font.hex').write_text(''.join(f'{v:02x}\n' for v in rows))
