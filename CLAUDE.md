# 产品数据库 (product-db)

IoT 产品选型对比、规格书生成、方案设计系统。独立于 quote-system 的新项目，不限品类。

## 最新变更 (2026-07-06, R21)

### R21: 时区显示修复 + 端口统一 + 环境配置完善

**时区显示修复:**
- 新增 `frontend/src/utils/time.ts` — `formatTime()` 统一将 UTC 时间转本地时区显示
- 10 处 raw `created_at`/`updated_at` → `formatTime()`
- SQLite 存 UTC 但返回 naive datetime（无时区戳），JS 按本地时区解析 → 显示晚 8 小时
- 修复：`formatTime` 检测 naive ISO 自动追加 `Z` 后缀，强制 UTC 解释
- AgentView 删除本地 `formatTime`，统一用共享版

**端口统一 (8002→8000):**
- 生产 systemd + Nginx 端口改为 8000，与开发环境一致
- CLAUDE.md 同步更新
- CLAUDE.md 同步更新

**环境配置:**
- `.env.example` 补全 24 个配置项（含注释），新机器 `cp .env.example .env` 即可
- Vite 启动命令改为 `npm run dev`，锁定项目 Vite 6.x（全局 Vite 8 不兼容）

**测试:** vue-tsc 0 errors / vitest 60/60

## 历史变更 (2026-07-06, R20)

### R20: API Key 统一 + 搜索评分优化 + UX 增强

**API Key 统一管理 (.env only):**
- `ai_engine.py`: 删除 DB 查 key 逻辑，仅用构造参数 → `.env` `AI_GATEWAY_KEY`
- `admin_routes.py`: `_LLM_CONFIG_DEFAULTS` 去 `api_key`；`_load_llm_config` 过滤 key；`update_llm_config` 保存前剔除；`test_llm_config` vision 测试用 `VISION_API_KEY`
- `products.py` `_ocr_image`: 改用 `.env` `VISION_API_KEY`（不再 fallback 到主 key）
- `config.py`: 新增 `VISION_BASE_URL`/`VISION_MODEL`/`VISION_API_KEY`
- DB `llm_config`: 清除存储的 `api_key`
- 前端 AdminView: API Key 输入框改为禁用 + `.env` 提示

**AI 搜索评分优化:**
- `ai.py` Round 0 关键词提取：prompt 加优先级规则（name>品类标签>描述）；LLM 匹配后 thin(≤3)时补 SQL 搜索合并
- `ai.py` mock agent: 拆分复合词为多关键词（"lorawan网关"→["lorawan","网关"]）
- `ai_tools.py`: 多关键词改评分制（name=3/model=2/desc=1）替代交错合并；候选池扩大到 limit×3；单关键词也加评分排序
- 搜索"lorawan网关"之前返回智能开关面板(描述含"兼容LoRaWAN网关")，现在返回真正的网关产品

**401 降级提示:**
- `ai.py`: LLM 401 时 yield warning 事件
- `api.ts` + `SolutionDetailView.vue`: 前端消费 warning 事件，黄色警告条展示

**UX 增强:**
- `SolutionsView.vue`: 新增方案对话框名称字段下移，客户+项目联动生成名称（`客户-项目`），手动编辑后断开联动
- `SolutionDetailView.vue` 批量选品: 搜索支持厂商/品类/名称/型号过滤；移除 6 项上限；产品行新增厂商列

**Bug 修复:**
- 首页 404: 服务器 `/opt/product-db/static/` 目录丢失，`git clean -fd` 清掉 untracked 目录 → `static/coming-soon.html` 入 git
- `admin_routes.py` `cfg[k].pop()` 加 `isinstance` 检查防类型错误
- `ai_tools.py:185` `escape_like(kw)` 错误用于 Python 字符串匹配 → 改用 `kw.lower()`

**测试:** Backend import OK / Frontend vue-tsc 0 errors / AI 对话 3 场景验证通过

## 历史变更 (2026-07-01, R19)

### R18: 安全加固 — 权限收敛 + 漏洞修复 + 代码质量

**权限收敛 (5 项):**
- products.py PUT/DELETE: `check_ownership(strict=True)` — 普通用户只能改/删自己产品
- product_files.py 4 端点: 全部加产品所有权检查（读→view, 写→strict）
- bom_templates.py 5 端点: BOM 模板/快照加所有权检查
- system_settings.py GET: 加 admin 检查
- cleanup-uploads: 加 admin 检查

**安全漏洞修复 (5 项):**
- S2: JWT `?token=` 限制仅 GET 请求
- S5: SHA256 遗留哈希加 warning log（自动升级已在 auth_routes）
- S7: BOM 模板删除缺 `check_ownership` → 已补
- agent.py LIKE 注入: keyword + manufacturer_name 加 `escape_like()`
- `check_ownership` strict 模式修复: NULL 旧数据拒绝写入，admin 判断改用 `_get_admin_ids()`

**代码质量 (6 项):**
- M1: 10 model 文件 + 6 router 文件 `datetime.now()` → `datetime.now(timezone.utc)`
- D1: python-jose → PyJWT 2.13, 移除 ecdsa/rsa/pyasn1 依赖
- B1: 17 个 POST 创建端点 → `status_code=201`
- B3: AI/Agent 3 端点 raw dict → Pydantic schema (`schemas/ai.py`)
- F6: api.ts 23 处 `data: any` → `Record<string, unknown>`, 返回类型修正
- M2: 8 张表 `created_by` 列加 `index=True`

