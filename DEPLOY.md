# product-db 部署说明

## 服务器

| 环境 | 服务器 | SSH |
|------|--------|-----|
| 生产 | product-db.cn (124.221.178.161) | `ssh -p 28793 tong@124.221.178.161` |

服务器前提（Debian 12）：需安装 `rsync`（前端部署用，见下方部署命令）。

```bash
ssh -p 28793 tong@124.221.178.161 'sudo apt-get install -y --no-install-recommends rsync'
```

> 2026-09-16 已安装 `3.2.7-1+deb12u5`（bookworm-security，含 CVE-2024-12084 系列修复）。rsync 仅装客户端二进制，默认 `rsync.service` 为 disabled，不监听端口。

## 环境拓扑

| 角色 | 位置 | 职责 |
|------|------|------|
| **开发环境** | 本机 | 唯一改动来源，所有提交从这里产生 |
| **仓库 / 备份** | GitHub `xxjtong/product-db` | 本机 `push`、服务器 `pull`，兼作远程备份 |
| **部署目标** | 生产服务器 `/opt/product-db` | **纯部署目标**，不产生改动 |

> ⚠️ **不要在生产服务器上编辑代码**。服务器的本地改动一律视为误操作，部署时直接丢弃 —— 下方「部署命令（后端变更）」里的 `git stash && git stash drop` 就是为此。需要改代码请回到本机改、提交、推送。
>
> 不受影响的部分：`backend/.env`、`backend/product_db.db`、`backend/app/uploads/`、`frontend/dist/` 均已在 `.gitignore` 中，`git stash` 不碰未跟踪文件、`git clean` 不加 `-x` 也不删已忽略文件 —— 这些能在 `git pull` 中安全存活。
>
> ⛔ **但绝不要在生产执行 `git clean -fd`**：`static/index.html` 既未跟踪也未忽略，会被直接删除 —— 这正是 2026-08 首页 404 的成因。

### 数据库归属：以服务器为准（与代码方向相反）

代码是「本机 → GitHub → 服务器」单向流动，**数据库正好相反**：

| | 权威来源 | 说明 |
|---|---|---|
| 代码 | **本机** | 改动只从本机产生 |
| 数据库 | **服务器** | `/opt/product-db/backend/product_db.db` 是唯一权威数据源 |

- 🚫 **任何情况下不要用本机的 `backend/product_db.db` 覆盖生产库**。两库结构相同但数据不同（2026-09-16 实测：生产 396 产品 / 6 方案 / 6 报价单；本机 395 / 4 / 4），覆盖即数据丢失。
- 本地开发库仅供调试，**不是**生产数据的副本，不要把它当作数据源。
- 需要用生产数据做本地调试时，走**只读快照**：从 `/opt/product-db-backups/db/` 取一份 `.backup` 产物拷到本机另存使用，绝不反向回写。
- 备份方向是单向的：生产 → `/opt/product-db-backups/`，**不回写**。
- `git pull` 不会碰它 —— `product_db.db` 已在 `.gitignore` 中（见上方说明）。

## 服务架构

```
用户 → Nginx (:443) → /product-db/* → proxy_pass → FastAPI (:8000)
                                          ↓
                                    frontend/dist/ (静态文件 + SPA)
```

- **Nginx**: 仅反向代理 `/product-db/` 到 FastAPI，SSL 终结
- **FastAPI**: `StaticFiles` mount 提供 `/product-db/assets/*`，catch-all 返回 `index.html`
- **systemd**: `product-db.service`，WorkingDirectory=`/opt/product-db/backend`

## 文件部署位置

