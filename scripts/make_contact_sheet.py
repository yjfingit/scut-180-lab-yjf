#!/usr/bin/env python3
"""
为切片结果生成预览拼图：每个视频抽 3 帧（25% / 50% / 75% 位置）拼成九宫格。

用法:
    python make_contact_sheet.py --img-dir DIR --out out.jpg [--cols 9] [--tile 240]
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont


def pick_frames(d, k=3):
    fs = sorted(f for f in os.listdir(d) if f.lower().endswith(".jpg"))
    if not fs:
        return []
    if len(fs) <= k:
        return [os.path.join(d, f) for f in fs]
    out = []
    for i in range(k):
        pos = int(round(i * (len(fs) - 1) / (k - 1)))
        out.append(os.path.join(d, fs[pos]))
    return out


def load_font(size):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=9)
    ap.add_argument("--tile", type=int, default=240)
    ap.add_argument("--per-video", type=int, default=3)
    ap.add_argument("--label-size", type=int, default=13)
    args = ap.parse_args()

    root = args.img_dir
    if not os.path.isdir(root):
        print(f"目录不存在: {root}", file=sys.stderr)
        return 1

    subdirs = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    if not subdirs:
        print(f"没有子目录: {root}", file=sys.stderr)
        return 1

    tiles = []
    for vi, sd in enumerate(subdirs, 1):
        picks = pick_frames(os.path.join(root, sd), args.per_video)
        for fi, p in enumerate(picks, 1):
            tiles.append((f"{vi}.{fi}", p))

    tw, th = args.tile, int(args.tile * 9 / 16)
    label_h = args.label_size + 6
    cols = args.cols
    rows = (len(tiles) + cols - 1) // cols
    W = cols * tw
    H = rows * (th + label_h)
    sheet = Image.new("RGB", (W, H), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    font = load_font(args.label_size)

    for i, (label, path) in enumerate(tiles):
        r, c = divmod(i, cols)
        x, y = c * tw, r * (th + label_h)
        try:
            im = Image.open(path).convert("RGB").resize((tw, th), Image.LANCZOS)
        except Exception as e:
            print(f"跳过 {path}: {e}", file=sys.stderr)
            continue
        sheet.paste(im, (x, y))
        draw.text((x + 4, y + th + 1), label, fill=(220, 220, 225), font=font)

    sheet.save(args.out, quality=88)
    print(f"拼图: {args.out}")
    print(f"尺寸: {sheet.size}  格子: {len(tiles)} ({cols} 列 x {rows} 行)")
    print()
    print("编号 -> 视频目录:")
    for vi, sd in enumerate(subdirs, 1):
        n = len([f for f in os.listdir(os.path.join(root, sd)) if f.lower().endswith(".jpg")])
        print(f"  {vi:>2}.x  {sd:<24} ({n} 张)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
