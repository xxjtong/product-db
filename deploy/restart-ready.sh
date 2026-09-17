#!/usr/bin/env bash
# 重启 product-db 并**等待就绪**（就绪门控）—— 替代裸 `sudo systemctl restart product-db`
#
# 用法:  deploy/restart-ready.sh
# 环境:  HEALTH_URL（应用自带健康接口）、PUBLIC_URL（经 nginx 的入口）、TIMEOUT 秒
#
# 为什么需要它：重启期间 uvicorn 不监听，nginx 直接对外 502（实测 5-8s），
# 而原部署流程 restart 后只手工 curl 一下，失败与否没有判据、也没有回滚提示。
#
# 本脚本做三件事：
#   1. 记录重启前的 git revision（失败时给出回滚命令）
#   2. restart 后轮询本地健康接口直到 200（应用已就绪）
#   3. 再验一次经 nginx 的公开入口与前端首页（dist 丢失会让 SPA 返回 503）
# 任一环节超时/失败 → 打印 journalctl 片段并以非 0 退出（**不自动回滚**）
set -uo pipefail

SERVICE="${SERVICE:-product-db}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/product-db/api/health}"
PUBLIC_URL="${PUBLIC_URL:-https://product-db.cn/product-db/api/health}"
HOME_URL="${HOME_URL:-https://product-db.cn/product-db/}"
TIMEOUT="${TIMEOUT:-30}"
REPO="${REPO:-/opt/product-db}"

PREV_REV="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"

echo "== 重启 $SERVICE（当前 revision: $PREV_REV）"
sudo systemctl restart "$SERVICE" || { echo "ERROR: restart 命令本身失败"; exit 1; }

start=$(date +%s)
ready=0
while [ $(( $(date +%s) - start )) -lt "$TIMEOUT" ]; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$HEALTH_URL" 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then ready=1; break; fi
  sleep 0.5
done

elapsed=$(( $(date +%s) - start ))
if [ "$ready" != "1" ]; then
  echo "ERROR: 等待就绪超时（${elapsed}s，最后一次 HTTP $code）—— 服务可能没起来"
  echo "--- journalctl -u $SERVICE（最近 20 行）---"
  journalctl -u "$SERVICE" -n 20 --no-pager 2>/dev/null | tail -20
  echo "--- 回滚参考 ---"
  echo "  cd $REPO && git checkout $PREV_REV && deploy/restart-ready.sh"
  exit 1
fi
echo "== 应用已就绪（${elapsed}s）: $HEALTH_URL → 200"

fail=0
pub="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$PUBLIC_URL" 2>/dev/null || echo 000)"
[ "$pub" = "200" ] || { echo "ERROR: 经 nginx 的健康检查返回 $pub"; fail=1; }
home="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HOME_URL" 2>/dev/null || echo 000)"
[ "$home" = "200" ] || { echo "ERROR: 前端首页返回 $home（dist 是否已部署？）"; fail=1; }

if [ "$fail" != "0" ]; then
  echo "--- 回滚参考: cd $REPO && git checkout $PREV_REV && deploy/restart-ready.sh"
  exit 1
fi

echo "== 对外验证通过：/api/health 200、首页 200"
exit 0
