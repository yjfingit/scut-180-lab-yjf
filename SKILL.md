---
name: scut-180-lab-yjf
description: Use this skill whenever operating the SCUT lab server "180机" (SSH alias 3080server180, a Linux host with 8× RTX 3080) as remote compute — checking GPU availability, preparing Python environments, writing/testing/running experiment code on the server, launching long jobs under tmux with explicit GPU binding, and cleaning up. It enforces a strict safety fence so that every operation stays inside /home/yangjuanfeng, never reads other users' files, and never touches other users' processes. Trigger whenever the user mentions 180机, 3080server180, 实验室服务器, remote experiments, grabbing a GPU, or running code on the lab machine.
agent_created: true
---

# SCUT 180 机实验助手

在 **180 机**（实验室公用的 Linux 算力服务器）上做实验的专用技能。目标：把 180 当外置算力，所有活都在 `/home/yangjuanfeng/` 里干，绝不误伤他人。

**环境前提：180 机是 Linux 系统**（Ubuntu，`/bin/sh` 为 dash）。
所有脚本、命令、路径分隔符、权限语义都按 POSIX/Linux 理解，**不要按 Windows 习惯处理**——
本地（Windows）是发指令的一端，远端（Linux）是执行的一端，两者路径与命令风格不同。
本地编排脚本可用 Git Bash 执行，但**下发到 180 的命令必须符合 Linux 语法**。

## 铁律（不可绕过）

1. **一切操作限于 `/home/yangjuanfeng/` 内。**
   写、改、删、建只能发生在自己的家目录；唯一例外是只读挂载的公共数据集
   `/home/cv_datasets/`（只读，绝不写入）。
2. **绝不读取他人文件。** 其他用户的目录（`/home/<其他用户名>/`）一律不进、不读、不列。
   即使是 755 可读目录也不读。
3. **绝不操作他人进程。** 只处理属主为 `yangjuanfeng` 的进程；禁止无属主限定的
   `pkill` / `killall`。
4. **破坏性操作必须先出清单再确认。** 删除文件、终止进程前，先打印完整目标清单
   （路径/进程 + 属主），取得用户确认后才执行。
5. **绝不进入禁区。** `/home/backup`、`/home/backup_208`、`/mnt/*`、`/etc`、`/usr`、
   `/var`、`/opt`、`/root`、`/boot` 等一律不碰。
   注意：`/home/backup`、`/home/backup_208` 是 **777 权限**，系统不会拦，必须靠本技能自觉拦住。

在任何操作前，先跑围栏校验：

```bash
bash ~/.workbuddy/skills/scut-180-lab-yjf/scripts/guard.sh path "<远程绝对路径>"
bash ~/.workbuddy/skills/scut-180-lab-yjf/scripts/guard.sh cmd  "<将要执行的命令>"
```

退出码 0 = 通过，1 = 拒绝（必须中止并告知用户），2 = 只读区（可读，禁止写）。

## 连接方式

```bash
ssh -o BatchMode=yes 3080server180 '<command>'
```

免密登录（密钥 `id_ed25519_lab_yangjuanfeng`），非交互可用，可直接执行命令。

## 环境约束（这台机器的真实情况，别假设相反）

| 项 | 实况 | 影响 |
|---|---|---|
| 系统 | **Linux（Ubuntu）**，`/bin/sh` 是 dash | 命令按 POSIX 写，别用 Windows 路径 |
| 调度器 | **无 slurm** | 没有排队，只能自己看卡、自己占 |
| 包管理 | **无 conda / pip / uv**，系统 python3 受 PEP668 保护 | 装包必须先建 venv |
| 容器 | 有 docker 但**不在 docker 组** | 容器方案不可用 |
| 权限 | **无 sudo** | 不能做系统级安装 |
| 保活 | 有 `tmux` / `screen` | 长任务必须用 tmux |
| 磁盘 | `/home` 极度饱和 | 写入前查水位 |
| 代理 | `127.0.0.1:7890`（他人服务，仅借用） | **GitHub 直连不通**，拉 GitHub 必须走代理 |
| venv | `/home/yangjuanfeng/lab/envs/venv` 已就绪 | 直接复用，调用时用其 bin/python |
| 联网注意 | ultralytics 等库会自动下载模型/数据集 | 训练前先把权重放到本地目录，避免中途卡在下载 |
| 数据布局 | 数据集/权重在 `lab/shared/`，不在项目内 | yaml 的 path 必须写绝对路径 |

