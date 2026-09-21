#!/usr/bin/env bash
# 安装/更新 product-db 的 systemd 单元（需要 root —— 单元文件属 root:root）
#
#   sudo bash deploy/install-systemd-unit.sh
#
# 幂等：内容没变就只做校验不重启；有变化才 daemon-reload + 重启，
# 并先备份旧单元到 /opt/product-db-backups/systemd/，重启失败自动回滚。
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_DIR}/deploy/systemd/product-db.service"
DEST="/etc/systemd/system/product-db.service"
BACKUP_DIR="/opt/product-db-backups/systemd"
SERVICE="product-db"
HEALTH_URL="http://127.0.0.1:8000/product-db/api/health"

log() { printf '%s\n' "$*"; }

if [ "$(id -u)" != "0" ]; then
  log "需要 root：sudo bash $0"
  exit 1
fi

[ -f "${SRC}" ] || { log "找不到源文件：${SRC}"; exit 1; }

# 应用实际使用的数据库路径 —— 加固项（尤其 ProtectHome）必须与它兼容，否则会出现
# 「服务起来了、/api/health 也 200，但所有查库接口 500」。R51 就踩过：库其实在 /home 下。
if [ -x "${REPO_DIR}/backend/venv/bin/python" ]; then
  db_url="$( cd "${REPO_DIR}/backend" && venv/bin/python -c \
    'from app.config import settings; print(settings.DATABASE_URL)' 2>/dev/null )" || db_url=""
  if [ -n "${db_url}" ]; then
    log "应用实际使用的数据库：${db_url}"
    case "${db_url}" in
      */home/*|*/root/*)
        if grep -qE '^[[:space:]]*ProtectHome[[:space:]]*=[[:space:]]*(true|yes)' "${SRC}"; then
          log "❌ 冲突：数据库在 /home 或 /root 下，而单元启用了 ProtectHome=true"
          log "   （后果：服务能启动但查库全部 500 —— unable to open database file）"
          log "   处理：注释掉单元里的 ProtectHome，或先把数据库移到 /opt。已中止。"
          exit 1
        fi
        log "  注意：库位于 /home 或 /root 下，单元中不可启用 ProtectHome"
        ;;
    esac
  fi
fi

# 0. 语法校验（不通过就别动生产）
# 注意：verify 会顺带报告 /etc/systemd/system 下**其它** unit 的既有问题
# （实测本机有 tat_agent、frps 两条无关警告），所以只认与本单元相关的报错
if command -v systemd-analyze >/dev/null 2>&1; then
  verify_out="$(systemd-analyze verify "${SRC}" 2>&1 || true)"
  if printf '%s' "${verify_out}" | grep -qi 'product-db\.service.*error'; then
    printf '%s\n' "${verify_out}"
    log "unit 语法校验未通过，已中止"
    exit 1
  fi
  log "unit 语法校验通过"
fi

# 1. 内容没变就直接返回（幂等，避免无谓重启）
if [ -f "${DEST}" ] && cmp -s "${SRC}" "${DEST}"; then
  log "单元内容与 ${DEST} 一致，无需更新。"
  log "当前加固项："
  systemctl show "${SERVICE}" -p NoNewPrivileges -p ProtectSystem -p PrivateTmp -p ProtectHome
  exit 0
fi

# 2. 备份现有单元
mkdir -p "${BACKUP_DIR}"
if [ -f "${DEST}" ]; then
  stamp="$(date +%Y%m%d_%H%M%S)"
  cp -p "${DEST}" "${BACKUP_DIR}/product-db.service.${stamp}"
  log "已备份旧单元 → ${BACKUP_DIR}/product-db.service.${stamp}"
fi

# 3. 安装 + 重载 + 重启
install -m 0644 "${SRC}" "${DEST}"
systemctl daemon-reload
log "已安装并 daemon-reload，正在重启 ${SERVICE} …"
systemctl restart "${SERVICE}"

# 4. 就绪验证（最多等 20 秒）
ok=""
for _ in $(seq 1 20); do
  sleep 1
  if curl -fsS -o /dev/null --max-time 3 "${HEALTH_URL}"; then ok=1; break; fi
done

if [ -z "${ok}" ]; then
  log "❌ 重启后健康检查未通过，开始回滚 …"
  newest="$(ls -1t "${BACKUP_DIR}"/product-db.service.* 2>/dev/null | head -1)"
  if [ -n "${newest}" ]; then
    install -m 0644 "${newest}" "${DEST}"
    systemctl daemon-reload
    systemctl restart "${SERVICE}"
    log "已回滚到 ${newest}，状态：$(systemctl is-active "${SERVICE}")"
  else
    log "没有可用备份，需人工介入"
  fi
  exit 1
fi

log "✅ 服务已就绪：${HEALTH_URL}"
log "生效的加固项："
systemctl show "${SERVICE}" \
  -p NoNewPrivileges -p ProtectSystem -p ProtectHome -p PrivateTmp -p PrivateDevices \
  -p ProtectKernelTunables -p ProtectKernelModules -p ProtectControlGroups \
  -p RestrictSUIDSGID -p LockPersonality -p RestrictAddressFamilies \
  -p StartLimitIntervalUSec -p StartLimitBurst -p TimeoutStopUSec
log "提示：加固后建议实测一次「导出规格书（PDF）」与「AI 对话」，确认子进程与外部 API 正常。"
