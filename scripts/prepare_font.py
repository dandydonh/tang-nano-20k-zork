#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
root=Path(__file__).resolve().parents[1]
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',18)
rows=[]
for c in range(128):
    # Draw at native size: 12x20 cells, with two unused rows of font leading
    # removed. Pad each glyph to 32 rows for simple block-ROM addressing.
    im=Image.new('1',(12,20))
    if 32 <= c <127: ImageDraw.Draw(im).text((0,-2),chr(c),font=font,fill=1)
    for y in range(32):
        rows.append(sum(im.getpixel((x,y))<<(11-x) for x in range(12)) if y<20 else 0)
(root/'assets/font.hex').write_text(''.join(f'{v:03x}\n' for v in rows))