**重构或移动文件后的验证要求**（本次实践教训）：
改动路径后不能只看文件在不在，必须端到端实跑一次：
`py_compile` 语法检查 → 数据集 check 脚本 → **实际启动一次训练** →
确认指标与改动前一致 + GPU 干净释放。否则断链问题会在真正跑长任务时才暴露。

## ⚠️ 下发命令的两条硬规则

这两条是实战踩出来的，违反必出错：

1. **不要用「ssh 单引号里嵌 python 代码」的写法。**
   本地 Git Bash 会对多层引号做错误解析，报 `syntax error near unexpected token '('`。
   正确做法：用 Write 工具在本地写 `.py` 文件 → `scp` 上传 → 远端执行。
   少数简单场景可退而使用 `python - <<'PYEOF'` heredoc；含中文或括号时仍建议走文件。

2. **远端脚本里引用 python 必须写绝对路径** `/home/yangjuanfeng/lab/envs/venv/bin/python`，
   不要依赖 PATH 或 `python` 裸命令。

## 六个动作

### ① 体检 check

开工前先看全局。跳过这步容易撞上被占的卡或写满的盘。

```bash
ssh -o BatchMode=yes 3080server180 '
hostname; uptime
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader
df -h /home /tmp
free -h'
```

关注：空闲卡数量、`/home` 剩余空间、负载、在线人数。

### ② 判卡 gpu（核心能力）

**关键：不要用 `utilization.gpu` 判空闲。** 它是瞬时采样，长跑任务大部分时刻采出来就是 0%，
会把别人的卡误判为空。可靠判据是两条同时成立：

1. `memory.used` 接近基础值（约 4 MiB）
2. 该卡未出现在 `nvidia-smi --query-compute-apps`

用技能自带脚本（已部署在 180 机 `/home/yangjuanfeng/lab/tools/gpu_probe.py`）：

```bash
ssh -o BatchMode=yes 3080server180 'python3 /home/yangjuanfeng/lab/tools/gpu_probe.py'
```

输出每卡进程表：卡号 / 状态 / 占用者 / 显存 / 温度 / 运行时长，并给出推荐卡。
若推荐卡为空，**报告等待或协商，绝不抢占**。

### ③ 环境 env

在 `/home/yangjuanfeng/lab/envs/venv` 建虚拟环境（系统 python 装不了包）：

```bash
ssh -o BatchMode=yes 3080server180 '
cd /home/yangjuanfeng/lab
python3 -m venv --without-pip venv
curl -sSL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
./venv/bin/python /tmp/get-pip.py
./venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <packages>'
```

**⚠️ 必须加 `--without-pip`。** 该机 python3.12 缺 `ensurepip`，直接 `python3 -m venv venv`
会报 `ensurepip is not available` 而失败。建好后用 `get-pip.py` 手动引导。

**调用约定（最容易踩的坑）**：装好包后，一定要用 venv 里的解释器显式调用，
否则会 `ModuleNotFoundError`（系统 python3 里没有这些包）：

```bash
/home/yangjuanfeng/lab/envs/venv/bin/python your_script.py
# 或先激活：source /home/yangjuanfeng/lab/envs/venv/bin/activate
```

**已有可用环境（勿重复搭建）**：`/home/yangjuanfeng/lab/envs/venv` 已装好
torch 2.5.1+cu121 / torchvision 0.20.1+cu121 / ultralytics 8.4.154，直接复用即可。

**⚠️ 若移动 venv 目录，必须修 shebang。** venv 内 `bin/` 下的 pip、yolo、torchrun 等
约 26 个脚本的 shebang 都写死了原始绝对路径；`pyvenv.cfg` 的 `command` 字段只是历史记录，无需改。
移动后执行：

