# scut-180-lab-yjf

SCUT 实验室 **180 机**（8× RTX 3080 Linux 算力服务器）实验助手 —— 一个 WorkBuddy / Claude Agent Skill。

把 180 机当成外置算力用：所有操作限定在自己的家目录内，绝不误伤同机的其他使用者。

## 这个 Skill 解决什么问题

实验室公用服务器上跑实验，主要风险不是"跑不起来"，而是**误伤别人**：

- 抢了别人正在用的 GPU
- 读/写了别人的目录
- 杀了别人的进程
- 往快满的盘里写大文件

这个 Skill 用一套硬性围栏 + 精准判卡脚本把这些风险挡住，同时把工作流固定下来：
**体检 → 判卡 → 建环境 → 写码测试 → tmux 绑卡执行 → 收尾**。

## 核心能力

| 能力 | 说明 |
|---|---|
| **安全围栏** | `guard.sh` 对每条命令/路径做三档分区校验（允许 / 只读 / 拒绝），进入禁区直接中止 |
| **精准判卡** | `gpu_probe.py` 不用 `utilization.gpu` 判空闲（长跑任务大部分时刻采样为 0%，会误判），改用「显存接近基础值 + 未出现在 compute-apps」双条件 |
| **环境约定** | 该机无 conda/pip、系统 python 受 PEP668 保护，venv 必须 `--without-python` 建再引导；文档里写清了这些反直觉的坑 |
| **长任务保活** | tmux + `CUDA_VISIBLE_DEVICES` 显式绑卡，日志重定向，断连不丢 |
| **专属代理** | 在 180 机上部署私有 mihomo 代理（独立端口），解决 GitHub 直连不通、HuggingFace DNS 污染等问题 |

## 目录结构

```
.
├── SKILL.md                    主技能文档（Agent 读取的入口）
├── references/
│   └── platform-notes.md       平台细节、权限矩阵、踩坑记录
└── scripts/
    ├── guard.sh                安全围栏校验（路径分区 + 危险命令扫描）
    ├── gpu_probe.py            精准判卡，输出每卡进程表与推荐卡
    └── README-local-env.md     本地环境说明
```

## 安装

这是 Agent Skill 格式（YAML frontmatter + Markdown）。装到用户级 skill 目录：

```bash
git clone https://github.com/yjfingit/scut-180-lab-yjf.git
cp -r scut-180-lab-yjf ~/.workbuddy/skills/
```

项目级安装则放到 `<项目>/.workbuddy/skills/`。

## 使用

装上后，提到「180机」「3080server180」「实验室服务器」「抢卡」「远程实验」等词会自动触发。

围栏校验可以直接调用：

```bash
# 校验路径是否在允许范围
bash scripts/guard.sh path "/home/yangjuanfeng/lab/projects/foo"
# 退出码: 0=通过  1=拒绝  2=只读区

# 校验命令是否危险
bash scripts/guard.sh cmd "rm -rf /home/yangjuanfeng/lab/tmp"
```

判卡：

```bash
ssh 3080server180 'python3 /home/yangjuanfeng/lab/tools/gpu_probe.py'
```

## 环境适配说明

> ⚠️ 本 Skill 绑定**特定主机与本人家目录**（SSH 别名 `3080server180`、家目录 `/home/yangjuanfeng`）。
> 换机器或换用户，需要同步修改 `SKILL.md` 中的路径约定与 `guard.sh` 里的家目录常量。

其中一些经验是通用的，值得借鉴：

- **判 GPU 空闲不能只看利用率**——必须看显存 + 计算进程列表
- **无 sudo 的机器上装包必须先建 venv**，且要处理 `ensurepip` 缺失
- **ultralytics 的 `datasets_dir` 解析基准不是 yaml 所在目录**，必须写绝对路径
- **订阅类服务常按 User-Agent 内容协商返回不同格式**，换 UA 可能从"节点列表"变成"完整配置"
- **机场规则库可能缺域名**导致 DNS 污染，表现为 TLS 握手失败而非连接失败

## License

MIT
