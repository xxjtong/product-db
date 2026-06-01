# 产品数据库 (product-db)

IoT 产品选型对比、规格书生成、方案设计系统。

## 技术栈

- Backend: FastAPI + SQLAlchemy 2.0 + SQLite + Alembic + Pydantic
- Frontend: Vue 3 + TypeScript + Vite + CSS Variables + Lucide Icons
- AI: DeepSeek API (LlmEngine) + Tool Calling + SSE
- Auth: JWT (python-jose) + bcrypt (passlib) + DEV_MODE fallback
- Logging: loguru (structured, rotation)
- Testing: pytest 66 tests + vitest (frontend)

## 项目结构

```
backend/          — FastAPI 后端 (13 个路由模块, 18 张表, 3 个 services)
frontend/         — Vue 3 前端 (14 个 views, 10 个 components)
```

## 开发命令

```bash
# 后端 (在 backend/ 目录)
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
python -m pytest tests/ -v

# 前端 (在 frontend/ 目录)
npx vite --host 0.0.0.0 --port 5173
npx vue-tsc --noEmit
npx vitest run
```

## 关键约定

- CRUD 更新使用 `for f in [fields]: if f in data: setattr(obj, f, data[f])` 模式
- 模型统一有 `to_dict()` 方法
- 认证中间件: DEV_MODE 下免登录自动创建 admin 用户
- 前端 CSS 变量定义在 `main.css`，组件用 scoped 样式
- 图标使用 Lucide Icons (lucide-vue-next)
- API 调用统一通过 `api.ts` 的泛型 `api<T>()` 函数
- AI 搜索使用先精确匹配后 bigram 回退的策略

## 数据流

- 产品通过 M2M 映射表关联通讯方式/协议/供电
- specs JSONB 存储品类特有参数，由 category_spec_definitions 驱动表单
- 方案 BOM → 依赖检查 → 报价单 snapshot 模式
