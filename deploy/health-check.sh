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
# 探测频率（**双频**，实测得出）：
#   · 本地接口  每 2 分钟（直接打 127.0.0.1:8000，不经过 nginx、不消耗限流配额）
#   · 公开入口  每 30 分钟（或本地已异常时立即补测）—— 因为公开入口要过全局限流
#     （默认 200/天、60/min），2 分钟一次 = 720 次/天，会先把配额打满，然后持续
#     把 429 误报成「服务不可用」。slowapi 的函数级豁免在中间件模式下无效（见
#     backend/app/main.py 中 health() 的注释），所以只能用降频来规避。
#
# 状态变化时才写日志/通知，持续故障不刷屏。
set -uo pipefail
umask 077

APP_BASE="${APP_BASE:-http://127.0.0.1:8000}"
HEALTH_URL="${HEALTH_URL:-$APP_BASE/product-db/api/health}"
LOCAL_HOME_URL="${LOCAL_HOME_URL:-$APP_BASE/product-db/}"
PUBLIC_URL="${PUBLIC_URL:-https://product-db.cn/product-db/api/health}"
HOME_URL="${HOME_URL:-https://product-db.cn/product-db/}"
PUBLIC_EVERY_MIN="${PUBLIC_EVERY_MIN:-30}"   # 公开入口检查间隔（分钟）
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
# 注意：curl 连接失败时会自己往 stdout 写 "000" 并非 0 退出，所以不能再 `|| echo 000`
# （那会拼成 "000000"），只兜底空值即可
probe() {  # $1=url $2=timeout
  local out
  out="$(curl -s -o /dev/null -w '%{http_code}' --max-time "$2" "$1" 2>/dev/null)"
  printf '%s' "${out:-000}"
}

problems=()
code="$(probe "$HEALTH_URL" 5)"
[ "$code" = "200" ] || problems+=("应用健康接口 $code（$HEALTH_URL）")

code="$(probe "$LOCAL_HOME_URL" 5)"
[ "$code" = "200" ] || problems+=("前端首页(本机) $code（$LOCAL_HOME_URL，dist 是否丢失？）")

# 公开入口：每 PUBLIC_EVERY_MIN 分钟一次；本地已异常时立即补测（判断影响面）
minute=$((10#$(date +%M)))
if [ "${#problems[@]}" -gt 0 ] || [ $((minute % PUBLIC_EVERY_MIN)) -eq 0 ]; then
  code="$(probe "$PUBLIC_URL" 8)"
  [ "$code" = "200" ] || problems+=("经 nginx 的健康接口 $code（$PUBLIC_URL）")

  code="$(probe "$HOME_URL" 8)"
  [ "$code" = "200" ] || problems+=("前端首页 $code（$HOME_URL）")
fi

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
