# 本地执行说明（Windows 侧）

本技能大部分脚本在 180 机（Linux）上运行。但部分编排命令在**本地 Windows 的 Git Bash** 里执行，
该环境默认 PATH 残缺（`dirname`、`head`、`cut` 等命令缺失），需先修补：

```bash
export PATH="/c/Users/yangjuanfeng/.workbuddy/binaries/PortableGit/versions/1.2.0/usr/bin:/c/Users/yangjuanfeng/.workbuddy/binaries/PortableGit/versions/1.2.0/mingw64/bin:$PATH"
```

## 其他本地注意事项

- `git bundle create /tmp/x.bundle` 会被 Git Bash 转成 Windows 路径而失败 → 改用相对路径
- `ssh -o BatchMode=yes 3080server180 '<cmd>'` 可直接非交互执行
- 传给 180 的 `scp` 源文件用 POSIX 风格绝对路径（`/c/Users/...`）