```bash
cd <新路径>/bin
for f in *; do
  [ -f "$f" ] && head -1 "$f" 2>/dev/null | grep -q "<旧路径>" && \
    sed -i "1s|<旧路径>|<新路径>|" "$f"
done
# activate* 脚本内嵌路径较多，用全局替换
sed -i "s|<旧路径>|<新路径>|g" activate activate.csh activate.fish Activate.ps1
```

**⚠️ ultralytics 数据集 yaml 的 `path` 必须写绝对路径。**
相对 path 的解析基准是 `~/.config/Ultralytics/settings.json` 里的 `datasets_dir`，
**不是 yaml 文件所在目录**；写相对路径会被解析到 `~/datasets/` 下并报 `images not found`。

**⚠️ ultralytics 会自动往 cwd 塞权重文件**（如 `src/weights/yolo26n.pt`），
可能与你放在 `shared/weights/` 的重复。发现后核对 MD5，相同则删项目内那份。

网络：pip 直连清华源即可；**GitHub 直连不通**，需要时切代理：
`export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890`
（7890 是他人服务，只借环境变量，绝不动其进程）

### ④ 写码与测试 dev

代码直接写在 180 上（不经过本机往复传输）。工作目录遵循标准工程布局：

```
/home/yangjuanfeng/lab/
├── README.md  .gitignore  lab-notes.md
├── envs/venv/               虚拟环境（集中存放，不散落各项目）
├── shared/                  跨项目共享的只读资产
│   ├── datasets/            数据集
│   └── weights/             预训练权重
├── tools/                   运维脚本（与具体项目无关）
├── projects/<项目名>/       每个实验独立目录
│   ├── src/                 源码（只放代码）
│   ├── scripts/             调试/运维脚本
│   ├── assets/              软链到 shared/（datasets、weights）
│   ├── logs/                运行日志
│   └── outputs/             训练产出
└── lab-notes.md             实验登记

兼容软链（**勿删**，旧路径仍可用）：`venv -> envs/venv`、`_tools -> tools`
```

**布局原则**：环境集中 / 资产独立于项目 / 代码与产物分离 / 工具与项目解耦。

**新增项目时**按此模板建目录，并在 `projects/<项目名>/assets/` 下用相对软链
引用共享资产（注意层级：`../../../shared/<资产名>`）。

小测试直接跑：`ssh -o BatchMode=yes 3080server180 'cd .../src && /home/yangjuanfeng/lab/envs/venv/bin/python test_xx.py'`

**传输方式**：本地写好的文件用 `scp` 推上去（Windows 本地路径用 `/c/...`）：

```bash
scp -o BatchMode=yes local_file.py 3080server180:/home/yangjuanfeng/lab/projects/<项目>/src/
```

**远端自检套路**：上传后先做语法检查再跑，避免白等

```bash
ssh -o BatchMode=yes 3080server180 '/home/yangjuanfeng/lab/envs/venv/bin/python -m py_compile <脚本路径> && echo SYNTAX_OK'
```

### ⑤ 执行 run

长任务必须 tmux 保活 + **显式绑卡**（防止跑到别人卡上）：

```bash
ssh -o BatchMode=yes 3080server180 '
cd /home/yangjuanfeng/lab/projects/<项目>/src
tmux new-session -d -s yjf-<任务名> \
  "CUDA_VISIBLE_DEVICES=<卡号> /home/yangjuanfeng/lab/envs/venv/bin/python train.py 2>&1 | tee ../logs/<任务名>.log"'
```

- 启动前**再跑一次判卡**（防止间隙被抢）
- `CUDA_VISIBLE_DEVICES` 必须显式指定，不要依赖默认
- 会话名统一加 `yjf-` 前缀，便于只识别自己的
- 日志重定向到文件，断连不丢
- **python 路径用绝对路径**，不要依赖 PATH（tmux 内的环境可能与交互 shell 不同）

查看进度：`tmux ls`（只找 `yjf-` 开头的）、`tail -f ../logs/<任务名>.log`

### ⑥ 收尾 clean

只列**自己的**会话与进程，确认后释放：

