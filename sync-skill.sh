#!/usr/bin/env bash
# ============================================================
#  scut-180-lab-yjf 三处同步脚本（180机 版）
#
#  三处：PC 本机 / GitHub / 180机
#  权威源：GitHub（唯一 source of truth）
#
#  180 机上的两个位置：
#    A) ~/lab/projects/scut-180-lab-yjf-repo   Git 仓库工作副本
#    B) ~/.workbuddy/skills/scut-180-lab-yjf   Agent 实际加载的 skill 目录
#    => A 是 git 源，B 由 A 同步而来，两者内容必须一致
#
#  用法:
#    bash sync-skill.sh pull     从 GitHub 拉最新 -> 同步到 skill 目录
#    bash sync-skill.sh push     把 180机 仓库改动推到 GitHub
#    bash sync-skill.sh status   对比 GitHub / 仓库 / skill目录
#    bash sync-skill.sh apply    仅把仓库内容覆盖到 skill 目录
#    bash sync-skill.sh blobs    只输出 <文件> <blob8> 供跨机比对
# ============================================================
set -uo pipefail

# 代理：仅当 6666 端口在监听时才启用，避免代理挂掉导致 git/ssh 卡死
if (exec 3<>/dev/tcp/127.0.0.1/6666) 2>/dev/null; then
  exec 3<&- 3>&-
  export https_proxy=http://127.0.0.1:6666 http_proxy=http://127.0.0.1:6666
fi

REPO="/home/yangjuanfeng/lab/projects/scut-180-lab-yjf-repo"
SKILL="/home/yangjuanfeng/.workbuddy/skills/scut-180-lab-yjf"
BRANCH="main"

C_OK=$'\033[32m'; C_ERR=$'\033[31m'; C_INFO=$'\033[36m'; C_OFF=$'\033[0m'
info() { echo "${C_INFO}[sync]${C_OFF} $*"; }
ok()   { echo "${C_OK}  ✓${C_OFF} $*"; }
err()  { echo "${C_ERR}  ✗${C_OFF} $*"; }

# 纳入版本管理的 skill 内容文件（与仓库根目录下的 README/LICENSE 等区分开）
tracked_files() {
  cd "$REPO" || return 1
  git ls-files | grep -E '^(SKILL\.md$|references/|scripts/)' | grep -vE '\.(png|jpg|jpeg|gif)$'
}

# 只同步 skill 内容文件，不含 README/LICENSE/.gitignore 这类仓库专有文件
apply_to_skill() {
  info "仓库 -> skill 目录"
  mkdir -p "$SKILL"
  rsync -a --delete \
    --exclude='.git' --exclude='.gitignore' \
    --exclude='README.md' --exclude='LICENSE' \
    --exclude='sync-skill.sh' \
    "$REPO"/ "$SKILL"/ || { err "rsync 失败"; return 1; }
  chmod +x "$SKILL/scripts/"*.sh 2>/dev/null
  ok "skill 目录已同步"
}

do_pull() {
  cd "$REPO" || return 1
  info "拉取 GitHub 最新"
  git fetch origin -q && git reset -q --hard "origin/$BRANCH" || { err "拉取失败"; return 1; }
  ok "仓库更新到 $(git rev-parse --short HEAD)"
  apply_to_skill || return 1
  echo
  do_status
}

do_push() {
  cd "$REPO" || return 1
  # 先把 skill 目录的改动回灌到仓库（万一直接在 skill 目录改了）
  local dirty=0
  for f in $(git ls-files); do
    if [ -f "$SKILL/$f" ] && ! cmp -s "$SKILL/$f" "$f"; then
      cp "$SKILL/$f" "$f"; dirty=1
    fi
  done
  [ "$dirty" = "1" ] && info "检测到 skill 目录有改动，已回灌到仓库"

  if [ -z "$(git status --porcelain)" ]; then
    ok "无变化，GitHub 已是最新"
    return 0
  fi
  git add -A
  echo
  git status --short
  echo
  git commit -q -m "sync: 从 180机 更新 skill ($(date '+%Y-%m-%d %H:%M'))" || return 1
  info "推送到 GitHub"
  git push -q origin "$BRANCH" || { err "推送失败（检查 ~/.git-credentials）"; return 1; }
  ok "已推送 $(git rev-parse --short HEAD)"
}

do_status() {
  cd "$REPO" || return 1
  git fetch origin -q 2>/dev/null

  echo "════════ 180机 一致性检查 ════════"
  printf "%-34s %-14s %-14s %-14s\n" "文件" "GitHub" "仓库" "skill目录"
  printf "%-34s %-14s %-14s %-14s\n" "----" "------" "----" "---------"

  local mismatch=0
  for f in $(tracked_files); do
    local g r s
    g=$(git show "origin/$BRANCH:$f" 2>/dev/null | git hash-object --stdin 2>/dev/null)
    r=$(git hash-object "$f" 2>/dev/null)
    s=$( [ -f "$SKILL/$f" ] && git hash-object "$SKILL/$f" 2>/dev/null || echo "MISSING" )

    local mark=""
    if [ "$g" = "$r" ] && [ "$r" = "$s" ]; then
      mark="${C_OK}✓${C_OFF}"
    else
      mark="${C_ERR}✗${C_OFF}"; mismatch=$((mismatch+1))
    fi
    printf "%s %-32s %-14s %-14s %-14s\n" "$mark" "$f" \
      "$(printf '%.8s' "$g")" "$(printf '%.8s' "$r")" "$(printf '%.8s' "$s")"
  done

  echo
  if [ "$mismatch" -eq 0 ]; then
    echo "${C_OK}180机 内部一致（GitHub = 仓库 = skill目录）${C_OFF}"
  else
    echo "${C_ERR}$mismatch 个文件不一致${C_OFF}"
    echo "修复：bash $(basename "$0") pull"
  fi
}

# 精简输出，供 PC 侧脚本解析：<文件> <blob8>
do_blobs() {
  for f in $(tracked_files); do
    local s
    s=$( [ -f "$SKILL/$f" ] && git hash-object "$SKILL/$f" 2>/dev/null || echo "MISSING" )
    printf "%-32s %.8s\n" "$f" "$s"
  done
}

case "${1:-status}" in
  pull)  do_pull ;;
  push)  do_push ;;
  apply) apply_to_skill ;;
  status) do_status ;;
  blobs) do_blobs ;;
  *)
    echo "用法: bash sync-skill.sh {pull|push|apply|status|blobs}"
    ;;
esac
