#!/usr/bin/env bash
# 安装中文字体（生成产品规格书 PDF 用）
#
# 背景：weasyprint 找不到汉字字形时会**静默丢字**（不报错、不告警），导出的 PDF 里
# 只剩英文与数字 —— 表现就是「规格书内容不完整，而且每份都长得一样」。
# 详见 DEPLOY.md「服务器」一节 与 AGENTS.md R47。
#
# 用法：
#   bash deploy/install-cjk-fonts.sh          # 用户级安装到 ~/.fonts（无需 sudo）
#   sudo bash deploy/install-cjk-fonts.sh     # 系统级安装到 /usr/share/fonts（全部用户可用）
#
# 默认用户级就够：服务的 systemd 单元是 User=tong（systemctl show product-db -p User），
# 以同一用户运行的服务能读到 ~/.fonts。只有把服务改成以别的用户运行时，才需要 sudo 做系统级安装。
#
# 幂等：已有中文字体时直接退出，不会重复下载。
# 装完**不需要重启服务** —— weasyprint 是每次导出时新起的子进程。
set -uo pipefail

PKG="fonts-noto-cjk"
FONT_SUBDIR="opentype/noto"

log() { printf '%s\n' "$*"; }

# 1. 已装过就跳过
existing=$(fc-list :lang=zh 2>/dev/null | wc -l)
if [ "${existing:-0}" -gt 0 ]; then
  log "已存在 ${existing} 个中文字体，无需安装。"
  fc-list :lang=zh | head -3
  exit 0
fi

# 2. 选择安装位置：root → 系统级；普通用户 → 用户级
if [ "$(id -u)" = "0" ]; then
  DEST="/usr/share/fonts/${FONT_SUBDIR}"
  log "以 root 运行 → 系统级安装到 ${DEST}"
else
  DEST="${HOME}/.fonts"
  log "以普通用户 $(id -un) 运行 → 用户级安装到 ${DEST}"
  log "  （前提：product-db 服务以同一用户运行；否则请用 sudo 做系统级安装）"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# 3. 取字体文件：优先复用系统里已有的，其次从 apt 源下载 deb（均无需 root）
FILES=()
if [ -d "/usr/share/fonts/${FONT_SUBDIR}" ]; then
  while IFS= read -r f; do FILES+=("$f"); done < <(find "/usr/share/fonts/${FONT_SUBDIR}" -maxdepth 1 -name '*.ttc')
fi

if [ "${#FILES[@]}" -eq 0 ]; then
  log "从 apt 源下载 ${PKG} …"
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

# 4. 安装并刷新 fontconfig 缓存
mkdir -p "${DEST}"
cp -f "${FILES[@]}" "${DEST}/"
fc-cache -f >/dev/null 2>&1 || true

# 5. 验证
count=$(fc-list :lang=zh 2>/dev/null | wc -l)
log "已复制 ${#FILES[@]} 个字体文件到 ${DEST}"
log "当前中文字体数 = ${count}"
if [ "${count:-0}" -eq 0 ]; then
  log "⚠️ 仍为 0：请确认 fc-list 可用，或检查字体文件是否可读"
  exit 1
fi
log "完成。无需重启服务，直接导出规格书即可。"