**前端 (3 项):**
- F10: AiChat.vue 删除 48 行死代码 `mdToHtml`
- F15: 404 路由 + NotFoundView.vue
- F17: SolutionDetailView 流式渲染 50ms 节流（减少 ~90% 重渲染）
- 登录页: 注册字段填写说明 + 注册关闭时隐藏链接

**测试:** backend pytest 84/84, frontend vue-tsc 0 errors

**变更统计:** 36 文件, ~250 insertions, ~240 deletions

### R17: 功能描述增强 + 安全加固 + E2E 测试 + 代码优化

**功能: 功能描述包含全部规格参数**
- `format_description_with_specs()` 统一 helper（后端 Python + 前端 TypeScript）
- 方案页/报价单 HTML 预览表格"功能描述"列 = 描述文字 + 全部规格参数（`K:V | K:V` 格式）
- 自动剥离描述中产品 URL（`https?://\S+`）
- HTML 单行截断（`nowrap + ellipsis`），tooltip 显示全内容
- 下载 Excel 保留完整功能描述（移除 `[:200]` 截断）
- 3 种导出覆盖：报价单/产品清单/BOM

**安全加固 (4 项):**
- passlib → bcrypt 直接调用（passlib 停止维护，bcrypt 5.0 不兼容）
- Excel 图片嵌入 SSRF：`_resolve_image()` 加 `validate_url()`
- Agent 工具 `get_product_detail` 移除 `cost_price`（`agent.py` + `ai_tools.py` 双处）
- 移除 `requirements.txt` 中 passlib 依赖

**代码优化:**
- 删除 `univer-bom-main.js` 死代码（897 行）+ 18 Univer npm 包（-73 依赖）
- `flattenTree` 去重 → 提取到 `markdown.ts`，ProductFormView/ProductsView 共享
- `BOMSpreadsheet.vue` token `encodeURIComponent`
- `SolutionItem.to_dict()` 移除未使用的 `product_specs` 字段
- 后端/前端分隔符统一为 `|`（原 `\n` vs `|` 不一致）
- Python `import re` 移至模块顶部
- TypeScript `getDesc()` 移除 `any` 类型

**测试框架:**
- Playwright E2E 框架搭建（`playwright.config.ts` + `e2e/core-flows.spec.ts`）
- E2E 测试：产品列表 → 方案 → 报价单 → 功能描述验证 → 导出按钮
- 关键技术：`addInitScript` 在 SPA 加载前注入 token

**全量代码评审:**
- 后端：6 严重 / 17 中等 / 7 性能
- 前端：2 严重 / 12 中等 / 10 新发现
- 评审报告：`docs/review-R17-2026-06-18.md`

**测试结果:**
- Backend pytest: 84/84 pass
- Frontend vitest: 38/38 pass
- vue-tsc: 0 errors
- Playwright E2E: 1/1 pass (6.3s)

**变更统计:** 23 文件, +370/-3915 行

### R17.1: 后端 Bug 修复 + E2E 测试全覆盖 (2026-06-19)

**Bug 修复 (4 项):**
- **`_extract_product_info` async bug**（严重）: `products.py` 中 `_extract_product_info` 从 `ai_fetch_file`（async route）调用时使用 `asyncio.run()`，在已有事件循环中抛 `RuntimeError`，被 `except Exception: pass` 静默吞掉 → 文件上传的 AI 提取从未真正调用 LLM，始终静默降级到 regex。修复：函数改为 `async def`，`asyncio.run()` → `await engine.chat()`
- **`_ocr_image` 同步阻塞**: 去掉 `requests.post` + `ThreadPoolExecutor`，改用 `httpx.AsyncClient`
- **图片上传硬编码 5MB**: 两处 `5 * 1024 * 1024` → `settings.IMAGE_MAX_SIZE`
- **`update_quotation_item` 一致性**: 手动 `for f in [...]` + `setattr` → `apply_partial_update()`

**E2E 测试全覆盖:**
- 3 个测试套件，**75 个测试，100% 通过**
- `e2e/full-regression.spec.ts`（51 tests）：17 个功能组全覆盖
- `e2e/api-health.spec.ts`（19 tests）：19 个 API 端点直连验证
- `e2e/perf-check.spec.ts`（4 tests）：性能 + 可访问性 + console 错误检测

**测试结果:**
- Backend pytest: 84/84 pass
- Frontend vitest: 38/38 pass
- vue-tsc: 0 errors
- Playwright E2E: 75/75 pass（全功能 2.6m + API 1.4s + Perf 14.6s）

**变更统计:** 4 文件, +560/-40 行

## 历史变更 (2026-06-17, R17-prior)

## 历史变更 (2026-06-17, R17-prior)

### R17-prior: Agent 全功能完善 — 文件上传 + 审批 + API 认证 + 工具定义

