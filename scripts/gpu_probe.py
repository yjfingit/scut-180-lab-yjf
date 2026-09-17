#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gpu_probe.py - 在 180 机上精准判定 GPU 空闲情况。

关键原则（不要改成看 utilization）：
  utilization.gpu 是瞬时采样，长跑任务大部分时刻采样出来就是 0%，
  用它判空闲会把别人的卡误判为空。可靠判据只有两条同时成立：
    1) memory.used 接近基础值（约 4 MiB，驱动开销）
    2) gpu_uuid 未出现在 `nvidia-smi --query-compute-apps` 中

输出：JSON（便于上层解析）+ 人类可读摘要（stderr）。

用法：
  python3 gpu_probe.py                # 人类可读 + JSON
  python3 gpu_probe.py --json         # 仅 JSON
  python3 gpu_probe.py --me yangjuanfeng   # 指定自己的账号，用于区分"我的卡"
"""

import json
import subprocess
import sys
import argparse


BASE_MEM_THRESHOLD = 64  # MiB。低于此值视为无实质占用（基础值约 4 MiB，留余量）


def run(cmd):
    try:
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=20
        ).stdout.strip()
    except Exception:
        return ""


def query_gpus():
    out = run(
        "nvidia-smi --query-gpu=index,uuid,name,memory.used,memory.total,"
        "utilization.gpu,temperature.gpu --format=csv,noheader,nounits"
    )
    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            continue
        gpus.append(
            {
                "index": int(parts[0]),
                "uuid": parts[1],
                "name": parts[2],
                "mem_used": int(parts[3]),
                "mem_total": int(parts[4]),
                "util": int(parts[5]),
                "temp": int(parts[6]),
            }
        )
    return gpus


def query_compute_apps():
    """返回 {gpu_uuid: [{pid, used_mem, user, etime, comm}, ...]}"""
    out = run(
        "nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory "
        "--format=csv,noheader,nounits"
    )
    mapping = {}
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        uuid, pid, mem = parts[0], parts[1], parts[2]
        info = {"pid": int(pid), "used_mem": int(mem)}
        # 关联进程属主与运行时长（这是判"是谁在用"的关键）
        ps = run(
            "ps -o user=,etime=,comm= -p %d 2>/dev/null" % int(pid)
        )
        if ps:
            f = ps.split()
            info["user"] = f[0] if len(f) > 0 else "?"
            info["etime"] = f[1] if len(f) > 1 else "?"
            info["comm"] = f[2] if len(f) > 2 else "?"
        else:
            info["user"] = "?"
            info["etime"] = "?"
            info["comm"] = "?"
        mapping.setdefault(uuid, []).append(info)
    return mapping


def build_report(me="yangjuanfeng"):
    gpus = query_gpus()
    apps = query_compute_apps()
    result = {
        "host": run("hostname"),
        "me": me,
        "free": [],
        "busy": [],
        "mine": [],
        "gpus": [],
    }

    for g in gpus:
        procs = apps.get(g["uuid"], [])
        # 判据：无进程 且 显存接近基础值
        looks_free = (len(procs) == 0) and (g["mem_used"] < BASE_MEM_THRESHOLD)
        owner_mine = any(p.get("user") == me for p in procs)

        gpu_view = {
            "index": g["index"],
            "name": g["name"],
            "mem_used": g["mem_used"],
            "mem_total": g["mem_total"],
            "util": g["util"],
            "temp": g["temp"],
            "status": "free" if looks_free else ("mine" if owner_mine else "busy"),
            "procs": procs,
        }
        result["gpus"].append(gpu_view)

        if looks_free:
            result["free"].append(g["index"])
        elif owner_mine:
            result["mine"].append(g["index"])
        else:
            result["busy"].append(g["index"])

    result["recommend"] = result["free"][0] if result["free"] else None
    return result


def human_report(r):
    lines = []
    lines.append("主机 %s | 我自己 %s" % (r["host"], r["me"]))
    lines.append("")
    lines.append("%-4s %-10s %-16s %-6s %-6s %s" % ("卡", "状态", "占用者", "显存", "温度", "跑多久"))
    lines.append("-" * 62)
    for g in r["gpus"]:
        if g["status"] == "free":
            owner, etime = "—", "—"
        else:
            u = g["procs"][0].get("user", "?") if g["procs"] else "?"
            owner = u
            etime = g["procs"][0].get("etime", "?") if g["procs"] else "?"
        label = {"free": "空闲", "mine": "我的", "busy": "占用"}[g["status"]]
        mem = "%d/%dM" % (g["mem_used"], g["mem_total"])
        lines.append(
            "%-4d %-10s %-16s %-6s %-6s %s"
            % (g["index"], label, owner, mem, str(g["temp"]) + "C", etime)
        )
    lines.append("")
    lines.append("空闲卡：%s" % (r["free"] or "无"))
    if r["mine"]:
        lines.append("我占用的卡：%s" % r["mine"])
    if r["busy"]:
        lines.append("他人占用：%s" % r["busy"])
    if r["recommend"] is not None:
        lines.append("推荐使用：GPU %d（启动前请再查一次）" % r["recommend"])
    else:
        lines.append("无空闲卡 —— 请等待或与占用者协商，不要抢占")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--me", default="yangjuanfeng")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = build_report(args.me)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(r, ensure_ascii=False))
        print(human_report(r), file=sys.stderr)


if __name__ == "__main__":
    main()
