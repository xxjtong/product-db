"""Authentication routes — login, logout, profile, user management."""
import json
import logging
import threading
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import hash_password, verify_password, create_token, get_current_user, client_ip
from app.services import rate_limit
from app.models.user import User
from app.models.login_log import LoginLog
from app.schemas.auth import (
    LoginRequest, TokenResponse, UserResponse,
    CreateUserRequest, UpdateUserRequest, UpdateProfileRequest,
    RegistrationRequest, ResetPasswordRequest, FieldVisibilityUpdate, AIPromptUpdate,
)
from app.config import settings
import httpx

router = APIRouter()


# IP → 地区。两级来源：ip2region 离线库优先，未命中/不适用时才回落 ipapi.co。
# 结果按 IP 缓存：同一 IP 的地区一天内不会变，缓存既省解析，也避免登录路径阻塞在网络调用上。
#
# 日志注：本文件的告警走 stdlib `logging.getLogger("uvicorn")`，记录进 **journald**
# （`journalctl -u product-db`），**不会**进 `backend/app.log` —— loguru 只接管它自己的
# logger，仓库里其他 21 处 logging.getLogger 同理。排查地区问题时两个地方都要看。
_ip_region_cache: dict = {}
_IP_REGION_TTL = 86400      # 成功结果缓存 1 天
_IP_REGION_FAIL_TTL = 300   # 失败也短暂缓存，防止每次都去撞配额
_IP_REGION_CACHE_MAX = 2048  # 登录接口匿名可达，防止缓存被大量不同 IP 撑爆

# ip2region 离线库：进程内单例（Searcher 常驻一个文件句柄，VectorIndex 已预载 512KB）。
# 加载失败只记一次 WARNING 并永久回落在线查询，不阻断登录。
_ip2region_searcher = None
_ip2region_loaded = False
_ip2region_lock = threading.Lock()


def _get_ip2region_searcher():
    """Get the process-wide ip2region searcher, loading it on first use; None if unavailable."""
    global _ip2region_searcher, _ip2region_loaded
    if _ip2region_loaded:
        return _ip2region_searcher
    with _ip2region_lock:
        if _ip2region_loaded:
            return _ip2region_searcher
        _ip2region_loaded = True
        log = logging.getLogger("uvicorn")
        try:
            import ip2region.searcher as xdb_searcher
            import ip2region.util as xdb_util
            path = settings.IP2REGION_XDB
            xdb_util.verify_from_file(path)
            v_index = xdb_util.load_vector_index_from_file(path)
            _ip2region_searcher = xdb_searcher.new_with_vector_index(xdb_util.IPv4, path, v_index)
            log.info("ip2region 离线库已加载：%s", path)
        except Exception as e:
            log.warning("ip2region 离线库不可用（%s：%s），IP 地区改走在线查询",
                        settings.IP2REGION_XDB, e)
            _ip2region_searcher = None
    return _ip2region_searcher


def _format_offline_region(raw: str) -> str:
    """离线库返回 `国家|省份|城市|ISP|国家代码`（v4 xdb 3.0 结构），缺失字段为 "0"。

    只在拿到可展示的信息时才返回；否则返回空串交给在线查询兜底 ——
    保留地址段在库里是 `Reserved|Reserved|Reserved|0|0`，那是「查不到」，
    不代表用户在「Reserved 地区」登录。
    """
    fields = (raw or "").split("|")
    country = fields[0] if len(fields) > 0 else ""
    province = fields[1] if len(fields) > 1 else ""
    city = fields[2] if len(fields) > 2 else ""
    if country in ("", "0", "Reserved"):
        return ""
    # 展示口径与在线结果一致：城市优先，其次省份，最后只留国家
    for value in (city, province):
        if value and value != "0":
            return f"{value}, {country}"
    return country


def _lookup_ip_region_offline(ip: str) -> str:
    """离线查询；库不可用、地址不在库中（含 IPv6 地址查 v4 库）时返回空串。"""
    searcher = _get_ip2region_searcher()
    if searcher is None:
        return ""
    try:
        return _format_offline_region(searcher.search(ip))
    except Exception as e:
        # IPv6 地址查 IPv4 库必然抛错，是预期内的回落场景，不刷 WARNING
        logging.getLogger("uvicorn").debug("ip2region 离线查询 %s 失败：%s", ip, e)
        return ""