| 内容 | 本地路径 | 服务器路径 | 部署方式 |
|------|----------|-----------|---------|
| **前端 dist** | `frontend/dist/` | `/opt/product-db/frontend/dist/` | `rsync -az --delete -e "ssh -p 28793" frontend/dist/ tong@124.221.178.161:/opt/product-db/frontend/dist/` |
| **后端代码** | `backend/` | `/opt/product-db/backend/` | `git push` → 服务器 `git pull`，然后 `sudo systemctl restart product-db` |
| **Python 依赖** | `backend/requirements.txt` | `/opt/product-db/backend/` | SSH 进入后 `source venv/bin/activate && pip install -r requirements.txt` |
| **环境变量** | `backend/.env` | `/opt/product-db/backend/.env` | 手动编辑（不入 git） |
| **数据库** | `backend/product_db.db` | `/opt/product-db/backend/product_db.db` | 不入 git；**以服务器为准**，禁止用本地库覆盖（见「数据库归属」） |
| **上传文件** | `backend/app/uploads/` | `/opt/product-db/backend/app/uploads/` | 不入 git |
| **IP 地区离线库** | `backend/data/ip2region_v4.xdb`（11MB） | `/opt/product-db/backend/data/ip2region_v4.xdb` | 入 git，随 `git pull` 下发；只读，无需额外步骤（见「IP 地区离线库」） |
| **文档** | `docs/`, `AGENTS.md` | `/opt/product-db/` | `git push` → `git pull` |
| **静态占位页** | `static/`（`coming-soon.html`、`maintenance.html`） | `/opt/product-db/static/` | 随 `git pull` 下发（仓库根目录就是 `/opt/product-db`），nginx `root` 直接读该目录 |
| **Nginx 配置** | — | `/etc/nginx/sites-enabled/product-db` | 手动编辑，`sudo nginx -t && sudo nginx -s reload` |
| **systemd** | — | `/etc/systemd/system/product-db.service` | `sudo systemctl daemon-reload && sudo systemctl restart product-db` |

## ⚠️ 重要：不要部署到 static/

`/opt/product-db/static/` 目录是 Nginx `root`，**仅**用 `coming-soon.html` 作为首页占位。前端 dist 必须部署到 `/opt/product-db/frontend/dist/`。

配置来源：
- `backend/app/config.py`: `FRONTEND_DIST = "frontend/dist"`（相对 backend 目录）
- `backend/app/main.py`: 解析为 `os.path.join(backend_dir, "..", "frontend/dist")` → `/opt/product-db/frontend/dist/`
- Nginx: `location /product-db/ { proxy_pass http://127.0.0.1:8000; }` — 不做静态文件服务，全部透传给 FastAPI
- Nginx `root /opt/product-db/static` 仅用于 `location = /` 返回 `coming-soon.html`；`static/index.html` 保留作为首页备用

## 部署命令（纯前端变更）

```bash
# 1. 本地构建
cd frontend && npm run build

# 2. 增量同步到正确目录
#    -a 保留属性 / -z 压缩 / --delete 自动清理上一次构建残留的 hash 资源
#    两侧路径结尾的斜杠必须有：表示「同步目录内容」，而不是套一层 dist 目录
rsync -az --delete -e "ssh -p 28793" dist/ \
  tong@124.221.178.161:/opt/product-db/frontend/dist/

# 前端变更无需重启后端，Nginx 透传，FastAPI 直接读新文件
```

> `--delete` 只作用于目标目录，删掉的是「本地已不存在的旧构建产物」。曾在 2026-09 发现残留累积到 277 个（322 个里只有 45 个有效），`scp` 只增不删是根因 —— 改用 rsync 后该问题不复存在。
>
> 首次用 rsync 替换 scp 时会重传全部文件（scp 不保留 mtime，rsync 据此判定不同），之后再跑就是真正的增量（实测第二次为 0 传输 0 字节）。

## 部署命令（后端变更）

```bash
# 1. 本地提交推送
git add -A && git commit -m "..." && git push

# 2. 先看服务器工作区状态（有未提交改动就先弄清是什么，不要盲目 stash+drop）
ssh -p 28793 tong@124.221.178.161 'cd /opt/product-db && git status --short'

# 3. 服务器拉取 + 装依赖 + 执行迁移 + 带就绪门控重启
ssh -p 28793 tong@124.221.178.161 \
  'cd /opt/product-db && git pull && backend/venv/bin/pip install -q -r backend/requirements.txt \
   && cd backend && venv/bin/alembic upgrade head && cd .. \
   && deploy/restart-ready.sh'
```

