#!/usr/bin/env bash
# guard.sh - 安全围栏核心。所有对 180 机的操作在拼接命令前，都应先过这一层校验。
#
# 用法（在本地执行，纯字符串校验，不联网）：
#   bash guard.sh path <远程绝对路径>        # 校验单条路径是否在允许范围内
#   bash guard.sh cmd  <要执行的命令字符串>   # 扫描命令中的危险模式
#   bash guard.sh show                        # 打印当前围栏规则
#
# 退出码：0 = 通过；1 = 拒绝（应当中止操作并告知用户）；2 = 只读区（允许读，禁止写）

set -u

HOST_ALIAS="3080server180"
ME="yangjuanfeng"
HOME_DIR="/home/yangjuanfeng"

# ---- 三档路径分区 ----------------------------------------------------------
# 档1 可读写：目录包含 或 名字前缀（以 = 结尾表示"前缀匹配"）
WRITABLE_PREFIXES=(
  "/home/yangjuanfeng"
  "/tmp/yjf-="
)
# 档2 只读：允许读，任何写/删一律拒绝
READONLY_PREFIXES=(
  "/home/cv_datasets"
)
# 档3 拦截：语义禁区。注意其中部分是 777 权限，系统不会拦，必须靠这里拦。
FORBIDDEN_PREFIXES=(
  "/home/backup"
  "/home/backup_208"
  "/home/lost+found"
  "/mnt"
  "/etc"
  "/usr"
  "/var"
  "/opt"
  "/root"
  "/boot"
  "/sys"
  "/proc"
)

RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; NC=$'\033[0m'

die()  { printf '%s[拒绝]%s %s\n' "$RED" "$NC" "$1"; exit 1; }
ok()   { printf '%s[通过]%s %s\n' "$GRN" "$NC" "$1"; }
warn() { printf '%s[警告]%s %s\n' "$YEL" "$NC" "$1"; }

# ---- 路径规整：折叠 . 与 .. ------------------------------------------------
normalize() {
  local p="$1" out="" part
  p=$(printf '%s' "$p" | sed 's|//*|/|g')
  local oldifs="$IFS"
  IFS='/'
  for part in $p; do
    case "$part" in
      ""|".") continue ;;
      "..") out=$(printf '%s' "$out" | sed 's|/[^/]*$||') ;;
      *) out="$out/$part" ;;
    esac
  done
  IFS="$oldifs"
  # 确保以 / 开头（IFS 切分会吃掉前导斜杠）
  if [ -z "$out" ]; then
    printf '/'
  else
    printf '%s' "/${out#/}"
  fi
}