```bash
ssh -o BatchMode=yes 3080server180 '
echo "--- 我的 tmux ---"; tmux ls 2>/dev/null | grep "^yjf-" || echo "无"
echo "--- 我的 GPU 进程 ---"
ps -u yangjuanfeng -o pid,etime,pcpu,comm --no-headers'
```

释放步骤（每一项都需用户确认）：
1. `tmux kill-session -t yjf-<任务名>`（只杀自己的会话）
2. 若进程残留，先核对 `ps -o user=` 确认属主，再 `kill <PID>`

## 专属代理（本人私有，端口 6666）

180 机原先只有他人借用的 `127.0.0.1:7890`。现已部署**本人专属** mihomo 代理，
端口 `6666`（混合 HTTP+SOCKS5），彻底独立于他人服务。

**部署位置**：`/home/yangjuanfeng/lab/proxy/`
```
proxy/
├── bin/mihomo              mihomo v1.19.31 (linux-amd64, with_gvisor)
├── conf/config.yaml        生成产物（勿手改，会被覆盖）
├── conf/sub.url            订阅地址（600 权限）
├── conf/sub.raw            订阅原始缓存
├── conf/backup/            历史配置备份（自动保留 5 份）
├── scripts/sync_sub.py     订阅同步 + 配置生成
├── proxy.sh                管理入口
├── proxy_env.sh            shell 环境（bashrc 已 source）
└── keepalive.sh            保活 + 定时刷新
```

**日常用法**（交互式 shell 已自动开启代理）：

```bash
proxy start|stop|restart|status|log|sync|reload|test
proxyon / proxyoff / proxyst     # 当前 shell 开关
```

**手动指定**（非交互 SSH、脚本、tmux 内）：

```bash
export https_proxy=http://127.0.0.1:6666 http_proxy=http://127.0.0.1:6666
export all_proxy=socks5h://127.0.0.1:6666
```

**保活**：crontab 每分钟自动拉起；每天 04:00 自动拉订阅 + 热重载。日志 `logs/keepalive.log`。

### 关键坑：订阅按 UA 内容协商

同一个订阅 URL，**User-Agent 不同返回的格式完全不同**：

| UA | 返回格式 | 处理 |
|---|---|---|
| 含 `clash` / `verge` | 完整 Clash YAML（71 节点 + 9 分组 + 9263 规则） | ✅ 直接改端口用 |
| 默认 / 浏览器 | base64 编码的分享链接 | ❌ 还要自己转换 |

`sync_sub.py` 里固定用 `clash-verge/v2.0.0` 作 UA，别改成浏览器 UA。
实测：换 UA 会让 36KB 的分享链接变成 517KB 的完整 YAML —— 后者才是想要的。

### 关键坑：机场规则库可能缺域名（DNS 污染）

机场规则库不含 `huggingface.co` 时，请求落入 `MATCH,🐟漏网之鱼`，
其 DNS 走国内解析 → **拿到污染 IP（如 huggingface.co → 202.160.128.238）**，
表现为 `CONNECT` 隧道建立成功但 `SSL_ERROR_SYSCALL`、HTTP 000。

判断方法（看 DNS 结果是否离谱）：`curl "http://127.0.0.1:6667/dns/query?name=<域名>&type=A"`

修复：在 `sync_sub.py` 的 `EXTRA_RULES` 里补该域名，插到 `GEOIP,cn,DIRECT` **之前**，
并加 `nameserver-policy` 走加密 DNS。重跑 `sync_sub.py --offline` + `proxy reload`。
新增域名照此办理即可，不必等机场更新。

## 推送到 GitHub（本机无凭证时的解法）

180 机**没有 GitHub SSH key，也没有 gh CLI**，而 HTTPS 推送不接受密码。
在无图形界面的服务器上给浏览器授权，用 **GitHub Device Flow**：

**原理**：180 机向 GitHub 申请一次性 `user_code`，用户在自己电脑的浏览器里填码授权，
180 机轮询换取 token。用户密码不经过任何中间方。