> ⚠️ **`alembic upgrade head` 不要省**：迁移直到 2026-09 都是靠手工执行的，结果是
> `created_by` 列、`product_categories` 表、一批索引在生产静默滞后了几个月
> （R33 才补齐）。它幂等，可以每次都跑。
>
> `deploy/restart-ready.sh` 取代裸 `systemctl restart`：它会轮询健康接口直到就绪
> 再验一次经 nginx 的入口与前端首页，失败则打印 journalctl 与回滚命令并以非 0 退出。

> 不要用 `git stash && git pull && git stash drop`：服务器上任何未提交改动会被静默丢弃（2026-09 曾发现服务器遗留未跟踪文件）。

## 部署命令（全栈变更）

```bash
# 1. 本地构建前端
cd frontend && npm run build

# 2. 本地提交推送
cd .. && git add -A && git commit -m "..." && git push

# 3. 部署前端（--delete 自动清理旧构建残留，无需再手工清 assets）
rsync -az --delete -e "ssh -p 28793" frontend/dist/ \
  tong@124.221.178.161:/opt/product-db/frontend/dist/

# 4. 服务器拉取后端 + 装依赖（如有新增）+ 迁移 + 就绪门控重启
ssh -p 28793 tong@124.221.178.161 \
  'cd /opt/product-db && git pull && backend/venv/bin/pip install -q -r backend/requirements.txt \
   && cd backend && venv/bin/alembic upgrade head && cd .. \
   && deploy/restart-ready.sh'
```

> 前端产物是独立 rsync 的（不入 git），所以只改前端时**不需要重启后端**：
> FastAPI 每次请求都从磁盘读 `frontend/dist`，`git pull` 之后直接生效。

## Nginx 配置位置

```
/etc/nginx/sites-enabled/product-db → /etc/nginx/sites-available/product-db
```

修改后：`sudo nginx -t && sudo systemctl reload nginx`

## systemd 配置

### 主服务 `product-db.service`

**仓库内已版本化**：[`deploy/systemd/product-db.service`](deploy/systemd/product-db.service)（内容与生产实际运行一致）。安装/更新：

```bash
# 需要 sudo（/etc/systemd/system 属 root）
sudo cp /opt/product-db/deploy/systemd/product-db.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl restart product-db
```

```ini
[Unit]
Description=Product DB Backend
After=network.target

[Service]
Type=simple
User=tong
Group=tong
WorkingDirectory=/opt/product-db/backend
Environment=PATH=/opt/product-db/backend/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/product-db/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### ⚠️ 权限加固 drop-in（必做，否则新文件的默认权限是 644）

应用以 `tong` 运行、进程 umask 默认 `0022`，它创建的文件（SQLite 的 `-wal`/`-shm`、轮转日志、uploads 新文件）都是 **644 = world-readable**。该实例存在 `debian` / `lighthouse` / `tong` 三个本地账号，等于生产库与日志对它们可读。

**仓库内已版本化**：[`deploy/systemd/product-db.service.d/umask.conf`](deploy/systemd/product-db.service.d/umask.conf)。安装：

```bash
sudo mkdir -p /etc/systemd/system/product-db.service.d
sudo cp /opt/product-db/deploy/systemd/product-db.service.d/umask.conf \
        /etc/systemd/system/product-db.service.d/
sudo systemctl daemon-reload && sudo systemctl restart product-db

# 验证：进程 umask 必须是 0077（默认是 0022）
grep -i ^umask /proc/$(systemctl show -p MainPID --value product-db)/status
```

> `UMask` 只影响**今后新建**的文件。已有文件需一次性收紧（见下方「一次性加固」）。

### 一次性加固（新机器部署后执行一次）

```bash
# 敏感文件：SECRET_KEY / API key、数据库（含 bcrypt 密码哈希）、日志
chmod 600 /opt/product-db/backend/.env
chmod 600 /opt/product-db/backend/product_db.db /opt/product-db/backend/product_db.db-wal /opt/product-db/backend/product_db.db-shm
chmod 600 /opt/product-db/backend/app*.log

# 上传目录：产品图片/文档。父目录链是 755，文件若为 644 则同机其他账号可读
chmod 700 /opt/product-db/backend/app/uploads
find /opt/product-db/backend/app/uploads -type d -exec chmod 700 {} +
find /opt/product-db/backend/app/uploads -type f -exec chmod 600 {} +

