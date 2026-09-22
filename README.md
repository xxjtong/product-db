# 产品数据库

IoT 产品选型对比、规格书生成、方案设计系统。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy 2.0 |
| 数据库 | SQLite + WAL（本地与生产一致；不再使用 PostgreSQL） |
| 前端 | Vue 3 + TypeScript + Vite |
| UI | CSS Variables + Lucide Icons |
| 部署 | systemd（生产，含沙箱加固）+ nginx 反代；`docker-compose.yml` 仅作本地可选 |

## 快速启动

```bash
# 后端
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 编辑配置
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd frontend
npm install
npx vite --host 0.0.0.0 --port 5173
```

浏览器访问 `http://localhost:5173`。DEV_MODE 下自动创建 admin/admin 账号。

## 测试

```bash
# Backend（675 用例：674 passed + 1 skipped，数量随迭代变化）
cd backend && venv/bin/python -m pytest tests/ -v

# Frontend
cd frontend && npx vitest run                     # 101 组件测试
cd frontend && npx vue-tsc --noEmit               # 类型检查

# E2E (需要先启动前后端服务)
cd frontend && npm run test:e2e                    # 7 个 spec 套件（见 e2e/）

# E2E 用「确定性种子库」跑（CI 就是这条路径，本地同样可用）
cd backend && venv/bin/alembic upgrade head && venv/bin/python seed_e2e.py \
  && venv/bin/uvicorn app.main:app --port 8000 &   # DATABASE_URL/DEV_MODE/SECRET_KEY 见 ci.yml
cd frontend && CI=1 npx playwright test            # 100 条（agent-isolation 需真实 Hermes，CI 下跳过）

# E2E 对生产（只跑「零写入」的套件 —— 见下方说明）
cd frontend && \
  E2E_BASE_URL=https://product-db.cn/product-db \
  E2E_API_URL=https://product-db.cn/product-db/api \
  E2E_USERNAME=tong E2E_PASSWORD=... E2E_USER_ID=2 E2E_ROLE=admin \
  npx playwright test fixes.spec.ts api-health.spec.ts core-flows.spec.ts \
    agent-isolation.spec.ts --config=playwright.prod.config.ts
```

### ⚠️ E2E 套件对生产的安全边界

| 套件 | 生产可跑 | 原因 |
|---|---|---|
| `fixes.spec.ts` | ✅ | 全部零写入或「失败也安全」（重复导入会被跳过、字典删除先确认有引用才试、报价单用不存在的方案 ID） |
| `api-health.spec.ts` | ✅ | 只读接口 + 登录 + 上传非图片（400，不落盘） |
| `core-flows.spec.ts` | ✅ | 只浏览列表/详情/检查导出按钮 |
| `agent-isolation.spec.ts` | ✅ | 需要自助注册的用例已 `test.skip(IS_REMOTE)` |
| `perf-check.spec.ts` | ❌ | 3 秒加载断言是**本地**基准，跨公网必然超时 |
| `full-regression.spec.ts` | ❌ | 含 UI 写操作（建产品、加/删字典、BOM 保存），会在生产造数据 |
| `error-scenarios.spec.ts` | ❌ | 同样含表单提交类写操作 |

## 生产部署

生产运行方式为 **systemd + nginx**（不是 Docker）：

```bash
# 前端：构建后 rsync 到服务器
cd frontend && npm run build && rsync -az --delete -e "ssh -p 28793" dist/ \
  tong@<host>:/opt/product-db/frontend/dist/

# 后端：推送后在服务器拉取并重启（带就绪门控）
git push && ssh -p 28793 tong@<host> 'cd /opt/product-db && git pull && deploy/restart-ready.sh'
```

详见 `DEPLOY.md`（含 systemd 单元、备份/健康检查 timer、加固项与回滚步骤）。

## 项目结构

```
product-db/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + 日志中间件
│   │   ├── database.py          # SQLAlchemy + JSONBType + 外键强制开关
│   │   ├── auth.py              # JWT 认证 (bcrypt) + DEV_MODE
│   │   ├── config.py            # Pydantic Settings
│   │   ├── models/              # 数据模型 (31 张 ORM 表 + 裸表 product_categories = 32 业务表)
│   │   ├── routers/             # API 路由 (14 个模块：含 agent / product_import / product_files)
│   │   ├── services/            # 业务逻辑
│   │   └── schemas/             # Pydantic 请求/响应模型
│   ├── tests/                   # pytest 测试，675 用例（674 passed + 1 skipped）
│   └── alembic/                 # 数据库迁移
├── frontend/
│   ├── src/
│   │   ├── components/          # 通用组件 (14 个, 含 GenUI 2 个)
│   │   └── views/               # 页面视图 (16 个)
│   ├── src/__tests__/           # vitest 前端测试 (98 用例)
│   └── e2e/                     # Playwright E2E (7 个 spec 套件)
├── deploy/                      # systemd 单元 + 备份/健康检查/日报脚本
├── docker-compose.yml           # 仅本地可选
└── .github/workflows/ci.yml     # CI
```

## API 概览

| 模块 | 端点示例 | 说明 |
|------|---------|------|
| 产品 | `GET/POST /api/products` | CRUD + 筛选 + 对比 + 导入/导出 + AI 识别 |
| 品类 | `GET/POST /api/categories` | 品类树 + 规格定义管理 |
| 方案 | `GET/POST /api/solutions` | BOM 管理 + 完整性检查 + 产品推荐 |
| 报价 | `GET/POST /api/quotations` | 报价 CRUD + Excel 导出 |
| BOM | `GET/POST /api/bom-templates` | 模板管理 + 快照保存/导出 |
| AI | `POST /api/ai/chat` | SSE 流式对话 + 4 工具 + GenUI 动态组件 + Quick Replies |
| 认证 | `POST /api/auth/login` | JWT (bcrypt) + 自注册 + 字段可见性 + 会话 |
| 管理 | `GET /api/admin/*` | 用户/日志/AI用量/下载审计 |

## 核心数据模型

```
products ──M2M──> dict_comm_methods      (通讯方式)
products ──M2M──> dict_comm_protocols    (通讯协议)
products ──M2M──> dict_power_supplies    (供电方式)
products ──1:M──> product_hardware_interfaces (硬件接口)
products ──M2M──> dict_sensor_metrics    (传感能力)
products ──FK──> device_categories       (品类)
products ──FK──> manufacturers           (厂商)
products ──FK──> suppliers               (供应商)
products.specs = JSONB                   (品类特有参数)
```

## 业务流

```
品类管理 → 规格定义 → 产品录入 (手动/AI识别/Excel导入)
                            │
                ┌───────────┼───────────┐
                ▼           ▼           ▼
            产品列表    产品对比    规格书生成
            (动态筛选)  (差异矩阵)  (HTML/PDF)
                │
                ▼
          选入方案 BOM → 依赖检查 → 生成报价单
                │              │
                ▼              ▼
          缺失依赖告警    自动推荐补齐
```

## License

MIT
