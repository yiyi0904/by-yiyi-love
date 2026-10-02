"""从源图生成程序图标（app.ico / icon.png），并输出对比预览。"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")
SOURCE = os.path.join(ASSETS, "source_icon.jpg")

# (名称, 裁剪框 or None) —— 裁剪框按源图像素坐标，均为正方形
CANDIDATES = {
    "full": None,
    "head": (95, 5, 535, 445),
    "face": (175, 110, 480, 415),
}


def build(crop: tuple[int, int, int, int] | None) -> Image.Image:
    im = Image.open(SOURCE).convert("RGB")
    if crop:
        im = im.crop(crop)
    side = min(im.size)
    left = (im.width - side) // 2
    top = (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side))
    return im


def make_sheet() -> str:
    cell = 256
    small = 32
    sheet = Image.new("RGB", (cell * 3 + 80, cell + 90), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (name, crop) in enumerate(CANDIDATES.items()):
        im = build(crop)
        big = im.resize((cell, cell), Image.LANCZOS)
        x = 20 + index * (cell + 20)
        sheet.paste(big, (x, 40))
        tiny = im.resize((small, small), Image.LANCZOS).resize((cell, cell), Image.NEAREST)
        sheet.paste(tiny, (x, 40 + cell + 10))
        draw.text((x, 16), f"{name}  -> 256px / 32px(放大)", fill="black")
    out = os.path.join(BASE, "icon_preview.png")
    sheet.save(out)
    return out


def write_assets(crop: tuple[int, int, int, int] | None, name: str) -> tuple[str, str]:
    im = build(crop)
    png_path = os.path.join(BASE, "icon.png")
    ico_path = os.path.join(BASE, "app.ico")
    im.resize((512, 512), Image.LANCZOS).save(png_path)
    base = im.resize((256, 256), Image.LANCZOS)
    sizes = [256, 128, 64, 48, 32, 16]
    frames = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    base.save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    return png_path, ico_path


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        print(make_sheet())
    else:
        key = sys.argv[1] if len(sys.argv) > 1 else "head"
        png, ico = write_assets(CANDIDATES[key], key)
        print("png:", png)
        print("ico:", ico, os.path.getsize(ico), "bytes")
