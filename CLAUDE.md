# 产品数据库 (product-db)

IoT 产品选型对比、规格书生成、方案设计系统。独立于 quote-system 的新项目，不限品类。

## 技术栈

| 层 | 技术 |
|----|------|
| Backend | FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2 |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Frontend | Vue 3 + TypeScript + Vite + CSS Variables |
| Icons | Lucide Icons (lucide-vue-next) |
| AI | DeepSeek API (LlmEngine) + Tool Calling + SSE |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Logging | loguru (structured + rotation) |
| Testing | pytest 66 tests + vitest |
| Deployment | Docker Compose + Nginx |

## 开发命令

```bash
# 后端
cd backend && source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pytest tests/ -v

# 前端
cd frontend
npx vite --host 0.0.0.0 --port 5173
npx vue-tsc --noEmit
npx vitest run
```

## 项目结构

```
backend/app/
├── main.py              # FastAPI 入口 + CORS + loguru 中间件
├── config.py            # Pydantic Settings (SECRET_KEY 必填, DEV_MODE)
├── database.py          # SQLAlchemy engine + JSONBType
├── auth.py              # JWT + bcrypt (passlib) + 旧 SHA256 兼容
├── models/              # 27 张表
│   ├── product.py, category.py       # 核心
│   ├── dictionary.py, mapping.py     # 字典+映射
│   ├── solution.py, quotation.py     # 方案+报价
│   ├── dependency.py, bom_template.py
│   ├── supplier.py, user.py
│   ├── ai_models.py, ai_usage_log.py # AI
│   ├── login_log.py, system_setting.py, field_setting.py
│   └── download_log.py               # 下载审计
├── routers/             # 13 个路由模块
│   ├── products.py, product_import.py, product_specs.py
│   ├── categories.py, suppliers.py
│   ├── solutions.py, quotations.py, bom_templates.py
│   ├── ai.py, auth_routes.py
│   ├── dictionaries.py, system_settings.py
├── services/
│   ├── ai_engine.py     # LlmEngine (DeepSeek API 直连)
│   ├── ai_tools.py      # Tool Calling 4 工具 + Mock 回退
│   ├── spec_service.py  # 规格校验 + 产品对比
│   ├── storage.py       # 文件管理
│   └── field_visibility.py # 字段可见性 (30s 缓存)
├── schemas/             # Pydantic 请求/响应模型
└── tests/               # pytest 66 tests

frontend/src/
├── App.vue              # 主布局 (暗侧边栏 + 内容 + AiChat 浮动面板)
├── api.ts               # 集中式 API 客户端 + SSE streamAiChat
├── router.ts            # 16 条路由
├── views/               # 14 个页面视图
├── components/          # 通用组件 (10 个)
│   ├── AiChat.vue       # AI 浮动对话面板 (可拖拽/缩放)
│   ├── BOMSpreadsheet.vue # Univer 电子表格
│   ├── DependencyGraph/Editor
│   ├── PageHeader, Pagination, SearchInput, Modal, TagBadge, ConfirmDialog
│   └── GenUI/           # AI 动态组件
│       ├── SolutionProductCard.vue  # 产品推荐卡片 (勾选+数量+加入方案)
│       └── QuoteDraftCard.vue       # 报价摘要卡片
└── __tests__/           # vitest 前端测试
```

## AI 架构

```
浏览器                    FastAPI                     DeepSeek API
  │─ POST /api/ai/chat ──>│                           │
  │  {input, conv_id}     │─ run_agent (max 2 turns)  │
  │                        │  ├─ build_context (DB动态)│
  │                        │  ├─ engine.chat() ───────>│
  │                        │  ├─ execute_tool()        │
  │                        │  └─ save_message()        │
  │<─ SSE events ─────────│                           │
  │  connect → tool →     │                           │
  │  products → component │  GenUI: SolutionProductCard│
  │  → text → done →      │         QuoteDraftCard    │
  │  quick_replies         │                           │
```

4 个 AI 工具: `search_products`, `get_product_detail`, `list_categories`, `create_quotation`
搜索策略: 先精确匹配 → 无结果则 bigram 回退
Mock 回退: 无 API key 时自动关键词匹配

## 方案 (Solution) 工作流

```
创建方案 → AI 助手选品 → 批量加入 BOM → 依赖检查 → 生成报价单
              │                  │            │
         GenUI卡片+勾选     搜索+多选    缺件告警+推荐
```

## 关键约定

- 模型统一 `to_dict()` 方法，Product 支持 map 参数防 N+1
- CRUD 更新: `for f in [fields]: if f in data: setattr(obj, f, data[f])`
- DEV_MODE=True 时免登录 (自动创建 admin/admin)，生产必须 False
- SECRET_KEY 生产环境必填，否则 sys.exit(1)
- 前端 CSS 变量定义在 main.css，组件用 scoped 样式
- API 统一通过 `api.ts` → `api<T>()` 泛型函数
- SSE component 事件 → GenUI 组件动态渲染
- 密码: bcrypt (passlib) + 旧 SHA256 自动升级
