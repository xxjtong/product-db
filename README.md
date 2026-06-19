# 产品数据库

IoT 产品选型对比、规格书生成、方案设计系统。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy 2.0 |
| 数据库 | SQLite（本地）/ PostgreSQL（生产） |
| 前端 | Vue 3 + TypeScript + Vite |
| UI | CSS Variables + Lucide Icons |
| 部署 | Docker + Nginx |

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
# Backend
cd backend && pytest tests/ -v                    # 84 单元测试

# Frontend
cd frontend && npx vitest run                     # 38 组件测试
cd frontend && npx vue-tsc --noEmit               # 类型检查

# E2E (需要先启动前后端服务)
cd frontend && npx playwright test                # 75 tests (3 套件)
```

## Docker 部署

```bash
cp .env.example .env  # 编辑 SECRET_KEY 等配置
docker compose up -d
```

## 项目结构

```
product-db/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + 日志中间件
│   │   ├── database.py          # SQLAlchemy + JSONBType
│   │   ├── auth.py              # JWT 认证 (bcrypt) + DEV_MODE
│   │   ├── config.py            # Pydantic Settings
│   │   ├── models/              # 数据模型 (18 张表)
│   │   ├── routers/             # API 路由 (13 个模块)
│   │   ├── services/            # 业务逻辑
│   │   └── schemas/             # Pydantic 请求/响应模型
│   ├── tests/                   # pytest 测试 (66 用例)
│   └── alembic/                 # 数据库迁移
├── frontend/
│   ├── src/
│   │   ├── components/          # 通用组件 (10 个)
│   │   └── views/               # 页面视图 (14 个)
│   ├── src/__tests__/           # vitest 前端测试 (38 tests)
│   └── e2e/                     # Playwright E2E + API + Perf (75 tests)
├── docker-compose.yml
└── .github/workflows/ci.yml     # CI/CD
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
