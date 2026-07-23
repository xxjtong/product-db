# product-db 部署说明

## 服务器

| 环境 | 服务器 | SSH |
|------|--------|-----|
| 生产 | product-db.cn (124.221.178.161) | `ssh -p 28793 tong@124.221.178.161` |

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
| **前端 dist** | `frontend/dist/` | `/opt/product-db/frontend/dist/` | `scp -P 28793 -r frontend/dist/* tong@124.221.178.161:/opt/product-db/frontend/dist/` |
| **后端代码** | `backend/` | `/opt/product-db/backend/` | `git push` → 服务器 `git pull`，然后 `sudo systemctl restart product-db` |
| **Python 依赖** | `backend/requirements.txt` | `/opt/product-db/backend/` | SSH 进入后 `source venv/bin/activate && pip install -r requirements.txt` |
| **环境变量** | `backend/.env` | `/opt/product-db/backend/.env` | 手动编辑（不入 git） |
| **数据库** | `backend/product_db.db` | `/opt/product-db/backend/product_db.db` | 不入 git，部署时不覆盖 |
| **上传文件** | `backend/app/uploads/` | `/opt/product-db/backend/app/uploads/` | 不入 git |
| **文档** | `docs/`, `CLAUDE.md` | `/opt/product-db/` | `git push` → `git pull` |
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

# 2. 部署到正确目录
scp -P 28793 -r dist/* tong@124.221.178.161:/opt/product-db/frontend/dist/

# 3. 清理旧文件（可选，防止残留）
ssh -p 28793 tong@124.221.178.161 'ls /opt/product-db/frontend/dist/assets/'

# 前端变更无需重启后端，Nginx 透传，FastAPI 直接读新文件
```

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

# 3. 部署前端
scp -P 28793 -r frontend/dist/* tong@124.221.178.161:/opt/product-db/frontend/dist/

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

- **应用日志**: `/opt/product-db/app.log`
- **systemd 日志**: `journalctl -u product-db -f`
- **Nginx 日志**: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`

## 数据库备份

```bash
ssh -p 28793 tong@124.221.178.161 'cp /opt/product-db/backend/product_db.db /opt/product-db/backend/product_db.db.bak.$(date +%Y%m%d_%H%M%S)'
```
