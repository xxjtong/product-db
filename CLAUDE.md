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
│   ├── SolutionDetailView.vue # 方案详情 (AI 气泡 + BOM 编辑)
│   └── SolutionsView.vue     # 方案列表 (行内状态编辑)
├── components/          # 通用组件
│   ├── AiChat.vue            # AI 浮动对话面板 (可拖拽/缩放, 气泡式)
│   ├── BOMSpreadsheet.vue    # BOM HTML 表格编辑器
│   ├── DependencyGraph.vue   # Canvas 依赖关系图 (自适应)
│   ├── PageHeader, Pagination, SearchInput, Modal, TagBadge, ConfirmDialog
│   └── GenUI/                # AI 动态组件 (SolutionProductCard, QuoteDraftCard)
├── univer-bom-main.js   # Univer 全屏编辑器入口 (实验中)
└── __tests__/           # vitest 22 tests
```

## AI 架构

### 整体流程

```
用户输入 "光照+网关"
    │
    ▼
┌─ POST /api/ai/chat ──────────────────────────────────────┐
│  body: {input, conversation_id}                          │
│                                                          │
│  1. build_context() ─ 缓存300s, 拼装 system prompt        │
│     "你是产品数据库AI助手... 414产品 27品类..."             │
│                                                          │
│  2. get_messages_for_context() ─ 最近20条对话历史          │
│                                                          │
│  3. save_message(user) ─ 持久化用户消息                   │
│                                                          │
│  4. run_agent(messages, db, conv_id):                    │
│     ┌─────────────────────────────────────────────────┐ │
│     │ Round 0: Keyword Extraction                      │ │
│     │                                                  │ │
│     │  kw_system = keyword_prompt + db_ctx (300s缓存)  │ │
│     │    - db_ctx: 品类/厂商/字典/414产品全量描述+specs │ │
│     │    - size: ~98KB ≈ 44K tokens                    │ │
│     │    - prompt 存储在 system_settings 表, 管理后台可编辑│ │
│     │                                                  │ │
│     │  LLM (deepseek-v4-flash, temp=0)                 │ │
│     │    → {"keywords":["光照","网关"],"category":null, │ │
│     │       "comm_method":null,"brand":null,...}        │ │
│     │                                                  │ │
│     │  execute_tool("search_products", args)           │ │
│     │    → 多关键词: 逐词独立搜索5条 → 去重交错合并      │ │
│     │    → 单关键词: 搜5条 → per_cat=3 → 总上限5条      │ │
│     │    → 0结果: 同义词替换回退                         │ │
│     │                                                  │ │
│     │  SSE: tool事件 + products事件 + component事件      │ │
│     │  products_found = True, max_turns = 1            │ │
│     └─────────────────────────────────────────────────┘ │
│     ┌─────────────────────────────────────────────────┐ │
│     │ Round 1: Chat LLM                                │ │
│     │                                                  │ │
│     │  products_found=True → tools=None → 纯文本回复    │ │
│     │  products_found=False → tools=TOOL_DEFINITIONS    │ │
│     │                                                  │ │
│     │  LLM 失败 → 若有产品数据: 直接展示                 │ │
│     │         → 若无产品数据: fallback mock agent       │ │
│     └─────────────────────────────────────────────────┘ │
│                                                          │
│  SSE stream → 前端消费                                    │
│    connect → tool → products → component → text → done   │
└──────────────────────────────────────────────────────────┘
```

### Round 0: Keyword Extraction (核心)

在调用搜索工具之前，先用轻量 LLM 从用户输入提取结构化参数。这是整个 AI 搜索精准度的关键环节。

**DB Context (`db_ctx`)** — 300s TTL 缓存，每次关键词提取时注入 prompt：

| 数据 | 大小 | 内容 |
|------|------|------|
| 品类 | 272B | 27 个品类名 |
| 厂商 | 412B | 47 个厂商名 |
| 字典表 | 407B | 通讯方式/协议/供电/传感器指标 |
| 产品列表 | ~95KB | 414 个产品的 名称(型号): 描述前120字 [top8 specs] |

总计约 98KB ≈ 44K tokens。DeepSeek 自动 prompt caching 命中后 system 部分按 10% 计费。

**提取的 JSON schema**：

```json
{
  "keywords": ["光照", "网关"],   // 必填, LLM自主拆词
  "category": null,               // 仅用户明确说出才填
  "comm_method": null,            // LoRaWAN/WiFi/Ethernet/4G/5G...
  "protocol": null,               // MQTT/HTTP/ModbusRTU...
  "power": null,                  // DC/PoE/Battery...
  "brand": null,                  // 厂商名, 必须来自DB
  "min_price": null,              // 数字, 未提则null
  "max_price": null,              // 数字, 未提则null
  "sort_by": null                 // price_asc / price_desc
}
```

**Prompt 管理**：`ai_keyword_prompt` 存储在 `system_settings` 表，通过 `/admin/ai-settings` API 在管理后台在线编辑。同义词映射（漏水→水浸, 感应器→传感器, 无线→WiFi 等）同时在 prompt 规则和代码 `synonym_map` 两处维护。

### Round 1: Chat LLM + 工具调用

4 个工具定义在 `ai_tools.py`，tool calling 最多 2 轮：

| 工具 | 功能 | 关键逻辑 |
|------|------|---------|
| `search_products` | 多关键词搜索 | 逐词独立搜5条→去重交错合并；同义词回退；价格/排序过滤 |
| `get_product_detail` | 单品完整 specs | 含通讯/协议/供电/硬件接口/传感器能力 |
| `list_categories` | 列出所有品类 | |
| `create_quotation` | 从方案创建报价单 | 含产品快照 |

### 搜索结果策略

| 场景 | 行为 |
|------|------|
| 单关键词 | LIKE 匹配 → 0结果则同义词替换 → per_cat=3 → 总上限5条 |
| 多关键词 | 每词独立搜5条 → 去重 → 交错合并（每轮从各词取1条）→ 无总上限 |
| 精确匹配失败 | 同义词聚合替换（漏水→水浸 AND 感应器→传感器 → "水浸传感器"） |
| API 无 key | Mock agent 关键词回退 |
| LLM 调用失败 | 已有产品则直接展示，无则 fallback mock |

### 降级与容错

```
API key 存在?
  ├─ Yes → Round 0 keyword LLM
  │         ├─ 成功 → Round 1 chat LLM
  │         │         ├─ 成功 → 流式文本回复
  │         │         └─ 失败 → products_found? 展示产品 : mock
  │         └─ 失败 → Round 1 chat LLM (with tools)
  │                   └─ 失败 → products_found? 展示产品 : mock
  └─ No  → mock agent (关键词匹配)