# 备份目录（含 manual/ 历史归档）不对其他本地账号开放
find /opt/product-db-backups -type d -exec chmod 700 {} +
find /opt/product-db-backups -type f -exec chmod 600 {} +
```

**加固后必须验证应用仍能提供文件**（应用以 tong 运行，属主不变应无影响）：

```bash
# 从库里取一个真实的本地上传图片，确认加固前后都是 200
URL=$(sqlite3 /opt/product-db/backend/product_db.db \
  "SELECT image_url FROM products WHERE image_url LIKE '/product-db/api/uploads/%' LIMIT 1;")
curl -s -o /dev/null -w '图片 → HTTP %{http_code}\n' "https://product-db.cn$URL"
```

> 用 `find` 分别处理目录与文件，而不是 `chmod -R`：后者只能给同一个模式，而目录要 `700`（可进入）、文件要 `600`（不给执行位）。
> 新建文件的权限由 systemd 的 `UMask=0077` 保证（见上），这里只处理存量。

## IP 地区离线库（ip2region）

登录日志的「地区」列由 `backend/data/ip2region_v4.xdb` 离线解析（**ip2region 为主，ipapi.co 只做兜底**）。

| 项 | 值 |
|----|-----|
| 数据文件 | `backend/data/ip2region_v4.xdb`（11,122,036 字节，只读，入 git） |
| 数据来源 | `https://raw.githubusercontent.com/lionsoul2014/ip2region/master/data/ip2region_v4.xdb` |
| SHA256 | `8e31bbdccb5bf21028af10592d4312ec975da0bffa108c0c5d862a12190f9ad3` |
| 查询库 | `py-ip2region==3.0.4`（官方 Python binding，Apache-2.0，已在 `requirements.txt`） |
| 配置 | `IP2REGION_XDB`（默认 `data/ip2region_v4.xdb`，相对 `backend/`） |

**部署**：文件与代码同在 git 里，`git pull` 即完成下发，无额外步骤。首次部署需 `pip install -r requirements.txt` 装上 `py-ip2region`（见「部署命令（后端变更）」）。

**验证**（服务器上执行，确认库可加载且能解析）：

```bash
cd /opt/product-db/backend && sha256sum data/ip2region_v4.xdb
venv/bin/python -c "
import ip2region.util as u, ip2region.searcher as s
u.verify_from_file('data/ip2region_v4.xdb')
print(s.new_with_vector_index(u.IPv4, 'data/ip2region_v4.xdb',
      u.load_vector_index_from_file('data/ip2region_v4.xdb')).search('113.132.197.169'))"
# 期望：中国|陕西省|西安市|电信|CN
```

**更新数据**（ip2region 不定期发版，无需跟进）：替换文件 → 记下新的 SHA256 并更新本节 → 重启服务。
`git pull` 每次会重传整个 11MB 文件，不要频繁更新。

> 库文件缺失/损坏时不会阻断登录：进程启动后首次用到时记一次 WARNING，之后永久回落 ipapi.co 在线查询。

### 为什么不加第二级兜底源（2026-09-17 评估，结论：不加）

**生产实测的命中率**：`login_logs` 里 33 个不同 IP 逐个跑离线库 → **31/31 真实 IP 全部命中**；唯二未命中的是 `127.0.0.1`（357 次）和 `testclient`（6 次），两者由代码里的「本地」短路直接返回、根本不走兜底。即国内兜底源当前能服务的流量为 **0**。

```bash
# 复现该评估
cd /opt/product-db/backend && venv/bin/python -c "
import sqlite3, ip2region.util as u, ip2region.searcher as s
se = s.new_with_vector_index(u.IPv4, 'data/ip2region_v4.xdb', u.load_vector_index_from_file('data/ip2region_v4.xdb'))
for ip, c in sqlite3.connect('product_db.db').execute('SELECT ip_address, COUNT(*) FROM login_logs GROUP BY ip_address'):
    try: print(ip, c, '->', se.search(ip))
    except Exception as e: print(ip, c, '-> ERR', e)"
```