def _lookup_ip_region_online(ip: str) -> str:
    """ipapi.co 在线查询（离线库未命中时的兜底）。

    失败必须留下可见痕迹：ipapi.co 免费额度耗尽时返回的是 HTTP 200 + 纯文本付费
    提示（不是 JSON）。早期实现直接 `resp.json()`，抛出的 JSONDecodeError 被裸
    `except Exception` 吞掉且只记 DEBUG（生产日志 sink 是 INFO）—— 结果是「地区」
    静默变空：2026-09 实测某日 189 条登录记录中 188 条为空，无人察觉。
    """
    log = logging.getLogger("uvicorn")
    try:
        resp = httpx.get(f"https://ipapi.co/{ip}/json/", timeout=3)
        ctype = (resp.headers.get("content-type") or "").lower()
        if resp.status_code != 200:
            log.warning("IP 地区查询 %s 返回 HTTP %s，本次地区留空", ip, resp.status_code)
        elif "json" not in ctype:
            # 免费额度耗尽时 ipapi.co 走这一支：200 + 纯文本
            log.warning("IP 地区查询 %s 返回非 JSON 响应（ipapi.co 配额耗尽？）：%.80s", ip, resp.text)
        else:
            data = resp.json()
            city = data.get("city") or ""
            country = data.get("country_name") or ""
            region = f"{city}, {country}" if city else country
            if region:
                return region
            log.warning("IP 地区查询 %s 未返回城市/国家：%.120s", ip, resp.text)
    except Exception as e:
        log.warning("IP 地区查询失败 %s：%s", ip, e)
    return ""


def _lookup_ip_region(ip: str) -> str:
    """IP → 地区：ip2region 离线库优先，未命中回落 ipapi.co，两者都拿不到则留空。"""
    if settings.DISABLE_IP_LOOKUP:
        return ""
    if not ip or ip.startswith("127.") or ip.startswith("192.168.") or ip.startswith("10.") or ip in ("::1", "testclient"):
        return "本地"

    now = time.time()
    cached = _ip_region_cache.get(ip)
    if cached and cached[0] > now:
        return cached[1]

    region = _lookup_ip_region_offline(ip) or _lookup_ip_region_online(ip)

    if len(_ip_region_cache) >= _IP_REGION_CACHE_MAX:
        _ip_region_cache.clear()
    _ip_region_cache[ip] = (now + (_IP_REGION_TTL if region else _IP_REGION_FAIL_TTL), region)
    return region