**文件上传 & 处理:**
- `POST /agent/upload` — 文件保存到 `uploads/` 目录，UUID 重命名，返回公开 URL
- 支持图片粘贴/拖拽/选择三种方式，`useFileDrop.ts` composable 复用（AgentView + AiExtractCard）
- 非图片文件显示文档图标 chip，图片显示缩略图
- 文件路径自动注入 system prompt（`{{UPLOAD_DIR}}`），Hermes 用 terminal 直接读
- 气泡下方显示可点击文件链接 chip，消息正文不显示文件路径
- `POST /agent/cleanup-uploads` — 清理 >7 天旧文件

**Human-in-the-loop 审批:**
- `approval_manager.py` — asyncio.Event 挂起等待，120s 超时
- `POST /agent/approval/{task_id}` — 人类决策端点
- 审批以对话内嵌消息形式呈现（授权执行/拒绝按钮），非弹窗
- 测试触发词 "测试审批" 模拟 `create_quotation` 完整审批链
- Hermes 设 `yolo` 模式，内部工具自动批准

**Agent 工具定义:**
- `AGENT_TOOLS` 4 个工具：search_products / get_product_detail / create_quotation / create_solution
- `_execute_tool()` 读工具直接执行（SQLite 查询），写工具需审批
- `_call_hermes()` 支持 `tools` 参数透传

**REST API 认证 & 查询:**
- prompt 中 `{{TOKEN}}` 替换为用户 JWT，API 请求带 `?token=` 参数
- prompt 加入方案/报价单完整 CRUD 指引
- 厂商查询链路：先获取厂商 ID → 再按 `manufacturer_id` 查询产品

**UI 优化:**
- ICP 页脚：全站 `position: static` 文档流底部
- Agent 流式：静态头像 + ▊ 高频闪烁光标 + "思考中" 淡入淡出
- 文件上传按钮：通用附件图标，不限文件类型
- 登录页无需滚动即可见 ICP 页脚

**部署 & 配置:**
- `config.py` 新增：`AGENT_API_BASE`, `DATABASE_PATH`, `AGENT_UPLOAD_DIR`
- `GET /agent/config` 返回：`db_path`, `api_base`, `upload_dir`
- pdb Hermes `command_allowlist` + `execute_code`
- 前端部署：`rm -rf assets/` 后 `scp dist/*` 到 `frontend/dist/`
- coming-soon.html 添加 ICP 页脚

## 历史变更 (2026-06-17, R16)

### R16: Agent prompt DB 化 + API 查询引导 + 流式动画 + ICP 页脚

### R15: Hermes Agent 全屏对话页 (2026-06-16)
- DOMPurify XSS 防护

**交互功能:**
- SSE 流式输出 + AbortController 中断
- 呼吸脉冲动画指示 agent 工作中
- Enter 发送 / Shift+Enter 换行
- 侧边栏 5 个建议问题快捷入口
- 每条回复底部显示 token 统计（输入/输出/合计）
- `/agent` 页自动隐藏 AiChat 浮动 FAB

**侧边栏:**
- 新增 Agent 入口（Bot 图标）介于报价单和字典之间

**修复 (评审):**
- 1 关键: `renderTable()` 在 `\n`→`<br>` 之后调用 → 移到之前
- 2 关键: 表头 `thead` 计算后未输出 → 补回 `${thead}`
- 1 死代码: `RE_TABLE_ROW` 未使用 → 删除
- 1 bug: bullet 列表 `$2` → `$1`（单捕获组）
- 1 安全: API key 硬编码 → `process.env.VITE_HERMES_API_KEY` + dev 默认值
- 2 优化: 流式图标动画 + token 统计

**范围:** 纯前端，后端 0 改动

**测试:** vue-tsc 0 errors / vitest 38/38 / vite build 成功 / Playwright E2E 浏览器实测通过

## 历史变更 (2026-06-15, R14)

### R14: 字段可见性修复 + AI 统计 + 产品修改时间

**字段可见性修复:**
- `products.py` `get_product`/`create_product`/`update_product` 加 `filter_fields_for_user`（之前仅列表端点有）
- 成本价隐藏时后端设 `None`，前端 `|| '—'` 兜底，与厂商/供应商统一
- 管理页字段开关加 toast 通知（「成本价」已对普通用户可见/隐藏）

**AI 统计修复:**
- `admin_routes.py` `by_operation` → `by_op`（前端 key 不匹配导致"0操作类型"）
- `AiUsageStats.vue` `op[0]`/`op[1]` → `op.operation`/`op.count`

**产品修改时间:**
- `ProductDetailView` 新增修改时间显示（浏览前）
- `Product.updated_at` 移除 `onupdate=datetime.now`（浏览+1 触发误刷）

**测试:**
- `_seed_product` 修复 kwargs 透传
- +6 `TestFieldVisibility` 测试（84→84）

## 历史变更 (2026-06-12, R13)

### R13: 权限收紧 + Excel 导出统一 + AI 增强 + 质量加固

**方案/报价单权限收紧:**
- `auth.py` `filter_by_ownership`/`check_ownership` 新增 `strict` 参数
- `strict=True`: admin 全看, 普通用户只看自己创建的
- solutions.py + quotations.py 全部端点接入 strict 模式
- 批量删除增加所有权校验

