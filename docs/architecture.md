# product-db 架构总览

IoT 产品选型对比、规格书生成、方案设计系统。独立项目，不限品类。

## 规模

| 维度 | 数量 |
|------|------|
| Python 文件 | 62 个 (6,819 行) |
| TypeScript/Vue/CSS | 38 个 (734 行) |
| API 端点 | ~85 个 |
| 数据库表 | 33 张 |
| 产品 | 392 个 |
| 测试 | pytest 129 + vitest 60 + E2E 92 |

## 技术栈

```
前端:   Vue 3 (Composition API + <script setup>)
        TypeScript + Vite 5
        Vue Router 4 (history mode)
        Lucide Icons + DOMPurify
        Custom CSS Variables (无框架)

后端:   FastAPI + Uvicorn
        SQLAlchemy 2.0 ORM + Pydantic v2
        Alembic (数据库迁移)
        SQLite (dev) / PostgreSQL (prod)
        JWT (PyJWT 2.13) + bcrypt (direct)
        loguru (结构化日志)

AI:     DeepSeek API (LlmEngine async)
        SSE 流式响应 + Tool Calling (4 tools)
        Prompt 缓存 300s TTL

部署:   Docker Compose + Nginx
        路径前缀: /product-db/
```

## 项目结构

```
backend/app/
├── main.py              # FastAPI 入口 + CORS + loguru 中间件
├── config.py            # Pydantic Settings
├── database.py          # SQLAlchemy engine + JSONBType
├── auth.py              # JWT + bcrypt + SHA256 兼容 + 权限过滤
├── models/              # 18 文件, 33 张表
│   ├── product.py, category.py, dictionary.py
│   ├── solution.py, quotation.py, bom_template.py
│   ├── dependency.py, supplier.py, user.py
│   ├── ai_models.py, ai_usage_log.py
│   ├── login_log.py, download_log.py
│   ├── product_file.py, mapping.py
│   └── system_setting.py, field_setting.py
├── routers/             # 14 个路由模块
│   ├── products.py, categories.py
│   ├── solutions.py, quotations.py
│   ├── dictionaries.py, suppliers.py
│   ├── ai.py, auth_routes.py, admin_routes.py
│   ├── product_files.py, product_import.py
│   ├── bom_templates.py, system_settings.py
├── services/            # 10 个服务模块
│   ├── ai_engine.py, ai_tools.py, ai_extract.py
│   ├── product_helpers.py, product_category_helper.py
│   ├── spec_service.py, spec_generator.py
│   ├── storage.py, field_visibility.py
├── schemas/             # 10 个 Pydantic 模式
├── utils/
│   ├── security.py      # SSRF 防护
│   ├── helpers.py       # apply_partial_update
│   └── escape.py        # SQL LIKE 转义
└── tests/               # pytest 129 tests (test_api.py + test_utils.py + test_agent_admin_files.py)

frontend/src/
├── App.vue              # 主布局 (侧边栏 + 搜索 + toast)
├── api.ts               # 集中式 API 客户端 + SSE
├── router.ts            # 16 条路由 (JWT 过期 + admin 守卫)
├── types.ts             # TypeScript 类型定义
├── utils/markdown.ts    # 共享格式化工具
├── views/               # 14 个页面视图
│   ├── ProductsView, ProductFormView, ProductDetailView
│   ├── SolutionsView, SolutionDetailView
│   ├── QuotationsView, QuotationDetailView
│   ├── DictionariesView, CategoriesView
│   ├── SuppliersView, ImportView
│   ├── ProductCompareView, AdminView, LoginView
├── components/          # 11 个通用组件
│   ├── AiChat.vue            # 浮动 AI 对话面板 (可拖拽)
│   ├── BOMSpreadsheet.vue    # HTML 表格编辑器
│   ├── DependencyEditor.vue  # 产品依赖管理
│   ├── DependencyGraph.vue   # Canvas 依赖关系图
│   ├── ProductFiles.vue      # 文件上传/下载/预览
│   ├── PageHeader, Pagination, SearchInput
│   ├── Modal, ConfirmDialog, TagBadge
│   └── GenUI/                # AI 动态组件
└── __tests__/           # vitest 60 tests (aiChat + api + components + mdToHtml + views)
```

## 后端分层架构

### 路由层 (14 模块)

| 路由 | 端点前缀 | 职责 |
|------|---------|------|
| `products.py` | `/products` | CRUD + AI 提取 + 图片 + 导出 |
| `categories.py` | `/categories` | 树形品类 + 规格定义 |
| `solutions.py` | `/solutions` | 方案 CRUD + 行内编辑 |
| `quotations.py` | `/quotations` | 报价单 CRUD + BOM + xlsx |
| `dictionaries.py` | `/dicts` | 厂商/通讯/协议/供电/传感器 |
| `suppliers.py` | `/suppliers` | 供应商管理 |
| `ai.py` | `/ai` | SSE 对话 + 对话管理 + 统计 |
| `auth_routes.py` | `/auth` | 登录/注册/JWT/Profile |
| `admin_routes.py` | `/admin` | 用户/系统/AI/日志管理 |
| `agent.py` | `/agent` | Hermes Agent 代理(SSE) + 文件上传 + 审批 |
| `product_files.py` | `/products/{id}/files` | 文件上传/下载/删除 |
| `product_import.py` | `/products/import` | 批量导入 |
| `bom_templates.py` | `/bom-templates` | BOM 模板 + 快照 |
| `system_settings.py` | `/system` | 系统配置 |

### 服务层 (10 模块)

