# 产品数据库 (product-db)

IoT 产品选型对比、规格书生成、方案设计系统。独立于 quote-system 的新项目，不限品类。

## 技术栈

| 层 | 技术 |
|----|------|
| Backend | FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2 |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Frontend | Vue 3 + TypeScript + Vite + CSS Variables |
| Icons | Lucide Icons (lucide-vue-next) |
| AI | DeepSeek API (LlmEngine async) + Tool Calling + SSE |
| Auth | JWT (python-jose) + bcrypt (passlib) + 登录频率限制 |
| XSS | DOMPurify (所有 v-html 已清洗) |
| SSRF | validate_url() + 手动重定向验证 |
| Logging | loguru (structured + rotation) |
| Testing | pytest 78 tests + vitest 22 tests |
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
npx vitest run
```

## 项目结构

```
backend/app/
├── main.py              # FastAPI 入口 + CORS + loguru 中间件
├── config.py            # Pydantic Settings (SECRET_KEY, DEV_MODE, CORS_ORIGINS...)
├── database.py          # SQLAlchemy engine + JSONBType
├── auth.py              # JWT + bcrypt (passlib) + 旧 SHA256 兼容
├── models/              # 27+ 张表 (product_categories 多对多)
│   ├── product.py, category.py       # 核心 (产品支持多品类)
│   ├── dictionary.py, mapping.py     # 字典+映射
│   ├── solution.py, quotation.py     # 方案+报价
│   ├── dependency.py, bom_template.py
│   ├── supplier.py, user.py
│   ├── ai_models.py, ai_usage_log.py # AI
│   ├── login_log.py, system_setting.py, field_setting.py
│   └── download_log.py               # 下载审计
├── routers/             # 14 个路由模块
│   ├── products.py, product_import.py
│   ├── categories.py, suppliers.py
│   ├── solutions.py, quotations.py, bom_templates.py
│   ├── ai.py, auth_routes.py, admin_routes.py
│   ├── dictionaries.py, system_settings.py
├── services/
│   ├── ai_engine.py     # LlmEngine (DeepSeek API async)
│   ├── ai_tools.py      # Tool Calling 4 工具 + Mock 回退
│   ├── ai_extract.py    # AI 产品识别提取
│   ├── product_helpers.py # 产品查询辅助 (eager loads, name maps, mappings)
│   ├── spec_service.py  # 规格校验 + 产品对比
│   ├── storage.py       # 文件管理 (路径穿越防护)
│   └── field_visibility.py # 字段可见性 (30s 缓存)
├── utils/
│   ├── security.py      # SSRF 防护 (validate_url)
│   ├── helpers.py       # apply_partial_update
│   └── escape.py        # SQL LIKE 转义
├── schemas/             # Pydantic 请求/响应模型
└── tests/               # pytest 78 tests

frontend/src/
├── App.vue              # 主布局 (暗侧边栏 + 全局搜索 + toast + 用户菜单)
├── api.ts               # 集中式 API 客户端 + SSE streamAiChat
├── router.ts            # 16 条路由 (JWT 过期检测 + admin 守卫)
├── types.ts             # TypeScript 类型定义 (Product, Category, Solution...)
├── utils/
│   └── markdown.ts      # 共享 HTML/markdown 格式化工具
├── views/               # 14 个页面视图
├── components/          # 通用组件
│   ├── AiChat.vue       # AI 浮动对话面板 (可拖拽/缩放)
│   ├── BOMSpreadsheet.vue # Univer 电子表格 (懒加载)
│   ├── DependencyGraph/Editor
│   ├── PageHeader (面包屑), Pagination, SearchInput, Modal, TagBadge, ConfirmDialog
│   └── GenUI/           # AI 动态组件
└── __tests__/           # vitest 22 tests
```

## AI 架构

```
浏览器                    FastAPI                     DeepSeek API
  │─ POST /api/ai/chat ──>│                           │
  │  {input, conv_id}     │─ run_agent (async, max 2)  │
  │                        │  ├─ build_context (60s缓存)│
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
         GenUI卡片+勾选     搜索+多选    缺件告警+推荐 (N+1 已预加载)
```

## 品类系统

- 产品支持**多品类** (product_categories 多对多中间表)
- 品类树: 传感器/网关/节点终端/安防/工具/执行器/蜂窝设备 7 个顶级
- 品类筛选面板: 分组折叠，品类+厂商默认展开，其他默认收起
- 编辑页: 品类多选标签按钮

## 关键约定

- 模型统一 `to_dict()` 方法，Product 支持 map 参数防 N+1
- 通用 partial update: `apply_partial_update(obj, data, fields)`
- DEV_MODE=True 时免登录 (自动创建 admin/admin)，生产必须 False
- SECRET_KEY 生产环境必填，否则 sys.exit(1)
- 前端 CSS 变量定义在 main.css，组件用 scoped 样式
- API 统一通过 `api.ts` → `api<T>()` 泛型函数
- SSE component 事件 → GenUI 组件动态渲染
- 密码: bcrypt (passlib) + 旧 SHA256 自动升级
- v-html 全部经 DOMPurify.sanitize() 清洗
- 字典数据 30s TTL 缓存, AI 上下文 60s TTL 缓存