**候选在线源实测**（全部在生产机上执行）：

| 候选 | 结果 |
|------|------|
| pconline `whois.pconline.com.cn/ipJson.jsp` | 免 key，HTTPS 200 / 139ms，`pro=陕西省 city=西安市 addr=陕西省西安市 电信ADSL`；**GBK 编码需转码**，纯 HTTP 被 403 |
| 腾讯位置服务 `apis.map.qq.com/ws/location/v1/ip` | 需 key（`{"status":301,"message":"必要字段key缺少"}`） |
| 高德 `restapi.amap.com/v3/ip` | 需 key（`INVALID_USER_KEY`） |
| ip.zxinc.org | 免 key，200 但 **1.6s**（偏慢） |
| 百度 qifu-api | `ResourceNotFound`，不支持指定 IP |
| 新浪 iplookup / ip.useragentinfo | 12s 超时 / 空响应 |

**候选第二级离线库**：ip2region 自家 v6 库仅在有 IPv6 客户端时才有用；纯真现在主推**需 APPCODE 的商业 API**，老 `qqwry.dat` 社区版的商用授权条款未能核实到官方原文（PyPI 上的 `qqwry-py3`/`qqwry` 只是读取器，不覆盖数据授权），商用项目不宜直接引入。

**数据新旧度**：库快照 `createdAt = 2026-08-28`（评估时 20 天旧），「新分配 IP 段缺失」这个理由不成立。

**结论与再评估信号**：都不加。判断「该加了」的信号是**离线未命中且在线也失败**——这种情况目前只在 ipapi.co 侧留 WARNING（`journalctl -u product-db`，见「日志」）。真出现国内 IP 未命中时再考虑，届时优先腾讯位置服务（数据最全，需 key）。

## 日志

- **应用日志**: `/opt/product-db/backend/app.log`（loguru，10MB 轮转 / 保留 7 天，权限 600）
  - ⚠️ 早先本节写的是 `/opt/product-db/app.log`，**那是错的**：日志路径原本是相对路径 `"app.log"`，落点取决于进程 CWD。历史上 CWD 变过，日志因此散落在项目根、`backend/`、`frontend/` 三处，且残留文件是 644（world-readable）。
  - 2026-09 已改为基于 `backend/` 的绝对路径（`backend/app/main.py` 的 `LOG_FILE`），此后只有 `backend/app.log` 会更新。旧位置的文件是历史残留，不会被 loguru 的 retention 接管，可手工删除。
- **systemd 日志**: `journalctl -u product-db -f`
  - ⚠️ 后端代码里用 stdlib `logging.getLogger(...)` 的地方（**23 处 / 10 个文件**，含登录地区查询、AI、报价单等）记录**只在这里**，不进 `app.log`：loguru 只接管自己的 logger。排查这类代码的告警时只看 `app.log` 会误判为「没有日志」。
    （统计口径：`grep -rho 'logging.getLogger' backend/app --include='*.py' | wc -l`）
- **Nginx 日志**: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`
- **备份日志**: `/opt/product-db-backups/db/backup.log`（每日备份脚本写入，超过 1MB 自动截断）
- **探针日志**: `/opt/product-db-backups/health.log`（可用性探针写入，超过 1MB 自动截断）

## 可用性探针（每 2 分钟）

此前**没有任何服务可用性告警**：进程崩了只有 `Restart=always` 静默拉起，前端 dist 丢失会让 SPA 返回 503 —— 两者都只能靠用户反馈才知道。

`deploy/health-check.sh` + 用户级 timer（与备份同样的模式）。**双频探测**：

| 频率 | 检查项 | 说明 |
|------|--------|------|
| 每 2 分钟 | `http://127.0.0.1:8000/product-db/api/health` | 绕开 nginx，判断应用本身是否活着 |
| 每 2 分钟 | `http://127.0.0.1:8000/product-db/` | 前端首页（dist 丢失时应用自身返回 503） |
| 每 30 分钟（或本地已异常时立即补测） | `https://product-db.cn/product-db/api/health`、`https://product-db.cn/product-db/` | 经 nginx 的端到端；**必须降频**，原因见下 |

