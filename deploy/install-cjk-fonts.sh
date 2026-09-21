#!/usr/bin/env bash
# 为产品规格书 PDF 安装中文字体
#
# 背景：weasyprint 找不到汉字字形时会**静默丢字**（不报错、不告警），导出的 PDF 里
# 只剩英文与数字 —— 表现就是「规格书内容不完整，而且每份都长得一样」。
# 详见 DEPLOY.md「服务器」一节 与 AGENTS.md R47。
#
# 用法：
#   bash deploy/install-cjk-fonts.sh          # 用户级装到 ~/.fonts（无需 sudo）
#   sudo bash deploy/install-cjk-fonts.sh     # 系统级装到 /usr/share/fonts（所有用户可用）
#
# 说明：
# - 服务以 tong 用户运行，用户级已经够用；系统级是让所有用户/其它服务都能用。
# - 幂等：判断依据是**目标目录**里有没有字体，而不是 fc-list 的全局计数 ——
#   否则「已装过用户级」会让「系统级安装」被误判为不需要装。
# - 装完**不需要重启服务**：weasyprint 是每次导出时新起的子进程。
set -uo pipefail

PKG="fonts-noto-cjk"
FONT_SUBDIR="opentype/noto"
SYS_DIR="/usr/share/fonts/${FONT_SUBDIR}"

log() { printf '%s\n' "$*"; }
count_zh() { fc-list :lang=zh 2>/dev/null | wc -l; }

# 1. 确定安装位置
if [ "$(id -u)" = "0" ]; then
  DEST="${SYS_DIR}"
  log "root 运行 → 系统级安装到 ${DEST}"
else
  DEST="${HOME}/.fonts"
  log "普通用户 $(id -un) 运行 → 用户级安装到 ${DEST}"
fi

# 2. 幂等检查（按目标目录）
if compgen -G "${DEST}/*.ttc" >/dev/null 2>&1; then
  log "${DEST} 已有字体，无需安装。当前中文字体数 = $(count_zh)"
  exit 0
fi
if [ "${DEST}" != "${SYS_DIR}" ] && compgen -G "${SYS_DIR}/*.ttc" >/dev/null 2>&1; then
  log "系统目录 ${SYS_DIR} 已有字体，无需再装用户级。当前中文字体数 = $(count_zh)"
  exit 0
fi

# 3. 系统级安装优先走发行版包管理（规范，且会自动刷新 fontconfig 缓存）
if [ "${DEST}" = "${SYS_DIR}" ] && command -v apt-get >/dev/null 2>&1; then
  if apt-get install -y "${PKG}" >/dev/null 2>&1; then
    log "已通过 apt-get install ${PKG} 完成系统级安装，当前中文字体数 = $(count_zh)"
    exit 0
  fi
  log "apt 安装未成功 → 回退为直接复制字体文件"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# 4. 找字体文件：优先复用本机已有的 .ttc，都没有才从 apt 源下载 deb（均无需 root）
FILES=()
for dir in "${SYS_DIR}" "${HOME}/.fonts" /home/*/.fonts /root/.fonts; do
  [ -d "${dir}" ] || continue
  while IFS= read -r f; do FILES+=("$f"); done < <(find "${dir}" -maxdepth 1 -name '*.ttc' 2>/dev/null)
  [ "${#FILES[@]}" -gt 0 ] && break
done

if [ "${#FILES[@]}" -eq 0 ]; then
  log "本机没有现成字体，从 apt 源下载 ${PKG} …"
  if ! (cd "${WORK}" && apt-get download "${PKG}" >/dev/null 2>&1); then
    log "下载失败：请确认 apt 源可用，或手动把 .ttc 字体文件放进 ${DEST}"
    exit 1
  fi
  deb="$(find "${WORK}" -maxdepth 1 -name "${PKG}_*.deb" | head -1)"
  if [ -z "${deb}" ]; then
    log "未找到下载下来的 deb 包"
    exit 1
  fi
  dpkg-deb -x "${deb}" "${WORK}/x"
  while IFS= read -r f; do FILES+=("$f"); done < <(find "${WORK}/x" -name '*.ttc')
fi

if [ "${#FILES[@]}" -eq 0 ]; then
  log "没找到任何 .ttc 字体文件，安装中止"
  exit 1
fi

# 5. 安装并刷新 fontconfig 缓存
mkdir -p "${DEST}"
cp -f "${FILES[@]}" "${DEST}/"
fc-cache -f >/dev/null 2>&1 || true

# 6. 验证
c=$(count_zh)
log "已复制 ${#FILES[@]} 个字体文件到 ${DEST}，当前中文字体数 = ${c}"
if [ "${c:-0}" -eq 0 ]; then
  log "⚠️ 仍为 0：请确认 fc-list 可用、字体文件可读"
  exit 1
fi
log "完成。无需重启服务，直接导出规格书即可。"
