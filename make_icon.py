#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 x-direct-cn 桌面图标（多尺寸 ICO）。

设计：深蓝圆角玻璃底 + 电光蓝雷达弧 + 白色 X + 右上实时绿点。
仅依赖 Pillow。运行后产出 panel.ico（16/24/32/48/64/128/256）与 panel-icon.png。
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path

BASE = Path(__file__).resolve().parent
S = 512  # 超采样，缩到小尺寸更锐利


def font(sz):
    for n in ("C:/Windows/Fonts/seguisb.ttf",
              "C:/Windows/Fonts/arialbd.ttf",
              "C:/Windows/Fonts/msyhbd.ttc"):
        try:
            return ImageFont.truetype(n, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def center(d, box, txt, f, fill, off=(0, 0)):
    bb = d.textbbox((0, 0), txt, font=f)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    x = box[0] + (box[2] - box[0] - w) / 2 - bb[0] + off[0]
    y = box[1] + (box[3] - box[1] - h) / 2 - bb[1] + off[1]
    d.text((x, y), txt, font=f, fill=fill)


def build():
    # 深蓝斜向渐变底
    im = Image.new("RGBA", (S, S))
    px = im.load()
    c1, c2 = (18, 31, 62), (6, 12, 30)
    for y in range(S):
        for x in range(S):
            t = (x / S) * 0.3 + (y / S) * 0.7
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)) + (255,)
    d = ImageDraw.Draw(im)

    # 圆角深色玻璃底板（不要大面积高光）
    d.rounded_rectangle((18, 18, 494, 494), radius=122, fill=(17, 28, 52, 255))
    d.rounded_rectangle((18, 18, 494, 494), radius=122,
                        outline=(58, 122, 220, 165), width=5)
    # 顶部极淡的一线高光
    d.arc((36, 36, 476, 476), start=196, end=344, fill=(255, 255, 255, 26), width=4)

    # 雷达环：只保留上下两道细弧，颜色统一电光蓝
    d.arc((78, 78, 434, 434), start=214, end=326, fill=(74, 158, 255, 205), width=10)
    d.arc((78, 78, 434, 434), start=34, end=146, fill=(74, 158, 255, 95), width=8)

    # X 发光层（弱一点，避免发灰）
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    center(gd, (0, 0, S, S), "X", font(286), (46, 130, 245, 150), off=(0, -12))
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    im.alpha_composite(glow)
    # X 主体
    center(d, (0, 0, S, S), "X", font(286), (244, 249, 255, 255), off=(0, -12))

    # 右上「实时」脉冲点：统一蓝色系，不用绿
    d.ellipse((366, 82, 420, 136), fill=(20, 36, 68, 255))
    d.ellipse((372, 88, 414, 130), fill=(74, 158, 255, 255))
    d.ellipse((385, 101, 401, 117), fill=(238, 248, 255, 255))

    # 柔和投影
    alpha = im.getchannel("A")
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sh.paste((4, 10, 24, 110), (0, 0, S, S), alpha.filter(ImageFilter.GaussianBlur(22)))
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.alpha_composite(sh)
    out.alpha_composite(im)
    return out


def save_ico(frames, path):
    """手写 ICO 容器：Pillow 的 append_images 对 ICO 无效，会只留下第一个尺寸。
    每帧用 PNG 压缩嵌入（Vista+ 支持），目录项按尺寸从小到大排列。"""
    import io
    import struct

    blobs = []
    for im in frames:
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        blobs.append(buf.getvalue())

    n = len(blobs)
    header = struct.pack("<HHH", 0, 1, n)
    offset = 6 + 16 * n
    entries, data = [], b""
    for (w, h), blob in zip([(f.width, f.height) for f in frames], blobs):
        # width/height 为 0 表示 256
        bw = 0 if w >= 256 else w
        bh = 0 if h >= 256 else h
        entries.append(struct.pack("<BBBBHHII", bw, bh, 0, 0, 1, 32,
                                   len(blob), offset))
        offset += len(blob)
        data += blob
    path.write_bytes(header + b"".join(entries) + data)


def main():
    src = build()
    src.save(BASE / "panel-icon.png")
    # 各尺寸独立 LANCZOS 缩放，保证 16/32 也清晰
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    frames = [src.resize(sz, Image.LANCZOS) for sz in sizes]
    ico = BASE / "panel.ico"
    save_ico(frames, ico)
    print("ICO:", ico, ico.stat().st_size, "bytes, sizes:",
          [(f.width, f.height) for f in frames])
    print("PNG:", BASE / "panel-icon.png")
    frames[5].save(BASE / "icon_preview.png")
    print("preview:", BASE / "icon_preview.png")


if __name__ == "__main__":
    main()
