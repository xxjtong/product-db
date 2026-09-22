"""计数限流 —— 登录、注册等匿名可达接口共用。

两种原语，按语义选用，不要把两者混用在同一个桶里：

1) **失败尝试计数**（DB 持久化）：以 `login_logs` 作为失败流水，按 IP 统计时间窗口内
   的失败条数。登录走这条 —— 计数随库持久化，进程重启不清零，且与登录审计同源。
2) **请求频次计数**（进程内滑动窗口）：按任意 key 统计窗口内请求次数，**不分成败**。
   注册走这条 —— 要挡的是「批量创建账号」，注册成功本身也是刷量，不能只数失败。

进程内实现的前提是**单进程部署**（uvicorn 单 worker，见 DEPLOY.md）。若将来上多
worker 或多机，原语 2 必须换成共享存储（Redis / DB），否则每个 worker 各有一份计数。
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session


# ─────────────────────────── 原语一：失败尝试计数（DB） ───────────────────────────

def count_failures(db: Session, ip: str, window: int) -> int:
    """窗口内该 IP 的失败尝试数（数据源：login_logs）。"""
    from app.models.login_log import LoginLog
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window)
    return db.query(LoginLog).filter(
        LoginLog.ip_address == ip,
        LoginLog.success == False,  # noqa: E712 —— SQLAlchemy 需要 `==`
        LoginLog.created_at >= cutoff,
    ).count()


def is_rate_limited(db: Session, ip: str, *, limit: int, window: int) -> bool:
    """该 IP 在窗口内的失败次数是否已达上限。"""
    return count_failures(db, ip, window) >= limit


def record_failure(db: Session, *, ip: str, user_id: Optional[int] = None,
                   user_agent: str = "", region: str = "", commit: bool = True) -> None:
    """记一次失败尝试（写入 login_logs，既是审计也是原语一的计数来源）。"""
    from app.models.login_log import LoginLog
    db.add(LoginLog(user_id=user_id, ip_address=ip, success=False,
                    user_agent=user_agent, region=region))
    if commit:
        db.commit()


# ─────────────────────── 原语二：请求频次计数（进程内滑动窗口） ───────────────────────

# key → 该 key 的命中时间戳列表（升序，只保留窗口内的）
_hits: dict = {}
_lock = threading.Lock()
# 匿名接口可达，key 里带 IP：设上限防止大量不同 IP 把内存撑爆（满了整体清空，
# 与 auth_routes 里 IP 地区缓存的处理一致 —— 宁可短暂放宽，也不要无界增长）
_MAX_KEYS = 4096


def _prune(stamps: list, now: float, window: int) -> list:
    cutoff = now - window
    return [t for t in stamps if t > cutoff]


def count(key: str, window: int) -> int:
    """窗口内该 key 的命中次数。"""
    now = time.time()
    with _lock:
        stamps = _prune(_hits.get(key, []), now, window)
        if stamps:
            _hits[key] = stamps
        else:
            _hits.pop(key, None)
        return len(stamps)


def hit(key: str, window: int) -> int:
    """记一次命中并返回窗口内的总次数。"""
    now = time.time()
    with _lock:
        if len(_hits) >= _MAX_KEYS and key not in _hits:
            _hits.clear()
        stamps = _prune(_hits.get(key, []), now, window)
        stamps.append(now)
        _hits[key] = stamps
        return len(stamps)


def check_and_hit(key: str, *, limit: int, window: int) -> bool:
    """先判后记，合并成一次加锁：返回 True 表示**已超限**（本次不再计数）。

    超限时不再计数，是为了让窗口自然滑出后自动恢复，而不是被持续请求一直顶住。
    """
    now = time.time()
    with _lock:
        stamps = _prune(_hits.get(key, []), now, window)
        if len(stamps) >= limit:
            _hits[key] = stamps
            return True
        stamps.append(now)
        _hits[key] = stamps
        return False


def reset(key: Optional[str] = None) -> None:
    """清空计数。传 key 只清这一个；不传则全清（测试与运维用）。"""
    with _lock:
        if key is None:
            _hits.clear()
        else:
            _hits.pop(key, None)