> ⚠️ 公开入口为什么要降频：全局限流是 200/天 + 60/min，2 分钟一次 = **720 次/天**，探针会先把配额打满，然后持续把 429 误报成「服务不可用」。
> 试图用 `@limiter.exempt` 豁免健康接口**实测无效**：slowapi 的 `SlowAPIMiddleware` 用 `_find_route_handler()` 取「最后一个 FULL 匹配的路由」作为 handler，而 SPA catch-all `/product-db/{full_path:path}` 注册在该路由之后、同样匹配 `/product-db/api/health` → 解析到的 handler 是 `serve_spa`，函数级豁免永远匹配不上（实测连续打 65 次仍出现 429）。根因注释留在 `backend/app/main.py` 的 `health()`。

只在**状态变化**时写一条显著日志（`OK 服务已恢复` / `FAIL ...`），持续故障只记一行「FAIL（持续）」，避免每 2 分钟刷屏。

```bash
# 安装/更新（用户级，无需 sudo；与备份 timer 同一目录）
mkdir -p ~/.config/systemd/user
cp /opt/product-db/deploy/systemd/product-db-healthcheck.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now product-db-healthcheck.timer
systemctl --user list-timers product-db-healthcheck.timer

# 手动跑一次（排查用）
/opt/product-db/deploy/health-check.sh; echo "exit=$?"
tail -5 /opt/product-db-backups/health.log
cat /opt/product-db-backups/health.state        # ok / fail

# 自检脚本本身（不改生产状态：用独立 STATE_DIR + 死端口模拟故障）
STATE_DIR=/tmp/hc_test HEALTH_URL=http://127.0.0.1:9/x LOCAL_HOME_URL=http://127.0.0.1:9/x \
  PUBLIC_URL=http://127.0.0.1:9/x HOME_URL=http://127.0.0.1:9/x \
  /opt/product-db/deploy/health-check.sh; echo "exit=$?"   # 期望 1
```

**可选：失败时推送到飞书/钉钉等 webhook**（不配置则只写本地日志）。把地址写进 timer 的环境变量即可：

```bash
mkdir -p ~/.config/systemd/user/product-db-healthcheck.service.d
cat > ~/.config/systemd/user/product-db-healthcheck.service.d/webhook.conf <<'EOF'
[Service]
Environment=ALERT_WEBHOOK=<webhook 地址>
Environment=ALERT_WEBHOOK_STYLE=feishu   # 飞书自定义机器人用 feishu；其它用默认 text
EOF
systemctl --user daemon-reload
```

## 重启就绪门控

裸 `sudo systemctl restart product-db` 期间 uvicorn 不监听，nginx 会短暂返回 502。改用：

```bash
cd /opt/product-db && deploy/restart-ready.sh
```

它做四件事：记录重启前的 revision → restart → 轮询健康接口直到 200（默认 30s 超时）→ 再验一次经 nginx 的接口与前端首页。任一步失败会打印 `journalctl` 片段与**回滚命令**并以非 0 退出（不自动回滚，避免掩盖问题）。

**实测数据（2026-09-17，在生产机上以 0.15s 间隔打自己的公开入口）**：

| 指标 | 实测值 |
|------|--------|
| 应用就绪耗时 | **1s**（脚本轮询间隔 0.5s，报出 1s） |
| 对外 502 窗口 | **约 1.3s**（80 个样本里 7 个 502，集中在 3.23s–4.42s） |

> 早先文档里写的「5-8s」是**错的**（那是部署时操作者 `sleep 4` 的等待时间，不是用户可见窗口）。真实窗口只有 1.3s，所以本脚本的主要价值是**「部署失败能立刻发现」**（并有回滚提示），而不是消灭这 1.3s。

### 维护页（可选，需 sudo：nginx 配置属 root）

既然窗口只有 1.3s，维护页收益有限，属于**可选**项。维护页已在仓库里（`static/maintenance.html`，随 `git pull` 落到 `/opt/product-db/static/`，nginx 的 `root` 直接能读到）。

改法：在 `/etc/nginx/sites-available/product-db` 的 **server 级**（例如 `index coming-soon.html;` 之后）加两行：