# ---- 判断 path 是否被 rule 覆盖 -------------------------------------------
# rule 以 "=" 结尾 => 名字前缀匹配（如 /tmp/yjf-= 匹配 /tmp/yjf-run1）
# 否则 => 目录包含匹配（等于自身或位于其下）
is_under() {
  local path="$1" rule="$2"
  case "$rule" in
    *=)
      local pre="${rule%=}"
      case "$path" in
        "$pre"*) return 0 ;;
        *) return 1 ;;
      esac
      ;;
  esac
  if [ "$path" = "$rule" ]; then return 0; fi
  case "$path" in
    "$rule"/*) return 0 ;;
    *) return 1 ;;
  esac
}

# ---- 校验单条路径 ----------------------------------------------------------
check_path() {
  local raw="$1" p
  p=$(normalize "$raw")

  case "$p" in
    /*) ;;
    *) die "必须是绝对路径：$raw" ;;
  esac

  local w r f
  for w in "${WRITABLE_PREFIXES[@]}"; do
    if is_under "$p" "$w"; then
      ok "可读写：$p"
      return 0
    fi
  done

  for r in "${READONLY_PREFIXES[@]}"; do
    if is_under "$p" "$r"; then
      warn "只读区（禁止写入）：$p"
      return 2
    fi
  done

  for f in "${FORBIDDEN_PREFIXES[@]}"; do
    if is_under "$p" "$f"; then
      die "路径落在禁区：$p（命中规则 $f）"
    fi
  done

  # 其余 /home/<他人> 一律视为禁区
  if is_under "$p" "/home"; then
    die "路径属于其他用户或未授权区域：$p"
  fi

  die "路径不在允许范围内：$p"
}

# ---- 命令危险模式扫描 ------------------------------------------------------
check_cmd() {
  local cmd="$1"
  local hit=0

  # 1) 禁止 --no-preserve-root
  if printf '%s' "$cmd" | grep -q -- '--no-preserve-root'; then
    die "禁止 --no-preserve-root"
  fi

  # 2) 递归删除且目标是根级/家目录/通配这类"裸"路径
  #    只拦真正危险的形态：/ 本身、~、*、/home（不带子目录）、/mnt 等
  if printf '%s' "$cmd" | grep -qE 'rm[[:space:]]+-[a-zA-Z]*[rR]'; then
    if printf '%s' "$cmd" | grep -qE 'rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*[[:space:]]+(/[[:space:]]*$|/[[:space:]]+[^/]|~|[^[:alnum:]/_.-]*\*)'; then
      die "检测到对根级/家目录/通配路径的递归删除：$cmd"
    fi
    if printf '%s' "$cmd" | grep -qE 'rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*[[:space:]]+(/home|/mnt|/tmp|/etc|/usr|/var|/opt|/boot)[[:space:]]*$'; then
      die "检测到对系统级目录的递归删除：$cmd"
    fi
    warn "命令含递归删除，执行前请确认目标全部在你的目录内"
    hit=1
  fi

  # 3) 特权与系统级操作
  if printf '%s' "$cmd" | grep -qE '(chown|chgrp|mkfs|fdisk|parted|mount|umount|reboot|shutdown|poweroff|systemctl|useradd|userdel|passwd|visudo|sudo)[[:space:]]'; then
    die "命令包含特权/系统级操作：$cmd"
  fi

  # 4) 裸 pkill / killall（必须带 -u yangjuanfeng）
  if printf '%s' "$cmd" | grep -qE '(pkill|killall)[[:space:]]'; then
    if printf '%s' "$cmd" | grep -qE 'pkill[[:space:]]+-u[[:space:]]+(yangjuanfeng|[0-9]+)'; then
      ok "pkill 已限定属主"
    else
      die "禁止无属主限定的 pkill/killall（必须形如：pkill -u $ME <pattern>）：$cmd"
    fi
  fi

  # 5) 单独 kill：要求人工核对属主
  if printf '%s' "$cmd" | grep -qE '(^|[[:space:]])kill[[:space:]]'; then
    warn "命令含 kill，执行前必须逐一核对目标进程属主是否为 $ME"
    hit=1
  fi

  # 6) 跨用户目录扫描
  if printf '%s' "$cmd" | grep -qE 'find[[:space:]]+/(home|mnt|)[[:space:]]'; then
    die "禁止跨用户目录扫描/查找：$cmd"
  fi
  if printf '%s' "$cmd" | grep -qE 'grep[[:space:]]+-[a-zA-Z]*r[a-zA-Z]*[[:space:]]+/home[[:space:]]*$'; then
    die "禁止对 /home 整体递归检索：$cmd"
  fi

  # 7) 递归改权限
  if printf '%s' "$cmd" | grep -qE 'chmod[[:space:]]+-[a-zA-Z]*R'; then
    warn "检测到递归 chmod，请确认目标仅在你的目录内"
    hit=1
  fi

  # 8) 命令中出现的路径逐一过围栏
  #    - 含写动作且路径落在禁区 => 直接拒绝
  #    - 只读他人/禁区路径 => 同样拒绝（用户明确要求不需要读他人文件）
  local p rc
  local has_write=0
  if printf '%s' "$cmd" | grep -qE '(^|[;&|[:space:]])(rm|mv|cp|mkdir|touch|tee|truncate|dd|chmod|chown|ln|install)[[:space:]]|>>?[[:space:]]*[^[:space:]&]'; then
    has_write=1
  fi

  for p in $(printf '%s' "$cmd" | grep -oE '/(home|mnt|tmp|var|opt|usr|etc)[A-Za-z0-9_./+-]*'); do
    check_path "$p" >/dev/null 2>&1
    rc=$?
    if [ "$rc" -eq 1 ]; then
      if [ "$has_write" -eq 1 ]; then
        die "命令对禁区路径执行写操作：$p"
      else
        die "命令试图访问禁区/他人路径（不允许读取他人文件）：$p"
      fi
    fi
  done

  if [ "$hit" -eq 1 ]; then
    warn "命令通过扫描，但含需人工确认的动作 —— 执行前请复核"
    return 0
  fi
  ok "命令通过危险模式扫描"
  return 0
}

# ---- 展示规则 --------------------------------------------------------------
show_rules() {
  echo "=== 安全围栏规则（目标主机 ${HOST_ALIAS}，账号 ${ME}）==="
  echo
  echo "档1 可读写："
  printf '   %s\n' "${WRITABLE_PREFIXES[@]}"
  echo
  echo "档2 只读放行（禁止写入）："
  printf '   %s\n' "${READONLY_PREFIXES[@]}"
  echo
  echo "档3 一律拦截："
  printf '   %s\n' "${FORBIDDEN_PREFIXES[@]}"
  echo "   以及所有其他用户目录（/home 下除自己外的一切）"
  echo
  echo "进程规则：只操作属主为 ${ME} 的进程；禁止无属主限定的 pkill/killall"
  echo "破坏性操作：删除 / 杀进程前必须列出目标清单并取得用户确认"
}

# ---- 入口 ------------------------------------------------------------------
case "${1:-show}" in
  path)
    [ $# -ge 2 ] || die "用法：guard.sh path <绝对路径>"
    check_path "$2"
    ;;
  cmd)
    [ $# -ge 2 ] || die "用法：guard.sh cmd <命令字符串>"
    check_cmd "$2"
    ;;
  show|"")
    show_rules
    ;;
  *)
    die "未知子命令：$1（可用：path / cmd / show）"
    ;;
esac
