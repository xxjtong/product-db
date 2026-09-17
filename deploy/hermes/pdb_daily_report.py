#!/usr/bin/env python3
"""product-db 每日运行报告 (v2)

把「使用情况」与「整体运行情况」汇总成一条文本，供 Hermes cron（no_agent 模式）
直接投递到飞书。**正常时只输出三行摘要，有告警时才输出完整报告**，
这样群里不会每天刷一大段，但真出问题时信息量足够定位。

数据源（全部只需 tong 权限，无需 sudo）：
  · /opt/product-db/backend/product_db.db —— 登录 / AI / 下载 / 业务增量
  · journalctl -u product-db              —— 请求日志：活跃时长、5xx、错误、重启
  · /opt/product-db-backups/              —— 快照新鲜度、探针 health.log/state
  · /proc/meminfo、/proc/uptime、shutil.disk_usage —— 内存 / 负载 / 磁盘

用法：
  pdb_daily_report.py [--date YYYY-MM-DD] [--full]
    --date  报告哪一天（默认今天；21:00 运行时当天数据已完整）
    --full  强制输出完整报告（人工排查用）

部署：正文在仓库 deploy/hermes/pdb_daily_report.py，
      ~/.hermes/scripts/pdb_daily_report.py 是指向它的软链接（随 git pull 更新）。
"""
import os
import re
import sqlite3
import subprocess
import sys
import time
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from shutil import disk_usage

DB = "/opt/product-db/backend/product_db.db"
BACKUP_DIR = "/opt/product-db-backups"
DB_BACKUP_DIR = os.path.join(BACKUP_DIR, "db")
UPLOADS_DIR = "/opt/product-db/backend/app/uploads"
PROBE_PATH = "/product-db/api/health"
# 本机探针（每 2 分钟）与公开探针（每 30 分钟）都出自这两个地址，
# 不能算进「用户活跃度」，否则探针会把活跃时长刷成 24 小时
SELF_IPS = {"127.0.0.1", "::1", "124.221.178.161"}

# 告警阈值：命中任意一条就输出完整报告，并在开头列出
TH = {
    "disk_used_pct": 85,     # 根分区使用率（%）
    "mem_avail_mb": 200,     # 可用内存（MB）
    "backup_max_age_h": 26,  # 最新快照年龄（小时）—— 备份每日 03:30 跑
    "http_5xx": 5,           # 当日 5xx 请求数
    "error_lines": 20,       # 当日 ERROR 级日志行数
}
# 快照份数不设阈值：保留策略是攒到 14 份，刚上线那几天必然不够，只报数不告警
BURST_PER_MIN = 10      # 单账号一分钟内登录次数达到此值就标注「疑似自动化」
MAX_ACCOUNT_LINES = 5   # 极简模式下最多列几个账号，其余折成一行

ACCESS_RE = re.compile(
    r'^(\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2}).*?INFO:\s+(\d+\.\d+\.\d+\.\d+):\d+ - '
    r'"([A-Z]+) (\S+) HTTP/[\d.]+" (\d{3})',
    re.M,
)
SNAP_RE = re.compile(r'^product_db\.db\.bak\.\d+_\d+$')


def utc_bounds(day):
    """本地日 → 数据库里的 UTC 时间边界 [start, end)

    DB 里 created_at 存的是 naive UTC（实测：UTC 03:25 = 本地 11:25），
    直接按 date(created_at) 切分会把本地日错位成 08:00→次日 08:00。
    """
    start = datetime.combine(day, dtime.min).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def to_local(ts):
    """naive UTC 字符串 → 本地 HH:MM"""
    try:
        return (datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=timezone.utc).astimezone().strftime("%H:%M"))
    except (TypeError, ValueError):
        return str(ts)[11:16]