```

### 对话管理

- `AIConversation` 表：user_id + title + updated_at
- `AIMessage` 表：role(user/assistant/system/tool), content, tool_calls(JSON), tool_call_id
- 每次请求加载最近 20 条消息作为上下文
- 首条消息自动截取前 30 字作为对话标题
- `ai_usage_logs` 表异步记录每次调用的 token 用量（线程池写入，WAL 安全）
- AI 统计数据通过 `GET /api/ai/stats` 获取（总调用次数 + token 汇总）

### SSE 事件流

| 事件 | 触发时机 | 前端处理 |
|------|---------|---------|
| `connect` | 连接建立 | 设置 conversation_id |
| `tool` | 执行工具前 | 显示 "搜索 XXX..." |
| `products` | 搜索到产品 | 渲染产品卡片列表 |
| `component` | GenUI 动态组件 | `<component :is>` 渲染 SolutionProductCard/QuoteDraftCard |
| `text` | LLM 流式文本 | 逐字符追加到气泡 |
| `done` | 本轮结束 | tokens 统计, quick_replies |
| `quick_replies` | 有产品结果时 | "对比产品" / "全部加入方案" |

### 前端双入口

| 入口 | 位置 | 特点 |
|------|------|------|
| `AiChat.vue` | 全局右下角浮动 FAB | 可拖拽/缩放, 独立对话列表 |
| `SolutionDetailView.vue` | 方案详情页内嵌 | 产品卡片含"加入方案"按钮, 气泡式布局 |

## 方案 (Solution) 工作流

```
创建方案 → AI 助手选品 → 批量加入 BOM → 依赖检查 → 生成报价单
              │                  │            │
         GenUI卡片+勾选     搜索+多选    缺件告警+推荐 (N+1 已预加载)
              │
         BOM 表格编辑器 (HTML table, 内联编辑+保存+导出xlsx)
```

## 品类系统

- 产品支持**多品类** (product_categories 多对多中间表)
- 品类树: 传感器/网关/节点终端/安防/工具/执行器/蜂窝设备等 27 个品类
- 品类筛选面板: 分组折叠，品类+厂商默认展开，其他默认收起
- 编辑页: 品类多选标签按钮
- 更新 `category_ids` 时自动同步 `category_id` 单列

## 前端关键组件

| 组件 | 功能 |
|------|------|
| `AiChat.vue` | AI 浮动对话面板 (可拖拽/缩放, 气泡式) |
| `SolutionDetailView.vue` | 方案详情 (客户信息 + AI 方案助手 + 产品清单 + 依赖图 + BOM 编辑器) |
| `BOMSpreadsheet.vue` | BOM HTML 表格编辑器 (内联编辑/保存/导出/模板) |
| `DependencyGraph.vue` | Canvas 依赖关系图 (ResizeObserver 自适应) |
| `SolutionsView.vue` | 方案列表 (行内状态下拉框) |
| `GenUI/` | AI 动态组件 (SolutionProductCard, QuoteDraftCard) |

## BOM 表格编辑器

- HTML 表格实现，点击单元格直接编辑
- 列: 序号/产品名称/型号SKU/数量/单价/折扣%/小计/备注 + 合计行
- 按钮: 重新加载/保存/导出xlsx/另存为模板
- 500px 最大高度，超出滚动
- 保存时将编辑数据转为快照格式写入 `solution_bom_snapshots` 表

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
- 方案列表状态可直接行内下拉修改（草稿/进行中/完成）
- AI 方案助手使用气泡式对话布局（用户右侧蓝色，AI 左侧灰色）
