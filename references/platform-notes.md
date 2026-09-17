# 180 机平台细节

## 机器概况

| 项 | 值 |
|---|---|
| SSH 别名 | `3080server180` |
| 主机名 | `pc-SYS-4029GP-TRT` |
| 系统 | **Linux（Ubuntu）**，内核 6.x，`/bin/sh` 为 dash |
| GPU | 8 × NVIDIA GeForce RTX 3080（10 GB 显存/张） |
| 内存 | 503 GB |
| 账号 | `yangjuanfeng`（uid 1051，组 `users`） |
| Tailscale IP | `100.126.143.118` |
| 登录密钥 | `~/.ssh/id_ed25519_lab_yangjuanfeng`（免密） |

属于 SCUT B7-240 服务器组（同组还有 `4090server175`，以及经 180 跳板的 `pazhoua800` / `pazhou3090`）。

## 权限矩阵（实测）

`/home` 下共 72 个目录，按访问能力分三档：

### 可读写
| 路径 | 说明 |
|---|---|
| `/home/yangjuanfeng/` | 自己的家目录，`drwxr-x---` |
| `/tmp/`、`/var/tmp/` | `1777`，带 sticky bit —— **只能删自己创建的文件** |
| `/tmp/yjf-*` | 本技能约定的临时工作区命名前缀 |

### 只读放行
| 路径 | 说明 |
|---|---|
| `/home/cv_datasets/` | 151 GB 公共数据集仓库，777 权限。含 Imagenet、coco、cifar、places365、iNaturalist2018、CAPPIDBZ、RadarData 等。**只读使用，绝不写入。** |

### 禁区（系统不拦，靠自觉）
| 路径 | 权限 | 风险 |
|---|---|---|
| `/home/backup/` | 777 | nginx 与系统备份（2022–2024），误删无提示 |
| `/home/backup_208/` | 777 | 空目录 |
| `/home/lost+found/` | 700 | 文件系统恢复区 |
| `/mnt/data1/` | 755 属 liupeng | 只读，不可写 |
| `/etc` `/usr` `/var` `/opt` `/root` `/boot` `/sys` `/proc` | — | 系统目录 |

其余 47 个用户目录多为 755（可读），25 个为 750（不可访问）。
**无论可读与否，一律不进他人目录。**

## 磁盘水位

| 挂载点 | 容量 | 状态 |
|---|---|---|
| `/`（含 `/tmp`） | 761 G | 7% 已用，677 G 可用 |
| `/mnt/data1` | 3.6 T | 34% 已用，只读 |
| `/home` | 33 T | **接近写满**，余量极小 |

`/home` 长期处于高水位，写入前必须查 `df -h /home`。

## 软件栈

**有**：`python3`(3.12.3)、`tmux`、`screen`、`git`、`rsync`、`curl`、`wget`、`nvcc`、`gcc`、`docker`（无权限）、`tailscale`

**无**：`conda` / `mamba` / `micromamba` / `uv` / `pip` / `slurm`(`sbatch`/`squeue`/`srun`)

系统 python 受 PEP668 保护（`/usr/lib/python3.12/EXTERNALLY-MANAGED`），
**不能** `pip install --user`，必须自建 venv。

## 判空闲 GPU 的正确方法

**错误做法**：看 `utilization.gpu`。它是瞬时采样，长跑任务大部分时刻采出来是 0%，
会把别人的卡误判为空。实测八张卡 util 全 0%，但其中两张已被他人进程占住 4.7 G / 6.4 G。

**正确判据**（两条同时成立）：
1. `memory.used` 接近基础值（约 4 MiB，驱动开销）
2. 该卡未出现在 `nvidia-smi --query-compute-apps` 列表

关联方法：用 `gpu_uuid` 把 `--query-gpu=index,uuid` 与
`--query-compute-apps=gpu_uuid,pid,used_memory` 对齐，得到「每卡进程表」。
再用 `ps -o user=` 查进程属主，判断是自己的还是别人的。

## 踩坑记录

- **`utilization` 不可信**：见上。
- **`/mnt/data1` 看似可用实则只读**：属 liupeng，755，写不进去。
- **777 目录是隐形地雷**：`/home/backup` 等权限开放，系统不拦，只能靠围栏自觉。
- **长任务必须 tmux**：SSH 断连会杀掉前台进程。
- **不显式绑卡会被抢占**：12 人共用且无调度器，不设 `CUDA_VISIBLE_DEVICES` 可能撞车。
- **本地 Git Bash 的 PATH 需要修补**：见 `scripts/` 中的说明（Windows 侧问题，非服务器问题）。
