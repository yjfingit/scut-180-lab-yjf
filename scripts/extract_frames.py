#!/usr/bin/env python3
"""
视频切片：每 stride 帧抽取 1 帧存为 JPEG。

输出布局（每个视频一个子目录）:
    <out_dir>/<视频名>/<源帧号:06d>.jpg

文件名用「源视频中的帧序号」，因此可直接反推时间点（帧号 / fps = 秒）。
例如 000270.jpg 在 29.97fps 下约为第 9.0 秒。

用法:
    python extract_frames.py --video-dir DIR --out-dir DIR [--stride 10]
                             [--quality 2] [--workers 15] [--limit N] [--dry-run]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import imageio_ffmpeg

    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = "ffmpeg"

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg"}
SEQ_PREFIX = "seq_"


def list_videos(d):
    return sorted(
        os.path.join(d, n) for n in os.listdir(d)
        if os.path.splitext(n)[1].lower() in VIDEO_EXT
    )


def extract_one(video, out_root, stride, quality, threads):
    """抽取单个视频。返回统计字典。"""
    stem = os.path.splitext(os.path.basename(video))[0]
    outdir = os.path.join(out_root, stem)
    os.makedirs(outdir, exist_ok=True)

    t0 = time.time()
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-threads", str(threads),
        "-i", video,
        "-vf", f"select=not(mod(n\\,{stride}))",
        "-fps_mode", "passthrough",
        "-q:v", str(quality),
        "-start_number", "0",
        os.path.join(outdir, f"{SEQ_PREFIX}%06d.jpg"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")

    seq_files = sorted(
        f for f in os.listdir(outdir)
        if f.startswith(SEQ_PREFIX) and f.endswith(".jpg")
    )

    # 顺序编号 -> 源帧号
    renamed = 0
    for f in seq_files:
        try:
            seq = int(f[len(SEQ_PREFIX):-4])
        except ValueError:
            continue
        new = f"{seq * stride:06d}.jpg"
        os.replace(os.path.join(outdir, f), os.path.join(outdir, new))
        renamed += 1

    return {
        "video": os.path.basename(video),
        "stem": stem,
        "out_dir": outdir,
        "images": renamed,
        "elapsed": round(time.time() - t0, 1),
        "rc": r.returncode,
        "stderr": (r.stderr or "").strip()[-500:],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--stride", type=int, default=10)
    ap.add_argument("--quality", type=int, default=2)
    ap.add_argument("--workers", type=int, default=15)
    ap.add_argument("--threads", type=int, default=6, help="每个 ffmpeg 进程的线程数")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个视频（测试用）")
    ap.add_argument("--only", default=None, help="只处理文件名含该子串的视频（测试用）")
    ap.add_argument("--manifest", default=None, help="写出 manifest json 路径")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.video_dir):
        print(f"视频目录不存在: {args.video_dir}", file=sys.stderr)
        return 1

    videos = list_videos(args.video_dir)
    if args.only:
        videos = [v for v in videos if args.only in os.path.basename(v)]
    if args.limit:
        videos = videos[: args.limit]
    if not videos:
        print("没有匹配的视频", file=sys.stderr)
        return 1

    print(f"ffmpeg : {FFMPEG}")
    print(f"输入   : {args.video_dir}")
    print(f"输出   : {args.out_dir}")
    print(f"步长   : 每 {args.stride} 帧 1 张   JPEG q={args.quality}")
    print(f"并行   : {args.workers} 进程 x {args.threads} 线程")
    print(f"视频数 : {len(videos)}")
    print()

    if args.dry_run:
        for v in videos:
            print(f"  [dry] {os.path.basename(v)} -> {os.path.join(args.out_dir, os.path.splitext(os.path.basename(v))[0])}/")
        return 0

    os.makedirs(args.out_dir, exist_ok=True)

    t_start = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(extract_one, v, args.out_dir, args.stride, args.quality, args.threads): v
            for v in videos
        }
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            flag = "OK " if res["rc"] == 0 else "ERR"
            extra = f"  <<< {res['stderr']}" if res["rc"] != 0 else ""
            print(f"[{flag}] {res['video']:<32} {res['images']:>5} 张  "
                  f"{res['elapsed']:>6.1f}s{extra}")

    total = sum(r["images"] for r in results)
    bad = [r for r in results if r["rc"] != 0]
    print()
    print(f"合计 {total} 张，用时 {time.time() - t_start:.1f}s")
    if bad:
        print(f"⚠️  {len(bad)} 个视频出错:")
        for r in bad:
            print(f"   - {r['video']}: {r['stderr'][:200]}")

    if args.manifest:
        with open(args.manifest, "w", encoding="utf-8") as f:
            json.dump({"stride": args.stride, "quality": args.quality,
                       "video_dir": args.video_dir, "out_dir": args.out_dir,
                       "total_images": total, "results": results},
                      f, ensure_ascii=False, indent=2)
        print(f"manifest: {args.manifest}")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