```bash
# 1. 发起授权（client_id 是 gh CLI 的公开 ID，可长期用）
curl -s -X POST -H "Accept: application/json" \
  -d "client_id=178c6fc778ccc68e1d6a&scope=repo" \
  https://github.com/login/device/code
# 返回 user_code（如 30E7-9C14）、device_code、expires_in=899

# 2. 把 user_code 告诉用户，让其在浏览器打开 https://github.com/login/device 填入授权
#    （用 present_files 直接打开该 URL）

# 3. 后台轮询换取 token（authorization_pending 表示还没授权，继续等）
curl -s -X POST -H "Accept: application/json" \
  -d "client_id=178c6fc778ccc68e1d6a" \
  -d "device_code=<device_code>" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
  https://github.com/login/oauth/access_token
```

**推送后必做的清理**（否则 token 明文留在仓库配置里）：

```bash
cd <repo>
TOK=$(cat <token文件>)
git remote set-url origin https://<user>:${TOK}@github.com/<user>/<repo>.git
git push -u origin main
# 立刻去掉明文 token
git remote set-url origin https://github.com/<user>/<repo>.git
# 转存到 600 权限的凭证文件，以后 push 免输
git config --global credential.helper store
printf "https://<user>:%s@github.com\n" "$TOK" > ~/.git-credentials
chmod 600 ~/.git-credentials
shred -u <token文件>                  # 销毁临时明文
grep -r "gho_\|ghp_\|github_pat" .git/config   # 确认无残留
```

**推送后必须验证**（不能只看 push 成功）：对比本地/远端 commit SHA +
逐文件 `git hash-object` vs API 返回的 `sha` + 干净目录 `git clone` 一次。

**注意**：用户可能误读授权页的 "GitHub staff will never give you a code" ——
那是防钓鱼提示，不是"等别人发码"。要主动解释 `user_code` 是我方申请的。

## 视频切片（帧抽取）

把视频按固定间隔抽帧、产出可直接用于标注的图片集。**180 机没有 ffmpeg**，
先按 `references/platform-notes.md` 的「没有 ffmpeg 怎么办」装 `imageio-ffmpeg` 拿到静态二进制。

两个脚本配套使用，**先探测再抽取**（探测能提前暴露分辨率/帧率异常和磁盘压力）：

```bash
PY=/home/yangjuanfeng/lab/envs/venv/bin/python

# ① 探测：时长 / fps / 分辨率 / 预计切片数，并落一份 json
$PY scripts/probe_videos.py <视频目录> --stride 10 --json <日志目录>/video_meta.json

# ② 抽取：每个视频输出到一个子目录，文件名 = 源帧号
$PY scripts/extract_frames.py --video-dir <视频目录> --out-dir <图片目录> \
    --stride 10 --quality 2 --workers 15 --threads 6 \
    --manifest <日志目录>/frame_extract.json
```

要点：

- **先 `--limit 1` 小样验证**，确认帧号间隔、尺寸、单张体积都正常，再跑全量。
- 输出布局 `<out>/<视频名>/<源帧号:06d>.jpg`；**源帧号**便于反推时间点（帧号/fps = 秒）。
- ffmpeg 的 `%06d` 是输出序号，脚本内部按 `序号 × stride` 重命名成源帧号。
- 104 核可安全并行 15 个 ffmpeg（每个 `-threads 6`）。实测 3.2 G / 22226 帧约 34 秒。
- **务必核对每个视频的实际产出数与探测预测数是否一致**，不一致说明有解码错误。
- 抽完做一次**独立复核**：用 `select=eq(n\,K)` 单独抽某帧，与产物比对应逐像素一致。

## 参考

- `references/platform-notes.md` — 180 机平台细节、权限矩阵、踩坑记录

## 脚本

- `scripts/guard.sh` — 安全围栏校验（路径三档分区 + 命令危险模式扫描）
- `scripts/gpu_probe.py` — 精准判卡，输出每卡进程表与推荐卡
- `scripts/probe_videos.py` — 探测视频元数据，估算切片数量（无需 ffprobe）
- `scripts/extract_frames.py` — 按步长抽帧，每视频一个子目录，文件名用源帧号
- `scripts/make_contact_sheet.py` — 生成预览拼图，肉眼快速核验切片质量
