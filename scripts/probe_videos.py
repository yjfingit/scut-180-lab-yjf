#!/usr/bin/env python3
"""
探测视频元数据，估算按 stride 切片后的图片数量。

用法:
    python probe_videos.py <视频目录> [--stride 10] [--json out.json]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

try:
    import imageio_ffmpeg

    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = "ffmpeg"

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg"}

RE_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
RE_VID = re.compile(r"Stream #\d+:\d+.*?:\s*Video:\s*([A-Za-z0-9_]+)")
RE_RES = re.compile(r"(\d{2,5})x(\d{2,5})")
RE_FPS = re.compile(r"([\d.]+)\s*fps")


def probe(path):
    """返回单个视频的元数据字典。"""
    info = {
        "file": os.path.basename(path),
        "path": path,
        "bytes": os.path.getsize(path),
        "duration": None,
        "fps": None,
        "width": None,
        "height": None,
        "codec": None,
        "frames": None,
        "ok": False,
        "error": None,
    }
    try:
        r = subprocess.run(
            [FFMPEG, "-hide_banner", "-i", path],
            capture_output=True, text=True, errors="replace", timeout=120,
        )
    except subprocess.TimeoutExpired:
        info["error"] = "timeout"
        return info
    err = r.stderr or ""

    m = RE_DUR.search(err)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        info["duration"] = h * 3600 + mi * 60 + s

    m = RE_VID.search(err)
    if m:
        info["codec"] = m.group(1)

    # 分辨率与 fps 都从 Video 流那一行取，避免误抓音频流
    for line in err.splitlines():
        if "Video:" not in line:
            continue
        mr = RE_RES.search(line)
        if mr:
            info["width"], info["height"] = int(mr.group(1)), int(mr.group(2))
        mf = RE_FPS.search(line)
        if mf:
            try:
                info["fps"] = float(mf.group(1))
            except ValueError:
                pass
        break

    if info["duration"] and info["fps"] and info["fps"] > 0:
        info["frames"] = int(round(info["duration"] * info["fps"]))
        info["ok"] = True
    elif info["duration"]:
        # 有些容器不报 fps，给个保守估计
        info["ok"] = True

    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video_dir")
    ap.add_argument("--stride", type=int, default=10)
    ap.add_argument("--json", default=None)
    ap.add_argument("--workers", type=int, default=0)
    args = ap.parse_args()

    d = args.video_dir
    if not os.path.isdir(d):
        print(f"目录不存在: {d}", file=sys.stderr)
        return 1

    files = sorted(
        os.path.join(d, n) for n in os.listdir(d)
        if os.path.splitext(n)[1].lower() in VIDEO_EXT
    )
    if not files:
        print(f"未找到视频文件: {d}", file=sys.stderr)
        return 1

    workers = args.workers or min(len(files), (os.cpu_count() or 8))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        metas = list(ex.map(probe, files))

    print(f"ffmpeg: {FFMPEG}")
    print(f"视频目录: {d}")
    print(f"切片步长: 每 {args.stride} 帧取 1 张")
    print()
    hdr = f"{'文件':<34} {'时长':>9} {'fps':>7} {'分辨率':>11} {'约帧数':>10} {'约切片':>8} {'体积':>9}"
    print(hdr)
    print("-" * len(hdr) * 1)

    tot_frames = tot_imgs = tot_bytes = 0
    for m in metas:
        dur = m["duration"] or 0
        dtxt = f"{int(dur // 60)}:{int(dur % 60):02d}"
        res = f"{m['width']}x{m['height']}" if m["width"] else "?"
        fps = f"{m['fps']:.2f}" if m["fps"] else "?"
        fr = m["frames"] or 0
        imgs = (fr + args.stride - 1) // args.stride if fr else 0
        tot_frames += fr
        tot_imgs += imgs
        tot_bytes += m["bytes"]
        print(f"{m['file']:<34} {dtxt:>9} {fps:>7} {res:>11} {fr:>10} {imgs:>8} "
              f"{m['bytes'] / 1024 / 1024:>8.1f}M")

    print("-" * 72)
    print(f"{'合计':<34} {'':>9} {'':>7} {'':>11} {tot_frames:>10} {tot_imgs:>8} "
          f"{tot_bytes / 1024 / 1024:>8.1f}M")
    print()
    print(f"预计输出图片总数: {tot_imgs}")

    # 按 4K jpg 约 1.5MB / 1080p 约 0.35MB 粗估体积
    res_seen = {(m["width"], m["height"]) for m in metas if m["width"]}
    if res_seen:
        print(f"出现的分辨率: {sorted(res_seen)}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"stride": args.stride, "video_dir": d,
                       "total_frames": tot_frames, "est_images": tot_imgs,
                       "videos": metas}, f, ensure_ascii=False, indent=2)
        print(f"元数据已写入: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
