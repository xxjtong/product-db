#!/usr/bin/env bash
# 生产每日备份 —— 由 systemd --user timer 调用（见 deploy/systemd/）
#   ① 数据库一致性快照（sqlite3 .backup）
#   ② uploads 上传目录的**硬链接增量快照**
#
# 用法:  deploy/backup-db.sh [保留份数]     默认保留 14 份（db 与 uploads 同用这个值）
# 环境:  DB_PATH / BACKUP_DIR / UPLOADS_PATH / UPLOADS_BACKUP_DIR 可覆盖默认路径
#
# 设计要点:
#   1. WAL 模式下必须用 sqlite3 .backup，cp 会丢掉未合并的 WAL 数据
#   2. 先写 .tmp、校验通过再改名 —— 失败时不留下"看起来像快照"的残缺文件
#   3. 快照落成普通 journal 模式并清掉 -wal/-shm 旁文件，产物自包含
#   4. 每轮校验 integrity_check + 行数哨兵，备份不能只看"命令返回 0"
#   5. umask 077 —— 快照一律 600，不依赖事后 chmod
#   6. uploads 用「每日一份完整快照 + --link-dest 硬链接」而不是单一 --delete 镜像：
#      镜像方式下源里删掉的文件在备份里也没了（等于没有历史可回），2026-06 的
#      文件误删事故正是这种情形；硬链接快照让每份都完整可恢复，未变文件又不占空间
set -euo pipefail
umask 077

DB="${DB_PATH:-/opt/product-db/backend/product_db.db}"
DEST="${BACKUP_DIR:-/opt/product-db-backups/db}"
UPLOADS="${UPLOADS_PATH:-/opt/product-db/backend/app/uploads}"
UP_DEST="${UPLOADS_BACKUP_DIR:-/opt/product-db-backups/uploads-snapshots}"
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

# --- uploads 快照（硬链接增量；失败不影响已完成的 db 快照，但本次以非 0 退出）---
up_rc=0
if [ ! -d "$UPLOADS" ]; then
  log "跳过 uploads：目录不存在 ($UPLOADS)"
elif ! command -v rsync >/dev/null; then
  log "ERROR 跳过 uploads：缺少 rsync"
  up_rc=1
else
  mkdir -p "$UP_DEST"
  UP_OUT="$UP_DEST/$TS"
  # --link-dest 指向上一个快照：未变的文件在新快照里是硬链接，几乎不占额外空间，
  # 而每份快照仍是**完整镜像** ——「今天误删了文件」可以从昨天那份捞回来。
  # （旧的手动命令是单目录 --delete 镜像，源里删掉的在备份里也没了，等于没有历史。）
  PREV="$(ls -1dt "$UP_DEST"/*/ 2>/dev/null | head -1 || true)"
  LINK_OPT=""
  [ -n "$PREV" ] && LINK_OPT="--link-dest=$PREV"
  if rsync -a --delete $LINK_OPT "$UPLOADS/" "$UP_OUT/" >>"$LOGFILE" 2>&1; then
    log "uploads 快照完成: $(basename "$UP_OUT")  文件 $(find "$UP_OUT" -type f | wc -l) 个"
  else
    log "ERROR uploads 快照失败（rsync 非 0）；db 快照已完成，本次以失败退出"
    rm -rf -- "$UP_OUT"
    up_rc=1
  fi

  # 保留策略：只留最新 KEEP 份快照目录
  { ls -1dt "$UP_DEST"/*/ 2>/dev/null || true; } | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -rf -- "$old" && log "  清理旧 uploads 快照 $(basename "$old")"
  done
  log "uploads 快照份数: $(find "$UP_DEST" -maxdepth 1 -mindepth 1 -type d | wc -l)  保留上限: $KEEP"
fi

log "完成"
exit "$up_rc"