**Excel 导出统一为威发格式:**
- 新建 `app/utils/excel_style.py` — 统一样式常量和辅助函数
- 12 列标准布局: 信息行(灰色) → 标题行(黄底) → 表头 → 数据行 → 合计(中文大写) → 备注 → 页脚
- 微软雅黑字体, thin 边框, 列宽标准化
- `export_products()` — 产品清单导出统一格式
- `export_quotation_xlsx()` — 报价单导出: H=F*G 公式, J=H*I 公式, J=SUM 公式
- `_write_basic_bom()` — BOM 导出统一格式
- 金额转中文大写 `num_to_chinese_uppercase()`
- F/H/J 列 ¥货币格式, G 列整数, I 列百分比

**图片嵌入 Excel:**
- `excel_style.py` `embed_image()` — 等比缩放居中嵌入产品图片到 L 列
- `_resolve_image()` — 支持本地文件/远程URL/上传目录
- 报价单和 BOM 导出均嵌入产品图片

**AI 助手质量提升:**
- `reasoning_content` 兜底: deepseek-v4-flash 推理模型回复在 reasoning_content 字段
- 关键词模型改回 `deepseek-chat` (无推理开销)
- 优化 `ai_keyword_prompt`: 去除硬编码同义词, LLM 自主语义理解产品匹配
- 新增 `solutions` 分组: 多方案场景 LLM 按方案返回产品组
- 前端 `AiChat.vue` / `SolutionDetailView.vue`: 方案组虚线分隔渲染
- SSE 异常不再泄露到前端, 服务器日志完整

**质量加固 (Review 修复):**
- `SolutionDetailView.vue` saveInfo: 静默丢弃 → toast 错误
- `quotations.py` BOM 保存: delete-then-insert → try/rollback
- `AiChat.vue` onAddToBom: 静默跳转 → toast 错误
- 批量添加 toast: 报告请求总数 → 报告实际成功/失败数
- `embed_image` 返回值检查 + 日志
- ~10 处 `except Exception` 补充异常详情日志
- BOM 编辑器 `model` 字段补充, `BomRow` 类型修正
- `bom_templates.py` `_sync_snapshot_to_items`: 修复未定义变量
- `ai.py` 提取 `_parse_tool_result` / `_get_done_events` helper
- `excel_style.py` 移除未用 import 和死参数
- `AiChat.vue` 提取 FAB 拖拽 helper

**数据修复:**
- `quotation_items.product_id` NOT NULL → nullable (BOM 编辑支持自由行)
- `quotation_items.sort_order` 0 → 1..N (修复 old_items 键冲突导致 product_id 丢失)
- `solution_items.sort_order` 同步修复
- DB `ai_keyword_model` 改回 `deepseek-chat`

### R12.2: 提示词 DB 化 + URL 按钮修复

## 最新变更 (2026-06-08, R12.2)

- 提示词 DB 化: `build_extraction_prompt` 从 `ai_extract_prompt` 读取, 管理页可编辑+重置
- 产品 URL 按钮: 裸 `www.` 域名自动识别, async/await 提取, 自动 `https://` 前缀
- 管理页优化: 提示词加重置按钮 + 分割线
- 新建产品页: 依赖关系卡片可见, 保存后跳转编辑页
- AI 卡片拖拽区文字改为"粘贴图片、拖拽文件到此处 或"

### R12.1: AI按钮恢复, 依赖卡片/自动滚动/URL提取联动

### R12: 全面优化 — 性能/架构/CSS/LLM/OCR/组件/安全

### R12: 全面优化 — 性能/架构/CSS/LLM/OCR

**性能优化:**
- +7 索引 (login_logs, product_categories, solution_items, quotation_items, product_dependencies, products(status,mfg), ai_conversations) / -2 重复索引
- `run_agent()` N+1: 40 次单独查询 → 1 次 `IN()` 批量加载
- 品类树递归 N+1: N 次查询 → 1 次全量 + 内存遍历 (`product_category_helper.get_category_descendants()`)
- BOM 3 处 `Product.query.all()` 全表扫描 → `Product.id.in_(pids)` 精确查询
- `build_context()` 规格定义查询: 10 次 → 1 次批量
- `product_categories` FK 修正: `categories(id)` → `device_categories(id)`, 7 orphan 行清理

**LLM + OCR:**
- 管理页新增 LLM 配置卡片 (主 LLM + 视觉 LLM 参数, 含测试按钮)
- 视觉 LLM 接入 Xiaomi Mimo (mimo-v2-omni), 图片上传自动 OCR 提取产品参数
- 测试按钮自动获取 `/v1/models` 可用模型列表 → DB → AI 设置下拉动态选项
- 主 LLM API key 三级 fallback: DB → .env → 空

**AI 用量统计:**
- 全 LLM 调用覆盖 (对话/URL提取/文本提取/文件提取/图片OCR)
- 提取为 `AiUsageStats.vue` 组件, 按操作类型标签
- 修复 token/duration 硬编码 0 的问题

**代码质量:**
- `get_or_404()` helper: 41 处 `db.get→404` 缩减为一行 (8 路由文件)
- `paginate()` helper: solutions.py + quotations.py 接入
- `apply_partial_update()` 全网部署: 6 路由 10 处 for 循环统一
- `utils/helpers.py` 新增 `get_or_404()`, `paginate()`; `apply_partial_update()` 支持 dict + Pydantic