```nginx
    # 后端未就绪时不返回裸 502/503/504，改为给用户一个会自动重试的维护页
    error_page 502 503 504 /maintenance.html;
    location = /maintenance.html { internal; }
```

> ⚠️ **必须放在 server 级，不要嵌进 `location /product-db/` 里面**：嵌套 location 匹配的是父级前缀之后的剩余 URI，`location = /maintenance.html` 写在里面永远匹配不到，维护页不会生效。
> `internal` 表示该页只能由 nginx 内部跳转（`error_page`）访问，直接请求会 404；`root` 从 server 级继承（`root /opt/product-db/static;`），不用重复写。

```bash
# 1) 备份（改坏了能一键回滚）
sudo cp -a /etc/nginx/sites-available/product-db ~/product-db.nginx.bak.$(date +%Y%m%d_%H%M%S)

# 2) 幂等插入两行（以 index 行做锚点；已插入过则不会重复）
sudo sed -i 's|^    index coming-soon.html;|    index coming-soon.html;\n\n    # 后端未就绪时不返回裸 502/503/504，改为给用户一个会自动重试的维护页\n    error_page 502 503 504 /maintenance.html;\n    location = /maintenance.html { internal; }|' \
  /etc/nginx/sites-available/product-db

# 3) 语法检查 + 生效
sudo nginx -t && sudo systemctl reload nginx

# 4) 验证：正常路径不受影响；维护页不可被直接访问（internal → 404）
curl -s -o /dev/null -w '  health → %{http_code}\n' https://product-db.cn/product-db/api/health
curl -s -o /dev/null -w '  直接访问维护页 → %{http_code}（期望 404）\n' https://product-db.cn/maintenance.html
```

**真实验证维护页生效**（不停后端：临时加一个指向死端口的 location，验证完删掉）：

```bash
sudo sed -i 's|^    location = /maintenance.html { internal; }|    location = /maintenance.html { internal; }\n    location = /__maint_probe__ { proxy_pass http://127.0.0.1:9; error_page 502 503 504 /maintenance.html; }|' \
  /etc/nginx/sites-available/product-db
sudo nginx -t && sudo systemctl reload nginx
curl -s https://product-db.cn/__maint_probe__ | grep -o '服务正在重启' | head -1   # 期望打印「服务正在重启」
sudo sed -i '/__maint_probe__/d' /etc/nginx/sites-available/product-db            # 删掉测试位置
sudo nginx -t && sudo systemctl reload nginx
```

**回滚**：

```bash
sudo cp -a ~/product-db.nginx.bak.<时间戳> /etc/nginx/sites-available/product-db
sudo nginx -t && sudo systemctl reload nginx
```

## 数据库备份

**备份目录：`/opt/product-db-backups/`**（与代码目录同级、分离，避免 `git clean -fd` / 重新克隆时被连带删除 —— 2026-08 曾因 `git clean -fd` 清掉未跟踪的 `static/` 导致首页 404）

```
/opt/product-db-backups/
├── db/        自动快照 product_db.db.bak.YYYYmmdd_HHMMSS
│              受保留策略管理：只留最新 14 份（脚本用 -maxdepth 1，不递归子目录）
├── uploads/   上传文件镜像（129M / 937 文件，由手动命令维护）
└── manual/    手工/历史归档，**不受保留策略影响**（清理时不会被动）
               · app-log-archive-YYYYMMDD.tar.gz — 旧日志归档
               · product_db.db.bak.<日期>_<说明> — 里程碑快照，如 pre_r27 / pre_ouchuang
```

> 归类规则：**自动产物进 `db/`，值得长期留存的进 `manual/`**。`manual/` 里的文件不会被备份脚本的保留策略删除。

### 一次性初始化（需要 sudo，只做一次）

`/opt` 属 `root:root 755`，`tong` 无权直接建目录；且 `sudo` 免密白名单里没有 `mkdir`/`chown`/`apt-get`。所以这一步必须由有 sudo 密码的人执行：

```bash
ssh -p 28793 tong@124.221.178.161 \
  'sudo mkdir -p /opt/product-db-backups/{db,uploads} && sudo chown -R tong:tong /opt/product-db-backups && ls -ld /opt/product-db-backups/{db,uploads}'
```

