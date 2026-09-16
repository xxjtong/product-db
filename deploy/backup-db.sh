#!/usr/bin/env bash
# 生产数据库每日快照 —— 由 systemd --user timer 调用（见 deploy/systemd/）
#
# 用法:  deploy/backup-db.sh [保留份数]     默认保留 14 份
# 环境:  DB_PATH / BACKUP_DIR 可覆盖默认路径
#
# 设计要点:
#   1. WAL 模式下必须用 sqlite3 .backup，cp 会丢掉未合并的 WAL 数据
#   2. 先写 .tmp、校验通过再改名 —— 失败时不留下"看起来像快照"的残缺文件
#   3. 快照落成普通 journal 模式并清掉 -wal/-shm 旁文件，产物自包含
#   4. 每轮校验 integrity_check + 行数哨兵，备份不能只看"命令返回 0"
#   5. umask 077 —— 快照一律 600，不依赖事后 chmod
set -euo pipefail
umask 077

DB="${DB_PATH:-/opt/product-db/backend/product_db.db}"
DEST="${BACKUP_DIR:-/opt/product-db-backups/db}"
KEEP="${1:-14}"
LOGFILE="$DEST/backup.log"
PATTERN='product_db.db.bak.[0-9]*'   # 只认真正的时间戳快照，排除 .tmp/-wal/-shm

log() {
  local msg
  msg="$(date '+%F %T')  $*"
  printf '%s\n' "$msg"
  printf '%s\n' "$msg" >> "$LOGFILE"
}

# --- 前置检查 ---
[ -f "$DB" ]                  || { log "ERROR 数据库不存在: $DB"; exit 1; }
command -v sqlite3 >/dev/null || { log "ERROR 缺少 sqlite3"; exit 1; }
mkdir -p "$DEST"

# 日志自限，超过 1MB 就截断（只保留最近一次运行前的部分）
if [ -f "$LOGFILE" ] && [ "$(wc -c < "$LOGFILE")" -gt 1048576 ]; then
  tail -c 262144 "$LOGFILE" > "$LOGFILE.tmp" && mv "$LOGFILE.tmp" "$LOGFILE"
fi

TS="$(date +%Y%m%d_%H%M%S)"
OUT="$DEST/product_db.db.bak.$TS"
TMP="$OUT.tmp"

# --- 快照 ---
log "开始快照 $DB → $(basename "$OUT")"
sqlite3 "$DB" ".backup $TMP"

# .backup 会让副本继承源库的 WAL 模式，关闭后可能留下空的 -wal/-shm 旁文件。
# 转成普通 journal 模式让产物自包含，再兜底清掉旁文件。
sqlite3 "$TMP" 'PRAGMA journal_mode=DELETE;' >/dev/null
rm -f "$TMP-wal" "$TMP-shm"

# --- 校验（任一项不过就不留文件）---
integrity="$(sqlite3 "$TMP" 'PRAGMA integrity_check;')"
if [ "$integrity" != "ok" ]; then
  log "ERROR integrity_check 未通过: $integrity"
  rm -f "$TMP" "$TMP-wal" "$TMP-shm"
  exit 1
fi

for spec in "products:1" "users:1" "ai_conversations:0"; do
  tbl="${spec%%:*}"
  min="${spec##*:}"
  n="$(sqlite3 "$TMP" "SELECT COUNT(*) FROM $tbl;" 2>/dev/null || echo -1)"
  if [ "$n" -lt "$min" ]; then
    log "ERROR 表 $tbl 行数异常: $n（期望 >= $min）"
    rm -f "$TMP" "$TMP-wal" "$TMP-shm"
    exit 1
  fi
  log "  校验 $tbl = $n"
done

chmod 600 "$TMP"
mv "$TMP" "$OUT"
log "快照完成: $(basename "$OUT")  $(du -h "$OUT" | cut -f1)"

# --- 保留策略：只留最新 KEEP 份 ---
ls -1t "$DEST"/$PATTERN 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -f -- "$old" && log "  清理旧快照 $(basename "$old")"
done

log "当前快照份数: $(find "$DEST" -maxdepth 1 -name "$PATTERN" | wc -l)  保留上限: $KEEP"
log "完成"