**前端组件:**
- `AiExtractCard.vue`: 从 ProductFormView 拆分 (826→607 行, -27%)
- `AiUsageStats.vue`: AI 统计独立组件
- `AsyncContainer.vue`: 加载/错误/空态统一 (5 视图接入)
- `filter-tag-inline` CSS 类: ProductsView 6 处 inline style 消除

**CSS 系统:**
- 新增 7 个语义 color token (`--color-blue-50/100/700`, `--color-slate-50/100/400/700`)
- 全局 hardcoded hex → `var(--color-*)` (除 tag 专用色)
- `@media (hover: hover)` 包裹 touch 设备无意义悬停
- `btn-label` 类: `<label>` 伪装按钮统一样式
- `form-row-sm` 类: 表单行按钮统一 32px 高度

**安全增强:**
- `auth.py` admin_id 硬编码 1 → 30s TTL 动态查询 admin 用户列表
- LLM 双 provider API key 均存 DB (管理页即时修改, 不用 SSH 改 .env)
- `--color-accent-light` 修复 (不再自引用)
- 7 个 QuotationDetailView TS null 错误修复

**配置化:**
- `config.py` 新增 6 项: FRONTEND_DIST, IMAGE_MAX_SIZE, FILE_MAX_SIZE, AI_MAX_REDIRECTS, AI_CONTEXT_CACHE_TTL, AI_EXTRACT_MAX_CHARS
- `main.py` 前端 dist 路径可配置 + 相对路径
- `products.py` DYLD/LD_LIBRARY_PATH 跨平台 (macOS/Linux)
- `schemas/common.py` 清理未用 PaginatedResponse/MessageResponse
- 管理页登录/下载日志显示用户名 (不再裸 ID)

**文档更新:**
- CLAUDE.md R12 变更日志 + 文档索引
- 系统功能说明.md 数据统计 + 组件列表更新
- docs/architecture.md + docs/database.md 已补充最新架构

### R9-R10: 产品筛选 UI 重构 + 字典增强 + 规格编辑器

- 产品列表筛选全部改为流式标签按钮(品类/厂商/通讯/协议/供电), 收起时只显示第一行(CSS max-height)
- 厂商标签按 `sort_order` 排列, 字典页可编辑排序值
- 品类点击父类自动展开子类, 子类独立换行显示
- 4个字典表(通讯/协议/供电/传感)加 `description` 列, 含详细功能说明, 编辑弹窗可修改
- 产品编辑页新增通用 key-value 规格编辑器(品类无 spec_definitions 时显示), 支持添加/编辑/删除
- 产品编辑页加 `onBeforeRouteLeave` 未保存提示, BOM 加 `beforeunload` 拦截
- 厂商筛选由下拉改回标签按钮
- 品类页嵌入字典页第一tab, 导航栏移除品类链接
- 产品列表批量删除按钮, 厂商默认排序, 字典下拉分页→500全部加载
- AiChat/SolutionDetailView 重复函数统一到 markdown.ts
- SolutionDetailView 编辑即时保存不再全量刷新, picker 懒加载
- CSS 工具类: section-header, input-sm, mb-8/12, mt-8/12/16, m-0, flex-1
- URL 状态保持: 产品/方案/报价单搜索+筛选+翻页同步到 URL, 后退恢复
- 产品删除前清理依赖(product_dependencies), 解决 SQLite FK 问题
- 所有产品 spec key 中文化 (ip_rating→防护等级 等)
- -P 版产品清理 LoRaWAN 通讯+网关依赖
- 测试 78/78, vue-tsc 0 errors

### R7-R8: 权限系统
- 8 张表加 `created_by` 列: products, categories, manufacturers, suppliers, 4 dict tables
- `auth.py` 新增 `filter_by_ownership()` 和 `check_ownership()` 辅助函数
- 规则: admin 看全部; 普通用户看 `NULL`(legacy)/自己/admin(id=1) 的
- 所有 PUT/DELETE 端点加 `check_ownership()` 403 保护
- SECRET_KEY 启动时校验 ≥32 字符 (DEV_MODE 除外)

### AI 关键词匹配重构
- LLM 直接从 db_ctx 匹配产品 ID → 代码验证 → 去重 → 交错展示
- 每关键词 top 10 → 跨关键词去重 → 每关键词最多 5 条 → 交错合并
- `deepseek-chat` 替代 `deepseek-v4-flash` (避免 reasoning_content 吃光 max_tokens)
- DSML fallback: 检测全角 `｜` 格式，提取关键词执行 SQL fallback

### BOM 编辑器
- 方案页移除 BOM 编辑器 (依赖检查按钮也移除)
- 报价单页面新增 BOM 编辑器 (数据源: quotation items)
- 新增 `GET/PUT /quotations/{id}/bom` 端点
- BOMSpreadsheet 组件支持 `solutionId` 或 `quotationId` prop
- 添加/删除行 + confirm 确认 + toast 通知
- 模板保存功能移除

### 列布局统一
所有表格统一为: `# | 产品名称 | 型号/SKU | 功能描述 | 数量 | 单价 | 折扣% | 小计 | 备注`
产品清单、BOM 表格、报价单(页面+XLSX导出) 全部一致
报价单页移除 税率/总金额 信息行，表格加合计行