属主设为 `tong:tong`（与 `/opt/product-db` 一致）后，**后续备份命令与定时任务全部无需 sudo**。

### 自动备份（systemd --user timer，每日 03:30）

| 项 | 值 |
|---|---|
| 脚本 | `/opt/product-db/deploy/backup-db.sh`（随 git 下发，可版本化审阅） |
| unit | `~/.config/systemd/user/product-db-backup.{service,timer}`（源在 `deploy/systemd/`） |
| 调度 | `OnCalendar=03:30`，`Persistent=true`（宕机/重启后补跑） |
| 保留 | 最新 14 份快照（约 34M） |
| 每轮校验 | `PRAGMA integrity_check` + 行数哨兵（products / users / ai_conversations），任一不过即非 0 退出且不留残缺文件 |

```bash
# 查看下次执行时间
ssh -p 28793 tong@124.221.178.161 'systemctl --user list-timers product-db-backup.timer'

# 查看上次运行结果 / 日志
ssh -p 28793 tong@124.221.178.161 'systemctl --user status product-db-backup.service; tail -20 /opt/product-db-backups/db/backup.log'

# 手动立刻跑一次
ssh -p 28793 tong@124.221.178.161 'systemctl --user start product-db-backup.service'
```

**新机器部署 timer**（无需 sudo）：

```bash
scp -P 28793 deploy/systemd/* tong@124.221.178.161:~/.config/systemd/user/
ssh -p 28793 tong@124.221.178.161 \
  'systemctl --user daemon-reload && systemctl --user enable --now product-db-backup.timer && systemctl --user list-timers'
```

> 依赖用户级 systemd 可在无登录时运行：`loginctl enable-linger tong`（本机已开启）。

### 手动备份命令

> ⚠️ 生产库是 **SQLite WAL 模式**，直接 `cp` 只能拿到主库文件，会丢掉 WAL 中尚未合并的数据（2026-08 曾因此拿到不一致副本；实测 WAL 达 3.1MB，比主库本身还大）。**必须**用 SQLite 在线快照 `.backup`：

```bash
# 一致性快照（含 WAL 内容）
ssh -p 28793 tong@124.221.178.161 \
  'sqlite3 /opt/product-db/backend/product_db.db ".backup /opt/product-db-backups/db/product_db.db.bak.$(date +%Y%m%d_%H%M%S)"'

# 上传文件增量镜像
ssh -p 28793 tong@124.221.178.161 \
  'rsync -a --delete /opt/product-db/backend/app/uploads/ /opt/product-db-backups/uploads/'
```

> 2026-09 之前本节写的备份路径是 `/opt/product-db-backups/`，但**从未跑通过**：该目录不存在，且 `/opt` 属 `root:root`、`tong` 无写权限。已由上面的「一次性初始化」修正。

恢复：将备份库放回 `/opt/product-db/backend/product_db.db`（或 `VACUUM INTO` 反向），uploads 用 rsync 还原，然后 `sudo systemctl restart product-db`。

## ⚠️ 不要随意清理 uploads

`POST /product-db/api/agent/cleanup-uploads`（admin）只删除**未被数据库引用**且超过 7 天的文件，这是 2026-06 文件丢失事故（21 个产品文档被误删）后加固的行为。不要在代码/脚本里扩大它的删除范围；产品文件与图片的删除必须走应用接口（delete_product_file / 产品编辑）。

**自动备份**：`deploy/systemd/product-db-backup.timer` 每日 03:30（用户级，`Linger=yes`）执行 `deploy/backup-db.sh`，产物进 `/opt/product-db-backups/db/`，保留 14 份。
> 本节 2026-09-17 之前写的是「当前无自动备份，建议部署 cron/systemd timer」——**已过时**：timer 早已落地，且实测 2026-09-17 03:30:57 无人值守跑过（`systemctl --user show product-db-backup.service -p Result` → `success`，产出 `product_db.db.bak.20260917_033057`）。
> **uploads 仍只在手动命令里镜像**（`db/` 的自动快照不含上传文件）。
