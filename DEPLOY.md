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
| **文档** | `docs/`, `AGENTS.md` | `/opt/product-db/` | `git push` → `git pull` |
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

# 2. 服务器拉取 + 重启
ssh -p 28793 tong@124.221.178.161 \
  'cd /opt/product-db && git stash && git pull && git stash drop 2>/dev/null; sudo systemctl restart product-db'

# 3. 验证
curl -s 'https://product-db.cn/product-db/api/health'  # 如果有 health endpoint
```

## 部署命令（全栈变更）

```bash
# 1. 本地构建前端
cd frontend && npm run build

# 2. 本地提交推送
cd .. && git add -A && git commit -m "..." && git push

# 3. 部署前端（--delete 自动清理旧构建残留，无需再手工清 assets）
rsync -az --delete -e "ssh -p 28793" frontend/dist/ \
  tong@124.221.178.161:/opt/product-db/frontend/dist/

# 4. 服务器拉取后端 + 安装依赖（如有新增）+ 重启
ssh -p 28793 tong@124.221.178.161 \
  'cd /opt/product-db && git pull && cd backend && source venv/bin/activate && pip install -r requirements.txt -q; sudo systemctl restart product-db'
```

## Nginx 配置位置

```
/etc/nginx/sites-enabled/product-db → /etc/nginx/sites-available/product-db
```

修改后：`sudo nginx -t && sudo systemctl reload nginx`

## systemd 配置

```
/etc/systemd/system/product-db.service
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

## 日志

- **应用日志**: `/opt/product-db/backend/app.log`（loguru，10MB 轮转 / 保留 7 天，权限 600）
  - ⚠️ 早先本节写的是 `/opt/product-db/app.log`，**那是错的**：日志路径原本是相对路径 `"app.log"`，落点取决于进程 CWD。历史上 CWD 变过，日志因此散落在项目根、`backend/`、`frontend/` 三处，且残留文件是 644（world-readable）。
  - 2026-09 已改为基于 `backend/` 的绝对路径（`backend/app/main.py` 的 `LOG_FILE`），此后只有 `backend/app.log` 会更新。旧位置的文件是历史残留，不会被 loguru 的 retention 接管，可手工删除。
- **systemd 日志**: `journalctl -u product-db -f`
- **Nginx 日志**: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`
- **备份日志**: `/opt/product-db-backups/db/backup.log`（每日备份脚本写入，超过 1MB 自动截断）

## 数据库备份

**备份目录：`/opt/product-db-backups/`**（与代码目录同级、分离，避免 `git clean -fd` / 重新克隆时被连带删除 —— 2026-08 曾因 `git clean -fd` 清掉未跟踪的 `static/` 导致首页 404）

```
/opt/product-db-backups/
├── db/        数据库快照 product_db.db.bak.YYYYmmdd_HHMMSS
└── uploads/   上传文件镜像（129M / 937 文件）
```

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

**当前无自动备份**（截至 2026-08-02），建议部署 cron/systemd timer 每日执行上面的快照 + rsync。