### 安全修复
- SQL 注入: `text(f'IN ({cat_id_list})')` → 参数化子查询
- SSRF path traversal: spec_generator `file://` 禁止，仅允许 http/https
- 文件下载端点加 auth: `product_files.py` download 加 `Depends(get_current_user)`
- `api.ts` headers 合并修复: `{...options, headers: {...headers, ...options.headers}}`
- `product.py` FK 修复: `nullable=False` + `ondelete="SET NULL"` → `ondelete="RESTRICT"`
- 死代码清理: admin_routes 死 return, App.vue fieldVisibility provide, 未用 imports

### 代码质量
- raw SQL `product_categories` 统一到 `product_category_helper.py` (6 文件消除)
- AiChat.vue `formatContent`/`extractProducts` 委托给 `markdown.ts`
- AiChat.vue resize listener 移入 `onMounted`/`onBeforeUnmount` 生命周期
- SolutionDetailView `updateItem`/`removeItem` 本地更新不再 `await load()`
- Picker 产品懒加载 (打开才请求 500 条)
- 报价单测试数据清理 (7 条重复 → 1 条)
- 价格 ¥ + 千位分隔 (方案/报价单列表+详情)

### 测试
- 修复测试套件 (60/78 → 78/78): `DEV_MODE=true` + `SECRET_KEY` 设测试值
- 后端 78/78, 前端 vitest 38/38, vue-tsc 0 errors

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
| Testing | pytest 84 tests + vitest 38 tests + Playwright 75 tests (3 套件: E2E+API+Perf) |
| Deployment | Docker Compose + Nginx |

## 开发命令

```bash
# 后端
cd backend && source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pytest tests/ -v

# 前端
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173   # 本地 vite (^6.3)，不用 npx vite（可能拿全局 v8）
npx vitest run
npx vue-tsc --noEmit

# E2E 测试
npx playwright test e2e/full-regression.spec.ts --reporter=list   # 全功能 (51 tests)
npx playwright test e2e/api-health.spec.ts --reporter=list        # API 端点 (19 tests)
npx playwright test e2e/perf-check.spec.ts --reporter=list        # 性能+可访问性 (4 tests)
npx playwright test --reporter=list                               # 全部套件
```

## 路径前缀配置

生产部署在 Nginx 反向代理子路径 `/product-db/`。Nginx 配置 `proxy_pass http://127.0.0.1:8000;`（**无**末尾斜杠）保留前缀透传。