| 服务 | 职责 |
|------|------|
| `ai_engine.py` | DeepSeek API 异步调用封装 |
| `ai_tools.py` | Tool Calling 4 工具 |
| `ai_extract.py` | AI 产品信息提取 + Regex 回退 |
| `approval_manager.py` | Human-in-the-loop 审批(asyncio.Event 挂起) |
| `product_helpers.py` | 产品查询 eager loads + 名称映射 |
| `product_category_helper.py` | 多对多品类统一操作 (消除 6 处 raw SQL) |
| `spec_service.py` | 规格校验 + 产品对比 |
| `spec_generator.py` | HTML/PDF 规格书生成 |
| `storage.py` | 文件管理 (UUID + 路径穿越防护) |
| `field_visibility.py` | 字段可见性 (30s TTL 缓存) |

## 前端架构

### 路由 (16 条)

```
/login              → LoginView.vue
/products           → ProductsView.vue         (列表 + 筛选)
/products/new       → ProductFormView.vue      (新增)
/products/:id       → ProductDetailView.vue    (详情 + 编辑)
/products/compare   → ProductCompareView.vue   (对比)
/products/import    → ImportView.vue           (导入)
/solutions          → SolutionsView.vue        (方案列表)
/solutions/:id      → SolutionDetailView.vue   (方案详情 + AI)
/quotations         → QuotationsView.vue       (报价单列表)
/quotations/:id     → QuotationDetailView.vue  (报价单详情 + BOM)
/categories         → CategoriesView.vue       (品类管理)
/dictionaries       → DictionariesView.vue     (6 tab 字典)
/suppliers          → SuppliersView.vue        (已并入字典)
/admin              → AdminView.vue            (管理后台)
/agent              → AgentView.vue            (Hermes Agent 全屏对话 + 文件上传 + 审批)
```

### 组件通信

```
App.vue (root)
├── SidebarNav          → 导航 + AI 统计
├── GlobalSearch        → 全站搜索
├── ToastSystem         → provide/inject
└── <router-view>
    ├── PageHeader      → props: title, breadcrumb
    ├── AiChat          → 全局浮动, 可拖拽缩放
    ├── BOMSpreadsheet  → props: solutionId|quotationId
    └── Modal/ConfirmDialog → v-model:visible
```

### 数据流

```
API 层 (api.ts)
  api<T>()           → 统一 JWT + 错误处理 + JSON 泛型
  streamAiChat()     → SSE ReadableStream 消费
  uploadProductImage → FormData + resp.ok 检查

View 层 (Composition API)
  ref()/reactive()   → 本地状态 (无 Pinia)
  onMounted()        → API 调用 → 数据绑定
  URL query params   → 搜索/筛选/翻页 状态持久化
```

## AI 架构

### 对话流程

```
用户输入 → POST /api/ai/chat (SSE)
  │
  ├─ Round 0: 关键词提取 (deepseek-chat, temp=0)
  │   ├─ db_ctx: 414 产品全量描述 ~98KB (300s TTL)
  │   ├─ 输出: {keywords, matches: {关键词: [产品ID]}}
  │   └─ 代码验证 → DB 取数据 → 去重 → 交错合并
  │
  └─ Round 1: Chat LLM (deepseek-v4-flash)
      ├─ products_found → 文本回复
      └─ 无产品 → 4 工具调用 → mock 回退

SSE 事件: connect → tool → products → component → text → done
```

### 产品提取

```
POST /api/products/ai-fetch
  URL  → httpx → BeautifulSoup → 文本
  PDF  → PyPDF2 → 文本
  docx → python-docx → 文本
  → call_ai_extract() → DeepSeek JSON
  → regex_extract_from_text() → 正则回退
```

### 降级链

```
API key?
  ├─ Yes → LLM keyword → LLM chat → 展示
  │         └─ 失败 → regex fallback (有日志)
  └─ No  → mock agent (关键词 SQL LIKE)
```

## 权限系统

```
filter_by_ownership(query, model, user)
  admin  → 看全部
  普通用户 → NULL (legacy) / user.id (自己) / 1 (admin)

check_ownership(item, user)
  admin  → 通过
  普通   → 非自己创建 → 403

8 张表含 created_by: Product, Category, Manufacturer, Supplier,
  DictCommMethod, DictCommProtocol, DictPowerSupply, DictSensorMetric

所有 PUT/DELETE 端点覆盖 check_ownership() (11 处)
```

## 安全措施

| 措施 | 实现 |
|------|------|
| 认证 | JWT + bcrypt (SHA256 自动升级) |
| 权限 | filter_by_ownership + check_ownership (全覆蓋) |
| XSS | DOMPurify.sanitize() 所有 v-html |
| SSRF | validate_url() + 手动重定向验证 |
| SQL 注入 | SQLAlchemy 参数化 (product_category_helper 统一) |
| 文件 | Magic bytes + 扩展名白名单 + 大小预检 |
| 路径 | UUID 重命名 + file:// 禁止 |
| 速率 | 登录频率限制 (IP-based) |
| 日志 | loguru 结构化 + 所有 except 有 log |

## 关键设计决策

1. **不用 Pinia** — `ref()/reactive()` 本地状态, 页面独立
2. **多对多品类** — `product_categories` 中间表, 遗留 `category_id` 逐步废弃
3. **BOM HTML table** — contenteditable, 不用第三方库
4. **CSS Variables** — 无框架纯自定义, `main.css` 统一定义
5. **全链路前缀** — `/product-db/` 透传 (Nginx proxy_pass 无末尾斜杠)
6. **Spec key 中文化** — 全局: `防护等级` 非 `ip_rating`
7. **DEV_MODE** — 免登录 admin/admin, 本地开发用
8. **快照 > 实时引用** — 报价单 product_snapshot 防止历史数据漂移

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
npx vue-tsc --noEmit

# 部署
git pull → npm run build → systemctl restart product-db
```
