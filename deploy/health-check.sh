#!/usr/bin/env bash
# 可用性探针 —— 由 systemd --user timer 每 2 分钟调用（见 deploy/systemd/）
#
# 用法:  deploy/health-check.sh
# 环境:  ALERT_WEBHOOK        可选；设置后失败时 POST 通知（不设置则只写日志）
#        ALERT_WEBHOOK_STYLE  可选；feishu（默认 text，即 {"text": "..."}）
#
# 为什么需要它：服务挂了只有 `Restart=always` 会静默拉起，dist 丢失会让 SPA
# 返回 503 —— 这两种情况此前都没有任何出口告警，只能靠用户反馈。
#
# 检查项：
#   1. 应用健康接口（本机 127.0.0.1:8000，绕开 nginx）
#   2. 经 nginx 的公开健康接口（端到端）
#   3. 前端首页（dist 缺失时应用自身返回 503）
# 只在**状态变化**时写一条显著日志并通知，避免每 2 分钟刷屏。
set -uo pipefail
umask 077

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/product-db/api/health}"
PUBLIC_URL="${PUBLIC_URL:-https://product-db.cn/product-db/api/health}"
HOME_URL="${HOME_URL:-https://product-db.cn/product-db/}"
STATE_DIR="${STATE_DIR:-/opt/product-db-backups}"
LOGFILE="$STATE_DIR/health.log"
STATEFILE="$STATE_DIR/health.state"
MAX_LOG=1048576   # 超过 1MB 截断，与备份脚本一致

mkdir -p "$STATE_DIR"

log() {
  local msg
  msg="$(date '+%F %T')  $*"
  printf '%s\n' "$msg" >> "$LOGFILE"
}

if [ -f "$LOGFILE" ] && [ "$(wc -c < "$LOGFILE")" -gt "$MAX_LOG" ]; then
  tail -c 262144 "$LOGFILE" > "$LOGFILE.tmp" && mv "$LOGFILE.tmp" "$LOGFILE"
fi

# --- 探测 ---
problems=()
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL" 2>/dev/null || echo 000)"
[ "$code" = "200" ] || problems+=("应用健康接口 $code（$HEALTH_URL）")

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$PUBLIC_URL" 2>/dev/null || echo 000)"
[ "$code" = "200" ] || problems+=("经 nginx 的健康接口 $code（$PUBLIC_URL）")

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$HOME_URL" 2>/dev/null || echo 000)"
[ "$code" = "200" ] || problems+=("前端首页 $code（$HOME_URL，dist 是否丢失？）")

# --- 状态迁移才记录/告警 ---
prev="$(cat "$STATEFILE" 2>/dev/null || echo unknown)"

notify() {
  local text="$1"
  [ -n "${ALERT_WEBHOOK:-}" ] || return 0
  local payload
  case "${ALERT_WEBHOOK_STYLE:-text}" in
    feishu) payload="$(printf '{"msg_type":"text","content":{"text":"%s"}}' "$text")" ;;
    *)      payload="$(printf '{"text":"%s"}' "$text")" ;;
  esac
  curl -s -o /dev/null --max-time 8 -X POST -H 'Content-Type: application/json' \
       -d "$payload" "$ALERT_WEBHOOK" || log "WARN 告警 webhook 发送失败"
}

if [ "${#problems[@]}" -eq 0 ]; then
  if [ "$prev" != "ok" ]; then
    log "OK 服务已恢复（上一状态: $prev）"
    notify "product-db 已恢复：健康接口与首页均 200"
    printf 'ok\n' > "$STATEFILE"
  fi
  exit 0
fi

msg="product-db 不可用：$(IFS='; '; echo "${problems[*]}")"
if [ "$prev" != "fail" ]; then
  log "FAIL $msg"
  notify "$msg"
  printf 'fail\n' > "$STATEFILE"
else
  log "FAIL（持续）$msg"
fi

# 附上服务状态，便于事后复盘
log "  systemd: $(systemctl is-active "${SERVICE:-product-db}" 2>/dev/null || echo unknown)（${SERVICE:-product-db}）"
exit 1