| 组件 | 配置 |
|------|------|
| `vite.config.ts` | `base: '/product-db/'` |
| `backend/app/main.py` | 所有路由前缀 `/product-db/`（包括 `/product-db/api/`、`/product-db/assets/`、SPA catch-all） |
| `frontend/src/router.ts` | `createWebHistory('/product-db/')` |
| `frontend/src/api.ts` | `API_BASE = '/product-db/api'` |
| `frontend/src/components/AiChat.vue` | SSE fetch: `/product-db/api/ai/chat` |
| 所有前端 View | 直接 fetch 调用统一使用 `/product-db/api/` 前缀 |
| `backend/tests/test_api.py` | 测试 URL 使用 `/product-db/api/` 前缀 |

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
│   ├── ai_engine.py            # LlmEngine (DeepSeek API async)
│   ├── ai_tools.py             # Tool Calling 4 工具 + Mock 回退
│   ├── ai_extract.py           # AI 产品识别提取
│   ├── product_helpers.py      # 产品查询辅助 (eager loads, name maps, mappings)
│   ├── product_category_helper.py # product_categories 多对多统一操作
│   ├── spec_service.py         # 规格校验 + 产品对比
│   ├── spec_generator.py       # HTML/PDF 规格书生成
│   ├── storage.py              # 文件管理 (路径穿越防护)
│   └── field_visibility.py     # 字段可见性 (30s 缓存)
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
│   ├── SolutionDetailView.vue # 方案详情 (客户信息 + AI 气泡 + 产品清单)
│   └── SolutionsView.vue     # 方案列表 (行内状态下拉, 批量选择)
├── components/          # 通用组件
│   ├── AiChat.vue            # AI 浮动对话面板 (可拖拽/缩放, 气泡式)
│   ├── AgentView.vue          # Hermes Agent 全屏对话页 (/agent, SSE直连, 多会话)
│   ├── BOMSpreadsheet.vue    # BOM HTML 表格编辑器
│   ├── DependencyGraph.vue   # Canvas 依赖关系图 (自适应)
│   ├── ProductFiles.vue      # 产品文件上传/下载/预览
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
│     │ Round 0: LLM 产品匹配 + 关键词提取                 │ │
│     │                                                  │ │
│     │  kw_system = keyword_prompt + db_ctx (300s缓存)  │ │
│     │    - db_ctx: 品类/厂商/字典/414产品全量[ID:xxx] 描述+specs  │ │
│     │    - size: ~98KB ≈ 44K tokens                    │ │
│     │    - prompt 存储在 system_settings 表, 管理后台可编辑│ │
│     │                                                  │ │
│     │  LLM (deepseek-chat, temp=0)                     │ │
│     │    → {"keywords":["光照","网关"],                  │ │
│     │       "matches":{"光照":[231,237],"网关":[278,280]}}│ │
│     │                                                  │ │
│     │  代码验证 ID → DB 取真实数据 → 去重 → 交错合并    │ │
│     │    → 每关键词 top 10 → 跨关键词去重 → 最多5条/词  │ │
│     │    → 价格过滤由 SQL 层处理                         │ │
│     │    → 0结果/DSML: fallback SQL LIKE               │ │
│     │                                                  │ │
│     │  SSE: tool事件 + products事件 + component事件      │ │
│     │  products_found = True, max_turns = 1            │ │
│     └─────────────────────────────────────────────────┘ │
│     ┌─────────────────────────────────────────────────┐ │
│     │ Round 1: Chat LLM (deepseek-v4-flash)            │ │
│     │                                                  │ │
│     │  products_found=True → 简要文本回复                │ │
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
  "keywords": ["光照", "网关"],        // 必填, LLM自主拆词 (最多4个)
  "matches": {"光照":[231,237,...]},   // 每个关键词匹配的产品ID (最多10个/词)
  "category": null,                    // 仅用户明确说出才填
  "comm_method": null,                 // LoRaWAN/WiFi/Ethernet/4G/5G...
  "protocol": null,                    // MQTT/HTTP/ModbusRTU...
  "power": null,                       // DC/PoE/Battery...
  "brand": null,                       // 厂商名, 必须来自DB
  "min_price": null,                   // 数字, 未提则null
  "max_price": null,                   // 数字, 未提则null
  "sort_by": null                      // price_asc / price_desc
}
```

**模型**: keyword 提取用 `deepseek-chat` (无 reasoning_content 开销), Chat LLM 用 `deepseek-v4-flash`。
**DSML fallback**: deepseek 偶尔返回 `<｜DSML｜tool_calls>` 格式，代码检测后解析关键词执行 SQL LIKE。
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

## API 概览

| 分组 | 端点 | 说明 |
|------|------|------|
| Auth | `POST /auth/login|register` | JWT 登录/注册, 频率限制 |
| Products | `GET|POST /products`, `GET|PUT|DELETE /products/{id}` | CRUD + 分页 + 品类/厂商/通讯筛选 |
| Categories | `GET|POST /categories`, `PUT|DELETE /categories/{id}` | 树形品类管理 |
| Solutions | `GET|POST /solutions`, `PUT|DELETE /solutions/{id}` | 方案 CRUD + 行内状态编辑 |
| Quotations | `GET|POST /quotations`, `PUT|DELETE /quotations/{id}` | 报价 CRUD + 导出 xlsx |
| Quotation BOM | `GET|PUT /quotations/{id}/bom` | 报价单 BOM 编辑器数据源 |
| BOM Snapshots | `GET|PUT /solutions/{id}/bom-snapshot` | 方案 BOM 快照 |
| Dicts | `GET|POST /dicts/{type}`, `PUT|DELETE /dicts/{type}/{id}` | 通讯/协议/供电/传感器/厂商/供应商 |
| AI | `POST /ai/chat` (SSE), `GET /ai/conversations` | AI 方案助手 |
| Agent | `POST /agent/chat` (SSE), `GET /agent/config|prompt` | Hermes Agent 代理 |
| Agent Files | `POST /agent/upload`, `POST /agent/cleanup-uploads` | 文件上传 + 清理 |
| Agent Approval | `POST /agent/approval/{id}`, `GET /agent/approvals` | Human-in-the-loop 审批 |
| Files | `GET|POST /products/{id}/files`, `GET|DELETE /products/files/{id}` | 产品文件 (下载需auth) |
| Admin | `GET|PUT /admin/*` | 用户管理/系统设置/AI设置 (admin only) |

## 核心数据模型

- **权限**: 8 张业务表含 `created_by` → users.id, `filter_by_ownership()` 列表过滤, `check_ownership()` 单资源 403
- **品类**: `product_categories` 多对多中间表, 统一通过 `product_category_helper.py` 操作
- **产品**: Product.cost_price 对非 admin 隐藏 (field_visibility), specs/urls JSON 字段
- **方案**: Solution → SolutionItem (级联删除), `created_by` 自动记录
- **报价**: Quotation → QuotationItem (product_snapshot JSON), `download_count` 下载计数
- **BOM**: SolutionBOMSnapshot 快照格式 (cells + colWidths), BOMTemplate 可复用模板
- **AI**: AIConversation + AIMessage (多轮对话), AIUsageLog (token 用量)

## 方案 (Solution) 工作流

```
创建方案 → AI 助手选品 → 批量加入/移除产品 → 生成报价单
              │                  │            │
         GenUI卡片+勾选     行内编辑数量/折扣  报价单含产品快照
              │
         方案列表行内状态下拉 (草稿/进行中/完成)
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
| `AiChat.vue` | AI 浮动对话面板 (可拖拽/缩放, 气泡式, DOMPurify清洗) |
| `SolutionDetailView.vue` | 方案详情 (客户信息 + AI 方案助手 + 产品清单行内编辑, 懒加载 picker) |
| `BOMSpreadsheet.vue` | BOM HTML 表格编辑器 (支持 solutionId/quotationId, 添加/删除行, toast通知) |
| `QuotationDetailView.vue` | 报价单详情 (只读表格 + BOM 编辑器 + xlsx 导出 + 合计行) |
| `SolutionsView.vue` | 方案列表 (行内状态下拉框, ¥价格格式) |
| `QuotationsView.vue` | 报价单列表 (行内状态下拉框, ¥价格格式) |
| `GenUI/` | AI 动态组件 (SolutionProductCard, QuoteDraftCard) |

## BOM 表格编辑器

- HTML 表格实现，点击单元格直接编辑
- 列: `# | 产品名称 | 型号/SKU | 功能描述 | 数量 | 单价 | 折扣% | 小计 | 备注` + 合计行
- 按钮: 重新加载/保存/添加行/导出xlsx (模板保存已移除)
- 每行垃圾桶图标删除 + confirm 确认
- 500px 最大高度，超出滚动
- 支持两种数据源:
  - `solutionId`: 读写 `solution_bom_snapshots` 表 (方案页已移除)
  - `quotationId`: 读写 `quotation_items` 表 (报价单页使用)
- 通知统一使用全局 `showToast()` (不再使用 `alert()`)
- 报价单 BOM 导出 XLSX 格式统一匹配编辑器列布局

## 产品文件 (Product Files)

- `product_files` 表: product_id, filename, file_url, file_size, file_type, label
- API: GET/POST `/products/{id}/files`, GET/DELETE `/products/files/{id}`
- 下载端点已加 `Depends(get_current_user)` 认证，支持 `?token=` 参数
- 支持格式: pdf/doc/xlsx/zip/txt/csv + 图片, 最大 20MB
- 上传 → `save_file()` UUID 重命名存到 `app/uploads/`
- 下载 → `StreamingResponse` + UTF-8 文件名
- 预览: PDF iframe, 图片 `<img>`, TXT/CSV `<pre>`, 其他下载
- 前端组件 `ProductFiles.vue`: 文件列表+上传+预览模态框

## 品类系统

- 产品支持**多品类** (`product_categories` 多对多, 统一通过 `product_category_helper.py` 操作)
- `products.category_id` 为遗留单列，逐步废弃中 (FK `ondelete=RESTRICT` 防止意外删除)
- 品类树 27 个活跃品类: 传感器/网关/节点终端/安防/工具/执行器等
- 产品列表筛选: 父品类行 + 点击展开子品类行（独立行显示）
- 后端递归查询子孙品类 ID, 选中父品类覆盖所有后代产品
- 删除品类自动级联清理 FK: spec_definitions, product_categories, dependencies, products.category_id → fallback, children.parent_id → NULL

## 数据库优化

- 业务索引: ai_messages(conv_id), product_files(product_id), solution_items(solution_id), quotation_items(quotation_id), quotations(solution_id)
- 报价单下载计数: `quotations.download_count` + `download_logs` 表 (下载端点无 auth 但需 token 参数)
- SQLite 31 张表, ~4000 行, 单文件运行
- 图片: 90% 远程 URL, 10% 本地 `app/uploads/`
- `product_category_helper.py` 消除 5 处 raw SQL, 统一 ORM 参数化查询

## 关键约定

- 模型统一 `to_dict()` 方法，Product 支持 map 参数防 N+1
- 通用 partial update: `apply_partial_update(obj, data, fields)`
- **权限**: `filter_by_ownership()` 过滤列表, `check_ownership()` 校验单资源 (admin 看全部, 普通用户看 NULL/自己/admin)
- **created_by**: 8 表 (products, categories, manufacturers, suppliers, 4 dict) 创建时自动设为 `user.id`
- DEV_MODE=True 时免登录 (自动创建 admin/admin)，生产必须 False
- SECRET_KEY 必填且 ≥32 字符 (DEV_MODE 除外), 否则 sys.exit(1)
- 前端 CSS 变量定义在 main.css，组件用 scoped 样式
- API 统一通过 `api.ts` → `api<T>()` 泛型函数, headers 正确合并
- API_BASE = `/product-db/api`, Vite proxy 匹配 `/product-db/api` → backend
- `window.open()` 下载/导出需 `?token=` query param 认证
- SSE component 事件 → GenUI 组件动态渲染
- 密码: bcrypt (passlib) + 旧 SHA256 自动升级
- v-html 全部经 DOMPurify.sanitize() 清洗
- 字典/供应商数据 30s TTL 缓存, AI 上下文 300s TTL 缓存
- 方案/报价单列表状态行内下拉修改, 报价单列表也支持
- AI 方案助手使用气泡式对话布局 (用户右侧蓝色, AI 左侧灰色, tool 状态左对齐)
- 导航栏排序: 搜索栏 → 产品 → 方案 → 报价单 → 品类 → 字典 → 管理
- 字典页面: 标签切换 (通讯方式/协议/供电/传感器/厂商/供应商)
- 供应商管理已并入字典页，无独立导航
- 所有表格统一列: `# | 产品名称 | 型号/SKU | 功能描述 | 数量 | 单价 | 折扣% | 小计 | 备注`
- 价格统一 ¥ + toLocaleString() 千位分隔格式

## 文档

- `docs/architecture.md` — 完整架构总览 (技术栈/分层/路由/组件/AI/安全)
- `docs/database.md` — 数据库设计 (33 表/ER/索引/JSON 策略/权限模型)