def _check_rate_limit(ip: str, db: Session) -> bool:
    """该 IP 的登录失败次数是否已达上限（实现见 services/rate_limit）。"""
    from app.services import rate_limit
    return rate_limit.is_rate_limited(
        db, ip, limit=settings.LOGIN_RATE_LIMIT, window=settings.LOGIN_RATE_WINDOW,
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if _check_rate_limit(ip, db):
        raise HTTPException(429, "登录尝试过于频繁，请稍后再试")
    user = db.query(User).filter_by(username=data.username).first()
    user_agent = request.headers.get("User-Agent", "")

    if not user or not verify_password(data.password, user.password_hash):
        rate_limit.record_failure(db, ip=ip, user_agent=user_agent,
                                  region=_lookup_ip_region(ip))
        raise HTTPException(401, "用户名或密码错误")

    if not user.is_active:
        # 禁用账户的登录尝试也要落审计并计入失败计数：此前直接 403 不写 login_logs，
        # 导致审计链断裂 —— 管理员既看不到有人在反复尝试已禁用的账户，限流也数不到。
        rate_limit.record_failure(db, ip=ip, user_id=user.id, user_agent=user_agent,
                                  region=_lookup_ip_region(ip))
        raise HTTPException(403, "账户已被禁用")

    # Auto-upgrade legacy SHA256 hash to bcrypt
    if not user.password_hash.startswith("$2"):
        user.password_hash = hash_password(data.password)

    region = _lookup_ip_region(ip)
    db.add(LoginLog(user_id=user.id, ip_address=ip, region=region, success=True,
                    user_agent=user_agent))
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token = create_token(user.id, user.username, user.token_version)
    return {"token": token, "user": user.to_dict()}


@router.get("/auth/me", response_model=UserResponse)
def get_me(user=Depends(get_current_user)):
    return {"user": user.to_dict()}


@router.post("/auth/logout")
def logout(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """登出：把该用户的 token_version +1，作废其**所有**已签发的 token。

    JWT 是无状态的，若不递增这个版本号，「登出」只是前端把 token 从 localStorage
    删掉，被复制走的 token 仍能用满 24h。代价是也会登出该用户的其他设备 ——
    在只有单一账号的使用场景下，这是更安全的一侧。
    """
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return {"ok": True}


@router.put("/auth/profile", response_model=UserResponse)
def update_profile(data: UpdateProfileRequest, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    if data.email is not None:
        user.email = data.email
    if data.password:
        # Require current password for security
        if not data.current_password or not verify_password(data.current_password, user.password_hash):
            raise HTTPException(400, "当前密码错误")
        if len(data.password) < 8:
            raise HTTPException(400, "密码至少8位")
        user.password_hash = hash_password(data.password)
        # 改密后作废该用户所有已签发的 token（前端会提示重新登录）
        user.token_version = (user.token_version or 0) + 1
    db.commit()
    return {"user": user.to_dict()}


# --- Registration ---

@router.get("/auth/registration-status")
def registration_status(db: Session = Depends(get_db)):
    from app.models.system_setting import SystemSetting
    s = db.query(SystemSetting).filter_by(key="registration_open").first()
    return {"open": s.value == "true" if s else False}


@router.post("/auth/register")
def register(data: RegistrationRequest, request: Request, db: Session = Depends(get_db)):
    from app.models.system_setting import SystemSetting
    # 先判开关再看频率：注册关闭时应当稳定回「注册功能未开放」（403），
    # 而不是刷几次之后变成 429 —— 那会让用户看不懂到底是哪个问题。
    s = db.query(SystemSetting).filter_by(key="registration_open").first()
    if not s or s.value != "true":
        raise HTTPException(403, "注册功能未开放")
    ip = client_ip(request)
    # 注册是匿名可达的写接口：按 IP 限制**尝试**次数（不分成败），挡批量注册与用户名枚举。
    # 不能塞进 login_logs 计数 —— 那张表是登录审计，且与登录失败共用一个桶会误伤正常登录。
    if rate_limit.check_and_hit(f"register:{ip}",
                                limit=settings.REGISTER_RATE_LIMIT,
                                window=settings.REGISTER_RATE_WINDOW):
        raise HTTPException(429, "注册尝试过于频繁，请稍后再试")
    username = data.username.strip()
    password = data.password
    if len(username) < 2 or len(password) < 8:
        raise HTTPException(400, "用户名至少2位，密码至少8位")
    if db.query(User).filter_by(username=username).first():
        raise HTTPException(400, "用户名已存在")
    u = User(username=username, password_hash=hash_password(password),
             role="user", email=data.email)
    db.add(u)
    db.commit()
    db.refresh(u)
    # 注册成功**不写 login_logs**：那张表是登录审计（登录成功/失败），注册既不是登录
    # 也不是登录失败。此前记一条 success=True，既污染审计口径，又让人误以为注册在
    # 「登录失败计数」里被算过——实际它反而绕过了登录限流。
    token = create_token(u.id, u.username, u.token_version)
    return {"token": token, "user": u.to_dict()}


# --- Session / JWT renewal ---

@router.get("/auth/session")
def get_session(user=Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.field_visibility import get_field_visibility, cost_visible
    from app.models.system_setting import SystemSetting

    s = db.query(SystemSetting).filter_by(key="registration_open").first()
    return {
        "user": user.to_dict(),
        "field_visibility": {} if user.role == 'admin' else get_field_visibility(db),
        # 生效后的成本可见性（admin / 按用户覆盖 / 全局开关三者合一），前端据此决定是否渲染成本列
        "can_view_cost": cost_visible(user, db),
        "registration_open": s.value == "true" if s else False,
    }