def run(cmd, timeout=120):
    """执行命令返回 stdout；异常/超时返回 None（返回码不视为失败，systemctl 非 0 很常见）"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return None


def human(n):
    """字节数转人类可读"""
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return f"{n:.0f}{unit}" if unit in ("B", "K") else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}G"


def dir_size(path):
    """递归统计目录大小与文件数"""
    total = files = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(root, name))
                files += 1
            except OSError:
                pass
    return total, files


def journal_of(day):
    """取某天 product-db 的 journal 全文（journald 只保留约 1-2 周）"""
    return run([
        "journalctl", "-u", "product-db",
        "--since", f"{day} 00:00:00", "--until", f"{day} 23:59:59", "--no-pager",
    ]) or ""


def parse_requests(text):
    """解析 uvicorn 访问行 → (总数, 5xx, 4xx, 探针数, {ip: [HH:MM:SS...]})

    用户活跃度只统计非探针路径、非本机来源的请求。
    """
    total = s5xx = s4xx = probe = 0
    by_ip = defaultdict(list)
    for m in ACCESS_RE.finditer(text):
        ts, ip, _method, path, status = m.groups()
        code = int(status)
        total += 1
        if code >= 500:
            s5xx += 1
        elif code >= 400:
            s4xx += 1
        if path.startswith(PROBE_PATH):
            probe += 1
            continue
        if ip in SELF_IPS:
            continue
        by_ip[ip].append(ts[-8:])
    return total, s5xx, s4xx, probe, by_ip


def local_minute(ts):
    """naive UTC 字符串 → 本地时间当天的第几分钟（0-1439）"""
    try:
        dt = (datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
              .replace(tzinfo=timezone.utc).astimezone())
        return dt.hour * 60 + dt.minute
    except (TypeError, ValueError):
        return None


def minute_of(t):
    """'HH:MM:SS' → 当天第几分钟"""
    return int(t[0:2]) * 60 + int(t[3:5])


def span_range(times):
    """首末请求时间 → 半开区间 (起始分钟, 结束分钟+1)

    右端 +1 是为了让「一分钟内打了 8 个请求」的跨度算 1 分钟而不是 0，
    否则会出现「跨度 0 分钟（有请求 2 分钟）」这种自相矛盾的输出。
    """
    times = sorted(times)
    return minute_of(times[0]), minute_of(times[-1]) + 1


def merge_minutes(intervals):
    """合并重叠区间后求总时长（分钟）

    同一账号常同时用两个 IP（家里 + 公司），逐 IP 相加会把并行时间算两遍。
    """
    total = 0
    cur_s = cur_e = None
    for s, e in sorted(intervals):
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    if cur_s is not None:
        total += cur_e - cur_s
    return total


def account_lines(acct_view, limit=MAX_ACCOUNT_LINES):
    """每个账号一行：登录次数（峰值高时标注疑似自动化）+ 活跃时长 + IP"""
    lines = []
    for a in acct_view[:limit]:
        if a["cnt"]:
            seg = f"👥 {a['name']}: 登录 {a['cnt']} 次"
            if a["peak"] >= BURST_PER_MIN:
                seg += f"（峰值 {a['peak']} 次/分，疑似自动化测试）"
            seg += f" · 活跃跨度 {a['minutes']} 分钟 · 有请求 {a['busy']} 分钟"
            if len(a["ips"]) > 1:
                seg += f" · {len(a['ips'])} 个 IP"
            elif a["ips"]:
                seg += f" · IP {a['ips'][0][0]}"
        else:
            # 有访问但没有登录记录（爬虫/云监控/匿名）
            seg = (f"👥 未识别（无登录记录的访问）: {a['reqs']} 请求"
                   f" · 活跃跨度 {a['minutes']} 分钟 · 有请求 {a['busy']} 分钟"
                   f" · {len(a['ips'])} 个 IP")
        lines.append(seg)
    if len(acct_view) > limit:
        lines.append(f"👥 …等共 {len(acct_view)} 个账号（其余省略）")
    return lines


def system_status(day, journal, req_total, s5xx, s4xx, probe):
    """采集整体运行情况；返回 (完整报告行, 告警列表, 极简摘要片段)"""
    out, alerts, compact = [], [], []

    # ── 服务 ──
    def state(unit):
        return (run(["systemctl", "is-active", unit], timeout=10) or "").strip() or "unknown"

    app_state, nginx_state = state("product-db"), state("nginx")
    if app_state != "active":
        alerts.append(f"服务 product-db 当前是 {app_state}")
    if nginx_state != "active":
        alerts.append(f"服务 nginx 当前是 {nginx_state}")
    # 当日启动次数：journal 里并没有 systemd 的 Starting/Started 行，
    # 只能数 uvicorn 每个进程启动时打的那一次「Started server process」
    starts = len(re.findall(r'Started server process', journal))
    # 被 systemd 自动重启（Restart=always）才是崩溃信号；人工 systemctl restart 不计入
    raw_nr = (run(["systemctl", "show", "product-db", "-p", "NRestarts", "--value"],
                  timeout=10) or "").strip()
    auto_restarts = int(raw_nr) if raw_nr.isdigit() else 0
    if auto_restarts:
        alerts.append(f"服务被 systemd 自动重启 {auto_restarts} 次（非人工操作，怀疑崩溃）")
    out.append(f"  服务: product-db {app_state} / nginx {nginx_state}"
               f"｜当日启动 {starts} 次（含部署重启）｜自动重启 {auto_restarts} 次")
    compact.append(f"服务 {app_state}" + (f"（当日启动 {starts} 次）" if starts else ""))

    # ── 请求与错误 ──
    # 应用自身的日志是 `| ERROR | logger | msg`；uvicorn 的是 `ERROR:    ...`，
    # 后者前面带 journal 前缀，不能用 ^ 锚定
    err_lines = (len(re.findall(r'\|\s*(?:ERROR|CRITICAL)\s*\|', journal))
                 + len(re.findall(r'ERROR:', journal)))
    tracebacks = journal.count("Traceback (most recent call last)")
    if s5xx >= TH["http_5xx"]:
        alerts.append(f"当日 5xx 请求 {s5xx} 次（阈值 {TH['http_5xx']}）")
    if err_lines >= TH["error_lines"]:
        alerts.append(f"当日 ERROR 日志 {err_lines} 行（阈值 {TH['error_lines']}）")
    out.append(f"  请求: {req_total:,}（4xx {s4xx} / 5xx {s5xx}）｜探针 {probe:,} 次"
               f"｜ERROR 日志 {err_lines} 行 / Traceback {tracebacks} 次")
    compact.append(f"请求 {req_total:,}（5xx {s5xx}）")
    if err_lines or tracebacks:
        compact.append(f"错误 {err_lines}")

    # ── 探针 ──
    state_file = os.path.join(BACKUP_DIR, "health.state")
    try:
        with open(state_file) as f:
            probe_state = f.read().strip() or "unknown"
    except OSError:
        probe_state = "unknown"
    fails_today = 0
    try:
        with open(os.path.join(BACKUP_DIR, "health.log")) as f:
            fails_today = sum(1 for ln in f if ln.startswith(day) and " FAIL" in ln)
    except OSError:
        pass
    if probe_state not in ("ok", "unknown"):
        alerts.append(f"可用性探针当前状态 {probe_state}（health.log 当日 FAIL {fails_today} 次）")
    elif fails_today:
        alerts.append(f"可用性探针当日 FAIL {fails_today} 次（现已恢复）")
    out.append(f"  探针: {probe_state}｜当日 FAIL {fails_today} 次")
    compact.append(f"探针 {probe_state}")

    # ── 资源 ──
    du = disk_usage("/")
    disk_pct = round(du.used * 100.0 / du.total)
    if disk_pct >= TH["disk_used_pct"]:
        alerts.append(f"根分区使用率 {disk_pct}%（阈值 {TH['disk_used_pct']}%）")
    mem = {}
    try:
        with open("/proc/meminfo") as f:
            for ln in f:
                k, _, v = ln.partition(":")
                mem[k] = int(v.split()[0])
    except (OSError, ValueError):
        pass
    mem_avail_mb = mem.get("MemAvailable", 0) // 1024
    if mem and mem_avail_mb < TH["mem_avail_mb"]:
        alerts.append(f"可用内存仅 {mem_avail_mb}MB（阈值 {TH['mem_avail_mb']}MB）")
    load1 = os.getloadavg()[0]
    try:
        with open("/proc/uptime") as f:
            up_days = float(f.read().split()[0]) / 86400
    except (OSError, ValueError):
        up_days = 0
    out.append(f"  资源: 磁盘 {disk_pct}%（{human(du.used)}/{human(du.total)}）"
               f"｜内存可用 {mem_avail_mb}MB｜负载 {load1:.2f}｜已运行 {up_days:.0f} 天")
    compact.append(f"磁盘 {disk_pct}%")
    compact.append(f"内存 {mem_avail_mb}M")

    # ── 备份 ──
    snaps = []
    try:
        for name in os.listdir(DB_BACKUP_DIR):
            if SNAP_RE.match(name):
                p = os.path.join(DB_BACKUP_DIR, name)
                snaps.append((os.path.getmtime(p), os.path.getsize(p)))
    except OSError:
        pass
    if not snaps:
        alerts.append("没有任何数据库快照")
        out.append("  备份: ⚠️ 无快照")
    else:
        newest, size = max(snaps)
        age_h = (time.time() - newest) / 3600.0
        if age_h > TH["backup_max_age_h"]:
            alerts.append(f"最新快照已 {age_h:.1f} 小时未更新（阈值 {TH['backup_max_age_h']}h）")
        out.append(f"  备份: 最新 {datetime.fromtimestamp(newest).strftime('%m-%d %H:%M')}"
                   f"（{age_h:.0f}h 前）｜{len(snaps)} 份 / {human(size)}")
        compact.append(f"备份 {age_h:.0f}h 前（{len(snaps)} 份）")

    # ── 数据体量 ──
    try:
        db_size = os.path.getsize(DB)
        wal_size = os.path.getsize(DB + "-wal")
    except OSError:
        db_size = wal_size = 0
    up_size, up_files = dir_size(UPLOADS_DIR)
    out.append(f"  数据: DB {human(db_size)}（WAL {human(wal_size)}）"
               f"｜上传目录 {human(up_size)} / {up_files} 文件")

    return out, alerts, compact


def main():
    target = date.today()
    force_full = "--full" in sys.argv
    if len(sys.argv) > 2 and sys.argv[1] == "--date":
        target = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
    day = target.isoformat()
    prev_day = (target - timedelta(days=1)).isoformat()
    day_from, day_to = utc_bounds(target)          # 本地日 → UTC 边界
    prev_from, prev_to = utc_bounds(target - timedelta(days=1))

    if not os.path.exists(DB):
        print(f"❌ product-db 日报生成失败：数据库不存在 {DB}")
        return 1

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    journal = journal_of(day)
    req_total, s5xx, s4xx, probe, act_by_ip = parse_requests(journal)

    # ── 1. 登录 ──
    c.execute("""
        SELECT u.username, u.role, COUNT(*) AS cnt,
               MIN(l.created_at) AS first_login, MAX(l.created_at) AS last_login,
               GROUP_CONCAT(DISTINCT l.ip_address) AS ips
        FROM login_logs l JOIN users u ON u.id = l.user_id
        WHERE l.created_at >= ? AND l.created_at < ? AND l.success = 1
        GROUP BY u.username ORDER BY cnt DESC
    """, (day_from, day_to))
    logins = c.fetchall()
    failed = c.execute(
        "SELECT COUNT(*) FROM login_logs WHERE created_at >= ? AND created_at < ? AND success=0",
        (day_from, day_to)).fetchone()[0]

    # ── 2. 活跃时长：请求按「该 IP 上此前最近一次登录的账号」归属 ──
    # 同一个出口 IP 常被多个账号用过（tong/admin 就是同一台机器），
    # 简单的 IP→账号 一对一映射会把一个人的活跃全算给另一个人。
    # 这里对每个请求找「该 IP 上时间不晚于它的最近一次成功登录」，之前没有
    # 任何登录的请求归入「未识别」。
    ip_logins = defaultdict(list)   # ip -> [(本地分钟, username)]，按时间升序
    c.execute("""
        SELECT l.ip_address AS ip, u.username AS username, l.created_at AS ts
        FROM login_logs l JOIN users u ON u.id = l.user_id
        WHERE l.created_at >= ? AND l.created_at < ? AND l.success = 1
        ORDER BY l.created_at
    """, (day_from, day_to))
    for row in c.fetchall():
        m = local_minute(row["ts"])
        if m is not None:
            ip_logins[row["ip"]].append((m, row["username"]))

    # 登录事件的分钟峰值：自动化测试会在一分钟内打几十次，
    # 标出来免得把「181 次登录」误读成异常
    peaks = {}
    c.execute("""
        SELECT u.username AS username, substr(l.created_at, 12, 5) AS minute, COUNT(*) AS n
        FROM login_logs l JOIN users u ON u.id = l.user_id
        WHERE l.created_at >= ? AND l.created_at < ? AND l.success = 1
        GROUP BY u.username, minute
    """, (day_from, day_to))
    for row in c.fetchall():
        peaks[row["username"]] = max(peaks.get(row["username"], 0), row["n"])

    buckets = defaultdict(lambda: defaultdict(list))   # 账号 -> IP -> [HH:MM:SS]
    for ip, times in act_by_ip.items():
        logs = ip_logins.get(ip)
        if not logs:
            buckets["未识别"][ip].extend(times)        # 无登录记录的访问
            continue
        log_minutes = [m for m, _name in logs]
        for t in times:
            i = bisect_right(log_minutes, minute_of(t)) - 1
            owner = logs[i][1] if i >= 0 else "未识别"
            buckets[owner][ip].append(t)

    acct = {}
    for r in logins:
        acct[r["username"]] = {"name": r["username"], "role": r["role"],
                               "cnt": r["cnt"], "peak": peaks.get(r["username"], 0),
                               "first": r["first_login"], "last": r["last_login"],
                               "reqs": 0, "minutes": 0, "busy": 0, "minset": set(),
                               "ips": []}
    for name, per_ip in buckets.items():
        a = acct.setdefault(name, {"name": name, "role": "", "cnt": 0, "peak": 0,
                                   "first": None, "last": None,
                                   "reqs": 0, "minutes": 0, "busy": 0, "minset": set(),
                                   "ips": []})
        for ip, times in per_ip.items():
            mins = {minute_of(t) for t in times}
            a["reqs"] += len(times)
            a["minset"] |= mins
            a["ips"].append((ip, len(times), span_range(times), len(mins)))
    for a in acct.values():
        # 同一账号的多个 IP 区间先合并再计时长（并行时段不能算两遍）
        a["minutes"] = merge_minutes([rng for _ip, _n, rng, _b in a["ips"]])
        a["busy"] = len(a["minset"])      # 至少发过一次请求的分钟数（下界）
        del a["minset"]
        a["ips"].sort(key=lambda x: -x[1])
    # 有登录记录的在前，按登录次数；匿名 IP 归入「未识别」排最后
    acct_view = sorted(acct.values(), key=lambda a: (-a["cnt"], -a["minutes"]))

    # ── 3. AI 使用 ──
    c.execute("""
        SELECT u.username, COUNT(*) AS calls,
               COALESCE(SUM(a.tokens_in + a.tokens_out),0) AS tokens,
               COALESCE(SUM(a.duration_ms),0) AS dur_ms,
               GROUP_CONCAT(DISTINCT a.operation) AS ops
        FROM ai_usage_logs a JOIN users u ON u.id = a.user_id
        WHERE a.created_at >= ? AND a.created_at < ?
        GROUP BY u.username ORDER BY calls DESC
    """, (day_from, day_to))
    ai = c.fetchall()
    ai_calls = sum(r["calls"] for r in ai)
    ai_tokens = sum(r["tokens"] for r in ai)

    # ── 4. 下载/导出 ──
    c.execute("""
        SELECT u.username, d.file_type, COUNT(*) AS cnt
        FROM download_logs d JOIN users u ON u.id = d.user_id
        WHERE d.created_at >= ? AND d.created_at < ?
        GROUP BY u.username, d.file_type ORDER BY cnt DESC
    """, (day_from, day_to))
    dl = c.fetchall()
    dl_total = sum(r["cnt"] for r in dl)

    # ── 5. 业务数据（当日新建）──
    created = []
    for tbl, label in [("solutions", "方案"), ("quotations", "报价单"), ("products", "产品")]:
        try:
            n = c.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE created_at >= ? AND created_at < ?",
                (day_from, day_to)).fetchone()[0]
        except sqlite3.Error:
            n = 0
        created.append((label, n))

    # ── 6. 对比昨日 ──
    prev_users = c.execute(
        "SELECT COUNT(DISTINCT user_id) FROM login_logs "
        "WHERE created_at >= ? AND created_at < ? AND success=1",
        (prev_from, prev_to)).fetchone()[0]
    prev_cnt = c.execute(
        "SELECT COUNT(*) FROM login_logs WHERE created_at >= ? AND created_at < ? AND success=1",
        (prev_from, prev_to)).fetchone()[0]
    prev_total = prev_5xx = 0
    prev_journal = journal_of(prev_day)
    if prev_journal:
        prev_total, prev_5xx, _p4, _pp, _pa = parse_requests(prev_journal)
    conn.close()

    # ── 7. 整体运行情况 ──
    sys_lines, alerts, compact = system_status(day, journal, req_total, s5xx, s4xx, probe)

    today_users = len(logins)
    today_cnt = sum(r["cnt"] for r in logins)

    # ── 输出：正常极简 / 异常全量 ──
    if not alerts and not force_full:
        # 用「无告警项」而不是「一切正常」：阈值内的 5xx / ERROR 仍会显示在下面一行，
        # 说「一切正常」会和数字自相矛盾
        print(f"✅ product-db 日报 {day}｜无告警项")
        if acct_view:
            for seg in account_lines(acct_view):
                print("   " + seg)
        else:
            print("   👥 今日无登录、无访问")
        print("   🖥️ " + " · ".join(compact))
        print(f"   🤖 AI {ai_calls} 次" + (f"/{ai_tokens//1000}k tokens" if ai_tokens else "")
              + f" · 📥 下载 {dl_total}"
              f" · 📦 新建 " + " ".join(f"{k}+{v}" for k, v in created)
              + (f" · ⚠️ 登录失败 {failed} 次" if failed else ""))
        return 0

    lines = []
    if alerts:
        lines.append(f"⚠️ product-db 日报 {day} —— 需关注 {len(alerts)} 项")
        for i, a in enumerate(alerts, 1):
            lines.append(f"  {i}) {a}")
    else:
        lines.append(f"📊 product-db 运行报告 — {day}")
    lines.append("=" * 46)

    lines.append(f"\n👥 账号使用情况 ({today_users} 个账号有登录)")
    if acct_view:
        for a in acct_view:
            head = f"  • {a['name']}" + (f" ({a['role']})" if a["role"] else "")
            if a["cnt"]:
                head += f" — 登录 {a['cnt']} 次"
                if a["first"]:
                    head += f"（{to_local(a['first'])} ~ {to_local(a['last'])}）"
                if a["peak"] >= BURST_PER_MIN:
                    head += f"（峰值 {a['peak']} 次/分，疑似自动化测试）"
            else:
                head += f" — 无登录记录，{a['reqs']} 次访问"
            lines.append(head)
            lines.append(f"      活跃跨度 {a['minutes']} 分钟"
                         f"（其中有请求 {a['busy']} 分钟）/ {len(a['ips'])} 个 IP")
            for ip, n, (s, e), busy in a["ips"]:
                lines.append(f"      · {ip}: {n:,} 请求, 跨度 {e - s} 分钟"
                             f"（有请求 {busy} 分钟）")
    else:
        lines.append("  （无用户登录、无访问）")
    if failed:
        lines.append(f"  ⚠️ 登录失败尝试: {failed} 次")
    lines.append("  (注: 活跃跨度 = 首末请求间隔(含空闲); 有请求 = 至少发过一次请求的分钟数;"
                 " 已排除探针流量; 跨天会话会被截断)")

    lines.append("\n🤖 AI 助手使用")
    if ai:
        for r in ai:
            lines.append(f"  • {r['username']}: {r['calls']} 次调用 | {r['tokens']} tokens"
                         f" | 耗时 {r['dur_ms']/1000:.0f}s")
            lines.append(f"      操作: {r['ops']}")
    else:
        lines.append("  （无 AI 调用）")

    lines.append("\n📥 下载/导出")
    if dl:
        for r in dl:
            lines.append(f"  • {r['username']}: {r['file_type']} × {r['cnt']}")
    else:
        lines.append("  （无下载）")

    lines.append("\n📦 业务数据 (当日新建)")
    lines.append("  " + "  ".join(f"{k}: +{v}" for k, v in created))

    lines.append("\n🖥️ 整体运行情况")
    lines.extend(sys_lines)
    lines.append(f"  对比昨日: 请求 {req_total:,} / 5xx {s5xx}（昨日 {prev_total:,} / {prev_5xx}）")
    lines.append(f"\n📈 对比昨日登录: 昨日 {prev_users} 人 / {prev_cnt} 次, 今日 {today_users} 人 / {today_cnt} 次")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
