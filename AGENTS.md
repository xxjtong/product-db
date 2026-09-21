# 产品数据库 (product-db)

IoT 产品选型对比、规格书生成、方案设计系统。独立于 quote-system 的新项目，不限品类。

## 最新变更 (2026-09-21, R50)

### R50: 数量 0 定为合法值（「本次不采购但保留该行」），不再被悄悄改成 1 (2026-09-21)

**问题**：数量 0 的语义各处不一致 —— 后端金额计算按 0 算（`quantity or 0`），
但 BOM **保存/载入**路径写成 `or 1`，于是**填 0 保存后读回变成 1**；而 BOM 编辑器输入框
明明是 `min="0"`（允许填 0），方案详情输入框却是 `min="1"`。同一系统里三种口径。

**语义决策（与用户确认）**：数量 0 = **合法值**：该行保留、金额算 0、产品信息不丢 ——
适用于「本次不采购但保留参考」的占位行，与 R49 的折扣 0（免费/赠品）同族。

**修复**：新增 [helpers.number_or(value, default)](backend/app/utils/helpers.py)（0 保留，
只有 `None`/空串/脏数据才回退），`discount_percent` 改为复用它 —— 两种语义不再各写一遍。

| 位置 | 改动 |
|---|---|
| `routers/quotations.py` BOM 保存落库 | `float(row.get("qty", 1) or 1)` → `number_or(row.get("qty"), 1)`；amount 复用同一个 qty（原来把 qty 表达式算了两遍） |
| `routers/bom_templates.py` 快照→条目同步 | E/F 列改走 `number_or`（原为 `or 0`，行为不变，统一入口） |
| `components/BOMSpreadsheet.vue` | 新增 `numberOr(v, fallback)`；载入报价单行与快照的 E/F/J 列都改用它（原 `Number(v) \|\| 1` 会把 0 变 1） |
| `views/SolutionDetailView.vue` | 数量输入框 `min="1"` → `min="0"`（界面此前不允许填 0，与后端行为矛盾） |

**有意保留 `\|\| 1` 的场景**：加入方案 / AI 加购（`SolutionProductCard`、`AiChat`、
`SolutionDetailView.onAddToBom`）的数量来自 `min="1"` 的输入框，0 在那里无意义，回退 1 是正确行为。

**测试:** backend +2（helper 边界；BOM 保存数量 0 → 该行保留、quantity 落库为 0、合计只算其他行）

> 数量 0 的行导出时：小计公式 `=E*F*G/100` 自然算出 0；需要的话可以在导出里给这类行
> 加「本次不采购」标注。

## 历史变更 (2026-09-21, R49)

### R49: 折扣率 0 不再被当成「未设置」（免费/赠品不再被按 100% 计价）(2026-09-21)

**问题**：全仓多处写成 `discount_rate or 100`。Python 与 JS 都把 `0` 视为假值 → **折扣率 0
被按 100% 计算**。凡是用到折扣的地方全部受影响：明细金额、方案/报价单合计、导出表格、
AI 建单、前端显示。生产当前 `discount_rate ≠ 100` 的条目为 0 条，所以还没暴露，但一旦有人
填 0（免费/赠品场景）就会算错钱。

**修复**：新增**唯一判定入口** [helpers.discount_percent](backend/app/utils/helpers.py)
（`0` 保留原值；只有 `None`/空串/脏数据才取默认 100），替换全部 **17 处**（后端 11 + 模型 2 + 前端 4）：

| 位置 | 处数 |
|---|---|
| `routers/quotations.py`（`_recalc_total`、导出、bom rows 接口、BOM 导入的 amount 与 discount_rate） | 5 |
| `routers/solutions.py`（`_recalc_totals`） | 1 |
| `routers/bom_templates.py`（快照→条目同步、兜底导出、快照导出） | 3 |
| `services/ai_tools.py`（算总价、落库） | 2 |
| `models/quotation.py` / `models/solution.py`（`to_dict` 回读，原先 0 会被读成 100） | 2 |
| 前端 `SolutionDetailView.vue` ×2、`BOMSpreadsheet.vue` ×2 | 4 |

两处实现细节：`to_dict` 为让模型层不依赖 `utils`，用内联 `is not None` 判断；前端两个组件
各自内联同口径的 `discountPct()`（`Number('') === 0` 会误判，所以不能简单用 `?? 100`）。

**测试:** backend +3（helper 边界 7 条断言、方案折扣 0、报价单折扣 0 + 导出折扣列断言）

> 顺带发现但**未改**（超出本次范围）：同一函数里的 `float(row.get("qty", 1) or 1)` 与
> `float(row.get("price", 0) or 0)` 也是"假值即默认"写法 —— 数量 0 会被当成 1。
> 因数量 0 的语义（等价于删除该行？）需业务确认，暂留待办。

## 历史变更 (2026-09-21, R48)

### R48: 修掉本轮检查发现的 3 条高优先（agent 写操作 401 / 管理员自锁 / BOM 小计口径）(2026-09-21)

本轮检查 = 2 路静态审计（本次改动的新问题 + 上轮遗留项现状）+ 生产实测。项目整体健康
（服务 active、近 24h 零错误、业务孤儿 0、成本可见性正确），查出 3 条真问题：

**H1. agent 提示词用 query token 做写操作 → 必然 401**
生产 `agent_prompt` 里有 **15 处** `?token={{TOKEN}}` / `&token={{TOKEN}}`，其中包括
`POST {{API_BASE}}/solutions?token={{TOKEN}}`、`PUT`、`DELETE` 与报价单 `POST`；
而后端只允许 **GET** 用 query-string token（`auth.py` 的 method 检查），写操作一律 401。实测：

```
POST + query token   → 401   ← 提示词要求 agent 这么做
GET  + query token   → 200
POST + Authorization → 422   ← 鉴权通过（只是 body 不合法）
```

即 Hermes agent 的**建/改/删方案、建报价单全部失败**（读操作正常）。
修法：提示词统一改为请求头 `Authorization: Bearer {{TOKEN}}`，并写明「写操作必须用请求头」。
- 代码默认值（`admin_routes._PROMPT_DEFAULTS["agent_prompt"]`）已重写；
- **生产 DB 里的实际值**（人工定制过，与代码默认值不同）用 `replace()` 精确剥离那 15 处
  token 片段并重写规则行 —— 保留其余定制内容，不整段覆盖；
- 生产验证：更新后 `token=` 出现次数 **15 → 0**，URL 示例变为 `/solutions`、`/solutions/<ID>` 等。

**H2. 管理员改/重置自己的密码 → 把自己锁在报错页**
`admin_routes` 递增 `token_version` 时没排除 `uid == 自己`，而管理页的 `adminApi` 用的是原生
`fetch`、不接 `api()` 的 401 跳转 → 弹完「已重置」后所有请求 401，页面停在错误态；
路由守卫只按客户端 `exp` 判断，所以刷新也不会跳登录。属 R41 第 4、5 两条修复的交互盲区。

修法：`update_user`（带 password 时）与 `reset_user_password` 都拒绝操作自己
（400 + 提示走「个人信息」）；补测试确认「改别人的密码」仍正常、且确实作废对方 token。

**H3. BOM 兜底分支的小计漏了折扣 → 与合计行自相矛盾**
兜底分支写 `=E*F`（数量×单价，不含折扣），快照分支写 `qty*price*discount/100`（含折扣），
而合计行的大写金额来自含折扣的 `sol.total_price` —— R45 统一了**列布局**却没统一**口径**，
同一张表里 `SUM(H)` 与大写金额会互相矛盾。**影响面**：生产当前 `discount_rate ≠ 100` 的条目
0 条，故尚未暴露。

修法：兜底 H 列改为 `=E{row}*F{row}*G{row}/100`，行内初值同步含折扣；补一条
`discount_rate=90` 的用例（原用例折扣全是 100%，所以一直是绿的，发现不了）。

**测试:** backend **486 passed** (1 skipped, +4)

> 本轮检查的其余结论仍待办：401 统一处理只覆盖 `api()`（原生 fetch 通道未接入，H2 只是其中一例）、
> BOM 看不到成本时仍设 J 列宽、`dedup_filename_part` 子串判重可能误删型号、
> `_keep_server_cost` 的 `cells` 类型边界、`apply_total_row` 参数无校验、
> 以及 14 条遗留项（折扣率 0 当 100、品类成环、报价单号竞态、GET 快照写库、导入裸 float、
> `/agent/approvals` 跨用户、分页无上限、列表全表加载、systemd 缺加固、CI 不含 E2E、
> 备份无异地、文档漂移等）。

## 历史变更 (2026-09-21, R47)

### R47: 修复规格书 PDF「中文丢失」——根因是服务器没有中文字体 (2026-09-21)

**现象**：导出的产品规格书「内容不完整」，而且**每份都长一样**。用户提供的
`产品规格书_RA02A_LoRaWAN烟雾感应器.pdf` 只有 1 页，用 PyPDF2 提取出的文本仅 **196 字符**：

```
LoRaWAN
Netvox ( ) | /  | : RA02A      ← 括号里、冒号前的汉字全没了
 Ethernet —
MQTT
 /
DC — —
```

**根因**：生产服务器上**没有任何中文字体**（`fc-list :lang=zh` 实测 0 个，全系统仅 6 个字体）。
weasyprint 找不到汉字字形时会**静默丢字**（不报错、不告警），于是 PDF 里只剩英文与数字 ——
所以每份规格书都残缺且彼此相似。

**修复（纯运维，未改一行代码）**：把 Noto Sans/Serif CJK 装进**用户字体目录**，无需 root ——
服务的 systemd 单元是 `User=tong`（`systemctl show product-db -p User`），`~/.fonts/` 即可生效。
已固化为脚本 `deploy/install-cjk-fonts.sh`（幂等；普通用户执行 = 用户级安装，`sudo` 执行 = 系统级）：

```bash
ssh -p 28793 tong@124.221.178.161 'bash /opt/product-db/deploy/install-cjk-fonts.sh'
```

- **不需要重启服务**：weasyprint 是每次导出时新起的子进程，装完立刻可用。
- **一处判断更正**：当时以为「免密 sudo 白名单不含 apt」才走用户级；复核 `sudo -n -l` 发现
  白名单里其实有 `apt install *`（以及 `apt update/upgrade`）。随后按「所有用户可用」的需求，
  用 `sudo -n apt install -y fonts-noto-cjk` 升级为**系统级**
  （`/usr/share/fonts/opentype/noto/`），并删掉 `~/.fonts` 的用户级副本避免同一字体占两份
  （复测：PDF 339KB、中文完整、耗时 10.4s）。

**验证（生产实测）**：中文字体数 **0 → 30**；导出 RA02A（产品 485）规格书耗时 7.8s，
PDF **37KB → 258KB**（内嵌 CJK 字体子集），提取文本 **196 → 309 字符且中文完整**
（`Netvox (奈伯思)`、`通讯方式`、`供电方式`、`描述`…）。
命令与排查方法已记入 [DEPLOY.md](DEPLOY.md) 的「服务器」一节。

> 教训：这类问题的排查顺序是「先看字体（`fc-list :lang=zh`），再看 PDF 体积」，
> 不要从「weasyprint 没装」猜起 —— R40 就在这条弯路上绕过一次。

**测试:** 无代码改动；backend **482 passed** / vitest **78 passed**（复核未受影响）。

## 历史变更 (2026-09-21, R46)

### R46: 无成本权限时导出表格不再出现「成本」字样 (2026-09-21)

R45 统一了 BOM 的列布局，但**报价单**与**产品清单**的导出还留着旧行为：成本列（M）的值虽然留空，
却仍然写入「成本」表头 —— 表格里有一个「成本」列却整列是空的，看起来像数据漏了。

统一为**无权限时整列不输出**（与 BOM 两个分支一致）：

| 导出 | 无成本权限时 |
|---|---|
| 报价单 | 不写 M3「成本」表头、不创建 M 列数据单元格、不设 M 列宽 |
| 产品清单 | 同上 |
| 方案 BOM（快照/兜底） | R45 起已是整列不输出 |

- `excel_style.apply_column_widths(ws, include_cost=True)` 新增参数：看不到成本时连 M 列宽也不设，
  免得表格右侧多出一条空列；**默认值保持"含成本"**，其它调用点不受影响。
- 有权限者看到的仍是原来的样子（M 列 + 「成本」表头），测试里专门断言了这一点，防止过度裁剪。
- 判定口径不变，仍是 `field_visibility.cost_visible()`（admin → 按用户三态 → 全局开关）。

**测试:** backend **482 passed** (1 skipped, +1：整表不得出现「成本」字样 + 管理员侧仍有表头)。

## 历史变更 (2026-09-21, R45)

### R45: BOM 导出统一为一套列布局（成本固定 J 列）(2026-09-21)

排查「导出报价单/BOM 时怎么判断要不要带成本列」时发现：BOM 导出的两条分支**用了两套完全不同的表结构** ——
不只是成本列位置不同，而是列数、列序都不一样。

| 分支 | 触发条件 | 列布局 |
|---|---|---|
| 快照分支 | 方案在 BOM 编辑器里保存过快照 | 10 列：`A# B产品名称 C型号/SKU D功能描述 E数量 F单价 G折扣% H小计 I备注 J成本`（生产实测 A..J，J1=「成本」） |
| 兜底分支 | 方案还没保存过快照，按 solution_items 生成 | 12 列：`序号/名称/规格型号/型号/功能描述/单价/数量/合计/折扣率/成交价/备注/图片` + 成本在 **M** |

这不只是"看着不一致"：存储、`_keep_server_cost`、`_COST_COLUMN = "J"` 一律按 J 列认定成本，
只有兜底分支的导出把成本放在 M，**布局与判定口径是错位的**。

**统一到编辑器布局**（列语义由编辑器与存储决定，导出应与编辑器所见一致）：

- `bom_templates._BOM_HEADERS` + `BOM_MAX_COL = 10` + 专属 `_BOM_COLUMN_WIDTHS`
  （不能复用报价单那套 12 列宽：列语义不同，硬套会让"数量"列拿到功能描述的 60 宽）
- 兜底分支：去掉「成交价」「图片」两列（快照布局本来就没有），成本移到 J
- 小计（H）仍是公式 `=E{row}*F{row}`；合计行的大写金额合并到 G、SUM 落在 H（与"小计"列对齐，
  成本列不参与合计）—— 为此给 `apply_total_row` 加了 `merge_end_col` / `max_col` 参数，
  给 `apply_info_row` / `apply_title_row` / `apply_note_row` / `apply_footer_row` 加了 `max_col`
  （**默认值不变**，报价单导出完全不受影响）
- 顺带统一「看不到成本时」的表现：兜底分支原先写一个空的「成本」表头，现在与快照分支一样
  **整列不输出**（连表头也不写）
- 行结构仍保留兜底分支特有的信息行/标题行/合计行（快照是用户在编辑器里排的，本来就没有这些）

> 注：报价单导出（12 列、成本 M）**未动** —— 那是另一套模板，用户没有提出要统一；本次只统一 BOM。

**测试:** backend **481 passed** (1 skipped, +2：`TestBOMColumnLayout` —— 列头与成本位置一致 / 不可见时整列不输出)。

## 历史变更 (2026-09-21, R44)

### R44: 报价单文件名去掉「报价单_」前缀（编号里的 QT 已含该语义）(2026-09-21)

R43 之后报价单文件名是 `报价单_QT-20260918-001_SMC-会议室环境检测.xlsx`，但编号本身就以
**QT**（quotation）开头 —— 类型信息写了两遍。改为 **`{编号}_{标题}.xlsx`**：

| 导出 | 文件名（生产实测） | 是否含类型词 |
|---|---|---|
| 报价单 | `QT-20260918-001_SMC-会议室环境检测.xlsx` | 编号里的 QT 即类型 |
| 方案 BOM | `BOM_id30_麦当劳广州-空调集控.xlsx` | BOM 是类型词，保留 |
| 产品清单 | `产品清单_20260921.xlsx` | 日期没有类型语义，保留 |
| 产品规格书 | `产品规格书_CT303 CT305 CT310_智能电流互感器.pdf` | 型号没有类型语义，保留 |

- 只有报价单能去掉前缀，因为只有它的首个片段自带类型语义；其余三类的首段（`BOM` / 日期 / 型号）都不是类型词。
- 编号为空时退回 `id{报价单ID}`（此时文件名不含类型词；下载入口就在报价单页，不影响辨识）。
- ASCII 回退名**保持** `quotation_58.xlsx`：它是给不支持 `filename*` 的老客户端用的，
  英文 + id 才既保证可编码又可辨识。
- 测试加 `quote("报价单") not in cd`，防止前缀被加回来。

**测试:** backend **479 passed** (1 skipped)

## 历史变更 (2026-09-21, R43)

### R43: 导出文件名去掉客户维度（客户信息本来就在名称里）(2026-09-21)

R42 把顺序调成「标识_客户_名称」后，实测仍有肉眼可见的重复：

```
报价单_QT-20260918-001_SMC_SMC-会议室环境检测.xlsx
BOM_id30_麦当劳（广州）_麦当劳广州-空调集控.xlsx
```

根因不在顺序，而在**数据形态**：查生产 7 条报价单与 7 条方案，其中 **6 条**的客户名就写在
标题/方案名里（客户「SMC」+ 标题「SMC-会议室环境检测」是常态，不是个例 — 因为做方案时
习惯把客户名写进项目名）。所以结论是**根本不该拼客户名**。

最终规则（比 R42 更简单）：

| 导出 | 文件名 | 生产实测 |
|---|---|---|
| 报价单 | `报价单_{编号}_{标题}.xlsx` | `报价单_QT-20260918-001_SMC-会议室环境检测.xlsx` |
| 方案 BOM | `BOM_id{方案ID}_{方案名}.xlsx` | `BOM_id30_麦当劳广州-空调集控.xlsx` |
| 产品清单 | `产品清单_{YYYYMMDD}.xlsx` | `产品清单_20260921.xlsx` |
| 产品规格书 | `产品规格书_{型号｜id}_{产品名}.pdf` | `产品规格书_CT303 CT305 CT310_智能电流互感器.pdf` |

- 报价单/方案 BOM **不含客户维度**；缺编号时退回 `id{报价单ID}`，保证标识仍在最前。
- 规格书保留「型号去重」：型号常整段出现在产品名里（「WTS506 气象站」+ 型号「WTS506」），
  此时省略型号 → `产品规格书_WTS506 气象站.pdf`；比较忽略空格/连字符/括号，
  「CT303 CT305 CT310」与「CT303/CT305/CT310」视为同一型号（`helpers.dedup_filename_part`）。
- 测试改用**真实数据形态**断言（客户 SMC + 标题 SMC-会议室环境检测），并断言
  `cd.count("SMC") == 1` —— 客户名若被重新拼进去就变成 2，用例直接红。这条比「断言等于期望串」
  更能守住意图，因为将来改分隔符或加片段时仍会失败。

**测试:** backend **479 passed** (1 skipped)

## 历史变更 (2026-09-21, R42)

### R42: 导出文件名改为「标识在前、客户/项目名在后」(2026-09-21)

R40 定的顺序是「客户_项目_编号」，实际用起来**看着像重复**：

```
报价单_SMC_SMC-会议室环境检测_QT-20260918-001.xlsx
        └┬┘ └────────┬────────┘
      客户叫 SMC   项目标题也以 SMC 开头
```

统一改为 **`{类型}_{标识}_{客户}_{项目/名称}.{ext}`**（没有该维度的片段直接跳过）：

| 导出 | 文件名 | 示例 |
|---|---|---|
| 报价单 | `报价单_{编号}_{客户}_{项目标题}.xlsx` | `报价单_QT-20260918-001_SMC_SMC-会议室环境检测.xlsx` |
| 方案 BOM | `BOM_id{方案ID}_{客户}_{方案名}.xlsx` | `BOM_id30_麦当劳（广州）_麦当劳广州-空调集控.xlsx` |
| 产品清单 | `产品清单_{YYYYMMDD}.xlsx`（全库导出，无客户/项目维度） | `产品清单_20260921.xlsx` |
| 产品规格书 | `产品规格书_{型号｜id}_{产品名}.pdf` | `产品规格书_CT303 CT305 CT310_智能电流互感器.pdf` |

两点口径：
- 规格书的「标识」用**型号**（本身就是产品标识），缺型号时退回 `id{产品ID}`；报价单缺编号时同样退回 `id{报价单ID}` ——
  保证任何时候都有一个可排序的前缀，不会退化成「客户名打头」。
- 测试除断言完整文件名外，**另加「标识必须出现在客户名之前」的位置断言**（`cd.index(...) < cd.index(...)`），
  免得以后又被调回旧顺序还全绿。

**测试:** backend **478 passed** (1 skipped) —— 4 条文件名用例整体改写为「标识在前」，
并新增「标识位置必须在客户名之前」与「缺型号退回 id」两类断言

## 历史变更 (2026-09-21, R41)

### R41: 全面审计后的 5 条高危修复 (2026-09-21)

起因是「再检查一下项目全部功能有无漏洞问题」，做了四路审计（后端安全 / 后端正确性 / 前端 / 运维与测试），
再用**生产库只读实测**逐条确认可达性。审计报告里有一批"看起来严重但生产不可达"的项，也一并记在下面，
避免以后重复误报。

**A) 修掉的 5 条高危**

| # | 问题 | 修法 |
|---|------|------|
| 1 | 报价单**条目写接口**（POST/PUT `/quotations/{id}/items`）把 `product_snapshot` 原样回传，含真实 `cost_price` —— 同文件的列表接口早已裁剪，列表裁了、写接口没裁等于没裁 | 两处返回值改走 `_filter_quotation_items_cost()`；并断言「管理员仍能看到」防止过度裁剪 |
| 2 | 报价单**导出**只读全局开关（`get_field_visibility()`），不走 `cost_visible` → R37 的按用户三态覆盖在这条路径失效（被单独放行的用户导出仍没有成本；反向则泄漏） | 改为 `show_cost = cost_visible(user, db)`，与产品导出、方案 BOM 导出一致 |
| 3 | **批量删除**用 `db.query(...).delete()`（bulk DELETE）不触发 ORM cascade，而 SQLite 外键在生产**未启用** → 产生永久孤儿子行；SQLite 的 `INTEGER PRIMARY KEY` 会复用 rowid，新单据可能把历史孤儿子行「认领」进新单据 | ①两条批量删除改为逐条 `db.delete(row)` 自行级联；②迁移 `b7c8d9e0f1a2` 清掉存量孤儿 |
| 4 | 管理后台 6 处直接 `await fetch(...)` **不检查 `res.ok`** —— `fetch` 对 4xx/5xx 不 reject，`catch` 永不触发 → 后端 403/429/500 时仍弹「已保存/已删除/密码已重置」，且本地状态不回滚。管理员会以为成本价可见性、注册开关已生效 | 6 处改用文件内已有的 `adminApi()`（自带 `res.ok` + detail 提取），失败时回滚 `fv.visible`/`regOpen`、保留弹窗 |
| 5 | **无登出、无 token 撤销**：JWT 无状态且全仓没有 logout 路由，改密/被重置密码后旧 token 仍能用满 24h | `users.token_version`（迁移 `c8d9e0f1a2b3`）+ payload 带 `ver` + `get_current_user` 逐次比对；新增 `POST /auth/logout`；改密、管理员重置密码时递增 |

> 第 5 条的兼容设计：老 token 没有 `ver` 字段，取 0；存量用户 `token_version` 的 `server_default` 也是 0
> → **部署不会把任何已登录用户踢下线**（有专门用例 `test_legacy_token_without_ver_still_valid` 守着）。
> 代价是「登出会登出该用户所有设备」，在单账号场景下这是更安全的一侧。

**B) 生产实测：外键为什么不能顺手打开**

`PRAGMA foreign_key_check` 在生产有 **978 行违规**，分类如下 —— 其中审计类**不该删**，所以不能简单「清空后开约束」：

| 违规 | 行数 | 处置 |
|------|------|------|
| `ai_messages → ai_conversations` | 712 | 会话已删、消息残留（可清理，但属独立事项） |
| `quotation_items → quotations` | 124 | **本次清理**（孤儿子行，批量删除产生） |
| `product_categories → products` | 56 | 产品已删、映射残留 |
| `solution_items → solutions` | 50 | **本次清理** |
| `login_logs → users` | 19 | **审计信息，必须保留** |
| `quotation_items → products` | 6 | `product_id` 指向已删产品（条目本身有效，应置 NULL 而非删行） |
| `product_comm_methods → dict_comm_methods` | 4 | 字典项已删 |
| `ai_usage_logs → users` | 3 | **审计，保留** |
| `solution_bom_snapshots → solutions` | 2 | **本次清理** |
| `dict_comm_protocols → users`、`category_spec_definitions → device_categories` | 各 1 | 遗留引用 |

结论：外键约束要打开，得先给每一类定策略（删 / 置 NULL / 保留），属独立事项；
在此之前**批量删除已自行级联**，孤儿不会继续增长。这条留给后续（记在「遗留」里）。

**C) 审计中"看着严重、实测不可达"的项（勿重复误报）**

1. **不存在双库分裂**：生产 `.env` 只配 `DATABASE_PATH`，代码兜底的 `DATABASE_URL` 会落到 `~/product-db/backend/product_db.db`
   —— 但 `readlink -f ~/product-db` = `/opt/product-db`（软链接），实测同一文件。**隐患仍在**（软链接一旦丢失，
   SQLite 会静默新建空库且 `/api/health` 照样 200），但当前无问题。
2. `AGENT_API_BASE` 生产已显式配 `127.0.0.1:8000`，代码兜底值 8002 未生效。
3. BOM 模板快照含 J 列成本的数量 = **0** → 模板成本泄漏不可达。
4. `products.parent_id` 非空的产品 = **0** → 「variants 内嵌成本未裁剪」不可达。
5. `products.created_by` 为 NULL 的有 **377/396**（导入创建）→ 产品实质是全站共享，
   「产品详情缺归属校验」应视为设计不一致，不是漏洞。

**D) 未修（已记录，等指示）**：折扣率 `0` 被 `or 100` 当未设置（8 处）、品类父子可成环、报价单号竞态、
`GET` 方案 BOM 快照会写库、导入非数字价格裸 `float()`、前端列表并发无序号保护、备份无异地副本、
E2E 大量容忍断言与 CI 不含 E2E、`.env.example` 限流值落后于代码等。

**测试:** backend **478 passed** (1 skipped, +9) / vitest **78 passed** (+7) / vue-tsc 0

## 历史变更 (2026-09-21, R40)

### R40: 导出文件名带客户与项目名 + 修掉中文文件名的编码缺陷 (2026-09-21)

**文件名方案**（便于在下载目录里区分）：

| 导出 | 文件名 |
|---|---|
| 报价单 | `报价单_{客户}_{项目标题}_{编号}.xlsx` → 例：`报价单_SMC_SMC-会议室环境检测_QT-20260918-001.xlsx` |
| 方案 BOM | `BOM_{客户}_{方案名}_id{方案ID}.xlsx` → 例：`BOM_麦当劳（广州）_麦当劳广州-空调集控_id30.xlsx` |
| 产品清单 | `产品清单_{YYYYMMDD}.xlsx`（全库导出、无客户/项目维度，用日期区分） |
| 产品规格书 | `产品规格书_{产品名}_{型号}.pdf` |

**新增 `app/utils/helpers.py` 两个工具**：
- `safe_filename_part()` —— 清理客户名/项目名里的 `/ \ : * ? " < > |` 与控制字符、压缩空白、按 40 字截断。客户名是自由输入，直接拼进文件名可能带出目录，或把 `Content-Disposition` 截断。
- `attachment_disposition()` —— 双写 `filename="<ASCII 回退>"` + `filename*=UTF-8''<百分号编码>`。HTTP header 只能放 latin-1，中文名必须走 `filename*`，同时保留 ASCII 回退兼容不支持它的老客户端。

**顺带修掉一个隐藏很深的缺陷（原以为是 weasyprint 没装，其实是编码异常）**：规格书原来的 header 是 `filename={中文产品名}-spec-sheet.pdf`，而 Starlette 在构造响应时就按 latin-1 编码 header → **抛 UnicodeEncodeError，被 `except` 吞掉，于是永远走 HTML 兜底**。全库 348 个中文名产品点「下载规格书」拿到的都是一个没有文件名的 HTML 页面，而不是 PDF。改成 `attachment_disposition()` 后 PDF 分支才真正可达。
> 排查弯路：一开始从「生产返回 text/html」推断 `shutil.which("weasyprint")` 为空，实际 `systemctl cat product-db` 显示 `Environment=PATH=/opt/product-db/backend/venv/bin:...`，weasyprint 一直在 PATH 里 —— 是 header 编码异常把它打回了兜底。教训：**先看日志里的 warning，再猜环境**。
> 另把 `spec_sheet` 的 `finally` 加了空值保护（临时文件创建失败时不会再 NameError）。

**生产验证**：四类导出实测响应头（`filename*` 解码后）分别为
`报价单_SMC_SMC-会议室环境检测_QT-20260918-001.xlsx`、`BOM_麦当劳（广州）_麦当劳广州-空调集控_id30.xlsx`、`产品清单_20260921.xlsx`、`产品规格书_智能电流互感器_CT303 CT305 CT310.pdf`；规格书实测为真 PDF（37926 字节、`%PDF-` 魔数）。四者均带 ASCII 回退名。

**测试:** backend **469 passed** (1 skipped, +5) —— 文件名清理、四类导出的 Content-Disposition；既有 spec-sheet 用例改为显式关掉 weasyprint 来覆盖兜底分支

## 历史变更 (2026-09-21, R39)

### R39: 报价单税率统一 13% (2026-09-21)

**问题**：`quotations.tax_rate` 一直落在 0 —— model 与 schema 默认值都是 0，前端也没有设置入口（R21 把报价单页的税率信息行移除了）。而导出的 xlsx 备注行会写「税率 N%」→ **客户拿到的报价单印着「税率 0%」**。同时 Hermes 侧创建报价单的脚本（`create_quotation.py`）写的是 13，两边长期不一致。

| 改动 | 内容 |
|---|---|
| 默认值 | `models/quotation.py` + `schemas/quotation.py`：0 → **13**；显式传入时仍以传入值为准，不写死 |
| 存量回填 | 迁移 `f6a7b8c9d0e1` 把 0/NULL 一并改成 13（否则老报价单导出仍是 0%）。**不可逆**：0 与 NULL 无法区分，降级一律写回 0 会误改本就 13% 的行 → `downgrade` 不动数据 |
| 展示格式 | 导出备注行改用 `_fmt_rate()`：`Numeric(5,2)` 取出来是 `13.00`，原来会打成「税率 13.0%」，现在按 **「税率 13%」** 展示 |
| **含税口径** | 明确口径：**单价与成本价均为含税价**，合计 = `Σ(数量 × 含税单价 × 折扣%)`，**不要再乘税率**（历史口径本就如此，13% 只是说明文字）。导出备注改为「价格为含税价（含 13% 增值税）」；`Product.base_price/cost_price`、`Quotation.total_amount` 三处补了口径注释，防止后续误做二次计税 |
| Hermes 侧 | `qty-assessment-workflow.md` 的创建模板 `tax_rate` 0 → 13（`create_quotation.py` 本就是 13；该侧文档无「不含税」等相反口径） |
| 前端展示 | 报价单列表列头「金额」→「**金额（含税）**」；详情页信息区加**只读**项「税率（含税）13%」、合计行改为「**合计（含税）**」（R21 曾移除该页的税率信息行，这次以只读形式加回，不提供编辑入口）；税率格式化复用「去尾零」口径，页面上不会出现「13.0%」 |

**生产验证**：存量 7 张全部回填为 13；导出 xlsx 备注行确认为「注：本报价单有效期 15 天；价格为含税价（含 13% 增值税）。」；新建报价单默认 `tax_rate=13`（临时单建后即删）；**浏览器实测**报价单列表表头为「金额（含税）」、详情页为「税率（含税）13%」与「合计（含税）」，DOM 全文无「13.0%」，控制台无报错。

**测试:** backend **464 passed** (1 skipped, +3：默认 13 / 显式值可覆盖 / 导出备注含含税口径与税率) / vitest **71 passed** (+2：列表列头含税、详情页税率与合计含税) / vue-tsc 0

> 注：税率可以**看**但不能**改**（R21 有意移除编辑入口，本次只加只读展示）。若以后不同客户需要不同税率，需另开一项（涉及前端表单、schema 校验、导出三处）。
> 另：详情页合计行右对齐，窄视口下需要横向滚动才能看到（R21 加的合计行就有此特性，非本次引入）。

## 历史变更 (2026-09-21, R38)

### R38: 探针与静态资源豁免限流 + 全局限额放宽 (2026-09-21)

R36 的日报在 09-18~09-20 连续告警「探针 fail」，追查后是**探针自己被限流**：09-18 起每天 380+ 次 429。

**根因**：探针 2 请求/2 分钟（health + 首页）= 1440 次/天，而全局限流是按 IP 的 **200/天** → 约 3.3 小时打满，此后全天 429（应用重启会清零，所以当天早上常「恢复正常」）。
代价不只是误报：持续 fail 会**污染探针状态机** —— 该时段真发生宕机也不会再产生新告警。

**为什么只能在中间件层豁免**：slowapi 的限流规则一律按「解析到的 handler 名字」匹配，而 SPA catch-all `/product-db/{full_path:path}` 注册在最后、遮蔽所有 handler → **`@limiter.exempt` 与 `@limiter.limit` 全都失效**，只有 `default_limits` 生效。新增 `RateLimitMiddleware(SlowAPIMiddleware)`，进 slowapi 之前按路径放行：
`/product-db/api/health`、`/product-db`（首页）、`/product-db/assets/`、uploads（静态资源与图片，逐个计入配额会让正常浏览很快触顶）。

**顺带放宽额度**：200/天 → **3000/天**、60/分 → **120/分**。依据：单个 SPA 用户正常浏览就可能超过 200/天（近 5 天实测有 1 次真实用户 IP 被限流），且探针与 Hermes agent 都从服务器本机 IP 出发、共用同一份额度。

**生产验证**：部署后连打 250 次 `/api/health` → **250 个 200**（旧实现第 ~200 次起 429）；紧接着同 IP 打 20 次普通 API → 全 200（证明未占用配额）。回归测试已验证「关掉豁免即失败」，不是空转用例。

**测试:** backend **461 passed** (1 skipped, +3) / vitest 69 passed / vue-tsc 0

## 历史变更 (2026-09-21, R37)

### R37: 成本价可见性 —— 统一判定 + 补漏 + 按用户三态覆盖 (2026-09-21)

起因是「给每个用户单独设置成本价显示权限」。评估阶段先发现：**现有的「成本价对非管理员隐藏」本身就是漏的**，所以本次分三步做——统一判定、补漏、再加按用户覆盖。

**A) 泄漏面（评估时实测确认，共 4 类）**
| 位置 | 问题 |
|------|------|
| `GET /solutions`、`/solutions/{id}` | 直接返回 `Solution.to_dict()`（含 `total_cost`）与 `SolutionItem.to_dict()`（含 `product_cost_price`），**方案路径从未接过字段可见性** |
| `GET/POST/PUT /solutions/{id}/items` | 三个条目接口同样带成本 |
| `PUT /solutions/{id}/bom-snapshot` | 直接返回落库快照，J 列成本原样回传 |
| `GET /products/export` | 只读全局开关、不看用户 |

根因：字段可见性只认 `cost_price` 这一个键名，而方案用的是 `total_cost` / `product_cost_price`，两个键名都不在覆盖范围内。

**B) 统一判定入口（`app/services/field_visibility.py`）**
- `cost_visible(user, db)` —— 唯一判定：admin 恒可见 → 按用户覆盖 → 全局开关
- `hide_cost_in(data, user, db)` —— 统一裁掉 `cost_price` / `product_cost_price` / `total_cost`（含一层 `items`）
- `apply_field_visibility(data, user, db)` —— 产品序列化入口：成本走 `cost_visible`（支持覆盖），其余字段仍只看全局
- 删掉三套各自实现（products 内联读全局、quotations `_should_hide_cost`、bom_templates `_cost_visible`）

> 教训：删 `_cost_visible` 时**漏了一个调用点**（`get_bom_snapshot`），是靠测试 `NameError` 才发现的。删符号前先 grep 全量引用。

**C) 「保存即归零」数据丢失（读侧过滤的写侧后果）**
成本对非管理员隐藏后，BOM 编辑器保存时仍会把成本列原样回传（值来自被裁掉的读结果 → 0/None），而后端是整份替换/重建 → **一次保存就把库里的成本抹掉**。
- 方案：看不到成本时丢弃客户端提交的所有 J 单元格，再补回服务端已有的 J（`_keep_server_cost`）
- 报价单：看不到成本时不采信客户端 `cost`，沿用旧快照的 `cost_price`（旧快照没有该键则不写入，而不是写 0）
- 附带修掉让上面两处失效的匹配缺陷：旧行原来只按 `sort_order` 匹配（假定等于行号），而条目不一定有 sort_order → 匹配不到，`specs/image_url/厂商` 与成本全保不下来。改为 **SKU 优先、位置兜底**
- 前端也一并收紧：无权限时不上报 `cost` / `J` 单元格

**D) 按用户三态覆盖（本次需求本体）**
- `users.can_view_cost`：`NULL`=跟随全局（默认，存量用户行为不变）/ `true`=允许 / `false`=禁止；admin 恒可见不受影响
- 迁移 `e5f6a7b8c9d0`（可空、**不给 server_default**——给了等于把存量用户一次性改权）
- `PUT /admin/users/{uid}`：该字段**不能交给 `apply_partial_update`**（它跳过 `None`），否则「改回跟随全局」永远存不下去 → 按 `model_fields_set` 单独处理
- `GET /auth/session` 增加生效后的 `can_view_cost`；前端 `App.vue` provide 后，方案/报价单/产品详情/产品表单/BOM 表格无权限时不渲染成本列（默认 false，避免加载前闪出成本）
- 管理页用户弹窗加三态下拉（仅对非 admin 显示），用户表加「成本价」列

**E) 生产验证（真实数据、非模拟）**
| 场景 | 结果 |
|------|------|
| 全局关 + 覆盖 NULL | 看不到（`cost_price=None`，`session.can_view_cost=False`） |
| 覆盖 true（全局仍关） | 看得到 `525.0` —— 覆盖优先于全局 |
| 全局开 + 覆盖 false | 仍看不到 —— 反向覆盖生效 |
| 全局开 + 覆盖 NULL | 看得到 —— 跟随全局（两个用户交叉验证） |
| 方案泄漏封堵 | 非管理员读自己的方案 30：`total_cost`/`product_cost_price` 均无；单独开放后 `total_cost=2415.0` 可见；复原后再次隐藏 |
| 产品导出 | 非管理员导出 xlsx 的 M 列全空 |
| 现场复原 | `can_view_cost` 全部回 NULL、全局开关回关 |

> 验证方式说明：为免在生产建账号，用服务器上的 SECRET_KEY 临时自签 5 分钟时效的 token 以真实非管理员身份只读验证，事后无残留（用户权限值、全局开关均已复原）。

**F) 顺带取证：历史数据是否已被清零** —— 方案快照 3 条中 0 条「全为 0」；报价单 174 条中 8 条成本=0，与产品当前成本对照有 3 条「疑似」，但**同一张报价单内其它条目保留了成本**（与「整单保存被清零」的机制不符），更可能是建单时产品尚无成本（快照本就是历史值）。结论：**不做数据回填**（拿今天的成本改历史报价等于篡改历史）。

**测试:** backend **458 passed** (1 skipped, +10) / vitest 69 passed / vue-tsc 0

**变更统计:** 19 文件（4 个提交：`b34492d` 统一判定与补漏 → `a1756b1` 修归零 → `2637e61` 按用户覆盖 → 文档）

## 历史变更 (2026-09-17, R36)

### R36: 日报加入整体运行情况 + 修 v1 三处数据错误 (2026-09-17)

生产服务器上的 Hermes 定时任务 `7f01bb46e256`（每日 21:00，`no_agent` 脚本，投递飞书群）此前只报**使用情况**，运维侧完全空白，而且有三处数据错误。本次重写为 v2。

**A) 新增「🖥️ 整体运行情况」**（全部无需 sudo）
| 维度 | 内容 |
|------|------|
| 服务 | `product-db`/`nginx` 是否 active、当日启动次数（数 uvicorn 的 `Started server process`）、**systemd 自动重启次数**（`NRestarts`） |
| 请求 | 当日请求总数、4xx/5xx、探针请求数、ERROR 日志行数与 Traceback 次数 |
| 探针 | `health.state` 当前状态 + `health.log` 当日 FAIL 次数 |
| 资源 | 根分区使用率、可用内存、1 分钟负载、系统运行天数 |
| 备份 | 最新快照时间与年龄、份数、体积 |
| 数据 | DB 与 WAL 大小、上传目录体积与文件数 |

**B) 阈值告警 + 输出分档**：阈值集中在 `TH`（磁盘 85%、内存可用 200MB、5xx 5 次、ERROR 20 行、快照年龄 26h）。**无告警时只输出三行摘要**（头部 + 使用行 + 运行行），命中任一阈值才输出完整报告并在开头列出告警项——避免每天在飞书群里刷一大段。

**C) 修掉 v1 的三处数据错误**
| 问题 | 现象 | 修法 |
|------|------|------|
| 快照正则写错 | 文件名是 `product_db.db.bak.20260917_033057`（带下划线），`\d+$` 匹配不上 → **每天都误报「没有任何数据库快照」** | 正则改为 `\d+_\d+$` |
| 时区错位 | DB 里 `created_at` 存的是 **naive UTC**（实测 UTC 03:25 = 本地 11:25），按 `date(created_at)` 切分等于把「本地日」错位成 **08:00 → 次日 08:00**；09-16 的报告因此扫进 179 次登录（含次日凌晨数据），v1 自 8 月起一直如此 | 新增 `utc_bounds()` 把本地日换算成 UTC 边界，`to_local()` 把显示时间转回本地；顺带用上 `created_at` 索引 |
| 重启计数取错标记 | `Starting product-db.service` 在 journal 里**根本不存在**（实测恒为 0） | 改为数 uvicorn 的 `Started server process`；并把重启告警换成 `NRestarts`（自动重启才是崩溃信号，人工部署重启不该算异常） |

**D) 活跃时长不再被探针污染**：R35 上线了每 2 分钟一次的可用性探针（约 720 次/天），v1 的统计会把它算成用户请求（实测当天 442 次探针流量）。v2 排除 `/product-db/api/health` 与本机/自身公网 IP。

**E) 脚本归属：仓库版本化 + 部署时复制**（**不能用软链接**）
- 正文入仓 `deploy/hermes/pdb_daily_report.py`（唯一修改处），部署时复制到 `~/.hermes/scripts/`
- ⚠️ 曾经试过「服务器软链接指向仓库文件」，**被 Hermes 直接拦死**：`cron/scheduler.py` 在 fire 时做
  ```python
  path = (scripts_dir / raw).resolve()          # resolve() 会展开软链接
  path.relative_to(scripts_dir_resolved)        # → ValueError
  return False, "Blocked: script path resolves outside the scripts directory"
  ```
  软链接解析后落在 `/opt/product-db/...`，不在 `~/.hermes/scripts/` 内 → 任务当天 21:00 会静默失败。硬链接也不行（`git pull` 会写新文件、悄悄断开）。**结论：必须复制**。
- 改脚本的完整流程：本机改 → push → 服务器 `git pull` + `install -m 700 deploy/hermes/pdb_daily_report.py ~/.hermes/scripts/` → 手跑一次确认

**F) 按用户反馈的迭代（v2.1）**：第一版日报里「登录 2 人 / 181 次」看不出是谁、各用了多久
- **极简模式改为每账号一行**：`👥 tong: 登录 180 次（峰值 52 次/分，疑似自动化测试）· 活跃时长 38 分钟 · 跨度 413 分钟 · 区域 西安市, 中国`；单账号一分钟内登录 ≥10 次即标注「疑似自动化测试」（那 181 次实测是 00:18–00:20 的一轮浏览器测试爆发，峰值 52 次/分，不是异常）；无登录记录的访问单列「未识别」；超过 5 个账号折叠为一行
- **两个时长口径，`活跃时长` 在前**：**活跃时长** = 至少发过一次请求的分钟数（下界，用户真正在用的时长）+ **跨度** = 首末请求间隔（含空闲）。只给跨度会把「开着页面没动」算成在干活 —— 实测某 IP 6 小时里只有 278 个请求、跨度却有 361 分钟。跨度按半开区间算（右端 +1），否则会出现「跨度 0 分钟（有请求 2 分钟）」
- **IP 解析为登录区域**：调应用自己的 venv + ip2region 离线库（`REGION_PY`/`REGION_XDB`）把 IP 解析成「城市, 国家」，口径与登录接口 `_format_offline_region` 一致；离线库查不到的（IPv6、库外地址段）退回 `login_logs.region`。极简行用区域替代裸 IP（多区域去重、超 3 个折叠），完整报告逐 IP 行写「西安市, 中国（113.132.197.169）」保留原始凭据
  - 顺带查明：`login_logs.region` 在 09-17 11:29 部署 R30 之前大量为空（UTC 16 点那 192 条里 182 条空，因为当时只有 ipapi.co 在线查询且额度耗尽），**部署后 8 条全部有值** —— 属历史数据，不是仍在发生的故障
- **归属修正**：同一出口 IP 被多个账号共用时（tong/admin 就是同一台机器），旧的 IP→账号「最后登录者独占」映射会让 09-16 的 tong 显示「活跃 0 分钟」而请求全算给 admin。改为**逐请求判定**：取该 IP 上时间不晚于该请求的最近一次成功登录作为归属；之前没有任何登录的请求归「未识别」
- 完整报告把原来的「👥 登录用户」与「⏱️ 活跃时长」两节**合并为「账号使用情况」**，一个账号一段（登录次数/时间/峰值 → 活跃时长/跨度 → 逐 IP 明细含区域）

**验证:** 09-16 与 09-17 两天实跑对比（09-16 登录数从 179 修正为 5，与服务端 v1 报告同一时段的真实登录吻合）；极简模式与告警模式分别用真实数据与强制阈值验证；账号归属用 09-16（tong/admin 共用 IP）与 09-17（单账号双 IP）两天交叉核对。

## 历史变更 (2026-09-17, R35)

### R35: 收敛暴露面与静默失败 + 运维配置入仓 + 导入写路径缺陷 (2026-09-17)

审查清单里剩余可落地项的一次性处理。**其中一条是在补测试时现挖出来的生产缺陷**。

**A) 生产实测确认的真实缺陷：Excel 导入遇到不匹配的品类会整批 500（`c7c82a1`）**
- `products.category_id` 是 `NOT NULL`（模型与生产库一致，实测 `notnull=1`、0 个 NULL），而 `import_confirm` 在品类名匹配不到时插 `None` → `IntegrityError` → **500 Internal Server Error**；因为只在最后 `commit` 一次，**整批数据全丢且用户只看到「Internal Server Error」**
- 常见触发：表格里没有「品类」列，或品类名与系统里不一致（含模糊匹配也匹配不到时）
- 修复：改为「先整体解析+校验，再落库」，匹配不到的品类名汇总成 **400 + 具体名字列表**；全部行不合格也返回 400 说明原因（不再是 `imported=0` 的假成功）
- 生产验证：修复前同一请求 **500** + journald `IntegrityError`；修复后 **400** + 「以下品类在系统中不存在…绝不存在的品类ZZZ」，产品总数保持 396
- ⚠️ **行为变化**：导入现在**要求品类能匹配到已有品类**（表格必须有品类列且名字对得上），否则整批拒绝而不是部分成功

**B) 安全与边界（4 项）**
| 项 | 问题 | 修法 |
|----|------|------|
| SSRF 重定向绕过 | `excel_style._resolve_image` 用 `requests` 默认跟随 302/307，重定向目标不再过 `validate_url` → 盲 SSRF（图片来源 `image_url` 任意登录用户可写，导出即触发） | `allow_redirects=False` + 逐跳校验（≤3 跳），与 `products.py`/`storage` 一致 |
| `/ai/stats` 口径溢出 | 全站 AI 用量（`total`/`total_tokens_*`）返回给任意登录用户 | 全局口径仅 admin；侧边栏只展示 `user_*`，界面不受影响 |
| 导入预览内存 | `import-preview` 把整个文件读进内存且无上限 | 改用 `storage.read_limited` + `FILE_MAX_SIZE` |
| 计数竞态 | `GET /products/{id}` 的 `view_count`、报价单导出的 `download_count` 是读-改-写 | 改 SQL 层 `coalesce(x,0)+1` 自增（并发不丢计数，GET 不再长持写锁） |

**C) 静默失败 8 处**：OCR 失败 / AI 提取回落 / 读自定义提示词 / agent 提示词与用量统计 / 文件清理 / llm-models 拉取与 JSON 解析 —— 原来是 `except: pass` 或只记 `debug`（生产 sink 是 INFO，线上不可见），统一升为 `warning` 并带异常信息；其中 3 处是**裸 `except:`**（会连 `KeyboardInterrupt` 一起吞）。

**D) 工程与运维**
- 删除前端未使用依赖 `exceljs` / `jszip` / `@types/dompurify`（全仓零引用，实测确认）
- systemd 主 unit 与 UMask drop-in **版本化入仓**（`deploy/systemd/product-db.service`、`deploy/systemd/product-db.service.d/umask.conf`），此前只以文档内联代码块存在，改错了没人能发现
- 补 `import-confirm` 写路径测试（此前**零覆盖**）

**E) 明确不改（附理由）**：`/agent/config` 向登录用户返回 `db_path`/`upload_dir`
- 这两个路径本就是 **agent 提示词的必需内容**（前端把它们填进 `{{DB_PATH}}`/`{{UPLOAD_DIR}}` 占位符），且 `db_path` 的默认值已硬编码在公开的 JS bundle 里；要真正收敛得把提示词模板替换搬到后端，属改造成本高于收益
- 这不是「也没人管」，而是**按设计暴露**，记在此处避免以后反复讨论

**测试:** backend **448 passed** (1 skipped, +9) / vitest 69 passed / vue-tsc 0

**变更统计:** 15 文件

## 历史变更 (2026-09-17, R34)

### R34: 文档与运维 — 漂移校正 + 可用性探针 + 重启就绪门控 (2026-09-17)

安全/功能/数据层三批之后的最后一批，处理审查里「运维没人管」的那一类问题。

**1) 部署流程补上迁移（这是「迁移静默滞后」的根源）**
- 部署命令改为：`git pull` → `pip install -r requirements.txt` → **`venv/bin/alembic upgrade head`** → `deploy/restart-ready.sh`
- 此前部署流程里没有迁移步骤、全靠手工执行 → `created_by` 列、`product_categories` 表、一批索引在生产静默滞后了数月（R33 才补齐）

**2) 重启就绪门控**（新增 `deploy/restart-ready.sh`）
- 裸 `systemctl restart` 期间 uvicorn 不监听，nginx 短暂返回 502，且失败与否无判据
- 新脚本：记录重启前 revision → restart → 轮询健康接口直到 200（默认 30s）→ 再验经 nginx 的接口与前端首页（能发现 dist 丢失导致的 503）；失败打印 `journalctl` 与回滚命令并非 0 退出（**不自动回滚**，避免掩盖问题）
- **实测（0.15s 间隔打公开入口）**：应用就绪 **1s**、对外 502 窗口 **≈1.3s** —— 早先文档写的「5-8s」是错的（那是部署时操作者 `sleep 4` 的等待，不是用户可见窗口）。因此该脚本的主要价值是「部署失败立刻可见 + 有回滚提示」，而非消灭这 1.3s
- 配套维护页 `static/maintenance.html`（每 5s 自动探测健康接口，恢复后回首页）为**可选项**（窗口仅 1.3s，收益有限）；nginx `error_page 502 503 504` 的改法已在 DEPLOY.md 给出，配置属 root **需人工 sudo 执行**

**3) 最小可用性探针**（新增 `deploy/health-check.sh` + `product-db-healthcheck.{service,timer}`，已在生产装好并实测）
- 此前**没有任何可用性告警**：进程崩了只有 `Restart=always` 静默拉起，dist 丢失会让首页 503，两者只能靠用户反馈
- **双频探测**：本地接口 + 前端首页**每 2 分钟**（直连 `127.0.0.1:8000`，不过 nginx、不耗配额）；经 nginx 的公开入口**每 30 分钟**（或本地已异常时立即补测）
- 为什么公开入口要降频（实测踩到）：全局限流 200/天，2 分钟一次 = **720 次/天** → 探针先打满配额、再把 429 持续误报成「服务不可用」。给它加 `@limiter.exempt` **实测无效** —— slowapi 的 `SlowAPIMiddleware` 用 `_find_route_handler()` 取「最后一个 FULL 匹配的路由」，而 SPA catch-all `/product-db/{full_path:path}` 注册在后、也匹配 `/health` → 解析到 `serve_spa`，函数级豁免永不生效（连续打 65 次仍 429）。根因注释留在 `main.py` 的 `health()` 里
- **只在状态变化时**写一条显著日志（持续故障写「FAIL（持续）」，不刷屏）；可选 webhook（`ALERT_WEBHOOK` + `ALERT_WEBHOOK_STYLE=feishu|text`）
- 实测：健康路径 exit 0；死端口模拟故障 exit 1 并按 `FAIL`→`OK 服务已恢复（上一状态: fail）` 正确记录迁移

**4) 文档漂移校正（逐条实测过口径）**

| 位置 | 原写法 | 实测 |
|------|--------|------|
| DEPLOY.md 日志节 | stdlib `logging.getLogger` 21 处 | **23 处 / 10 个文件**（写 21 是我上一批的错） |
| DEPLOY.md 备份节 | 「当前无自动备份」（与同章自相矛盾） | timer 早已落地，**实测 2026-09-17 03:30:57 成功运行** |
| AGENTS.md 技术栈 | `PostgreSQL (prod)` | SQLite（dev/prod 都是，生产库为唯一权威源） |
| AGENTS.md 技术栈 | `Docker Compose + Nginx` | systemd + nginx + rsync（compose 是早期实验、非生产路径） |
| AGENTS.md 测试数 | `pytest 372 tests`（两处） | **440 collected（439 passed + 1 skipped）** |
| AGENTS.md E2E | `full-regression 51 tests` | **53**（各文件实测：53/17/19/4/2/1 = 96） |
| AGENTS.md R21.1 | 括号内相加 104 ≠ 96 | 标注为当时笔误并给出当前分布 |
| AGENTS.md 结构树 | routers 只列 12 个文件名 | 补 `product_files.py`、`agent.py`（实际 14 ✓） |
| AGENTS.md 结构树 | `router.ts 16 条路由` | 18 条 path（16 组件路由 + 2 redirect） |
| AGENTS.md R28 | 「生产尚无自动备份」 | 标注 2026-09 已落地 + 实测运行时间 |
| AGENTS.md：`32 张业务表` | — | **实测正确**（34 个表 − `alembic_version` − `sqlite_sequence` = 32，含非 ORM 的 `product_categories`），不改 |

**测试:** backend 439 passed (1 skipped)、vitest 69 passed、vue-tsc 0（本批未动应用代码，仅脚本/静态页/文档）

**变更统计:** 8 文件（2 脚本 + 2 unit + 1 静态页 + 3 文档），+约 250

## 历史变更 (2026-09-17, R33)

### R33: 数据层一致性 — 让「从零建库」可用并与生产/模型对齐 (2026-09-17)

起点是审查里的一条：「迁移链里完全没有 `product_categories`」。实测比对「alembic 全新库 vs 生产库」后发现比预想严重得多 —— **`alembic upgrade head` 从零根本跑不通**，且建出的结构与生产/模型不一致。

**修复的 4 处（都能定位到具体报错）**
1. **全新库第一步就崩**：`fix_explicit_ddl` 无条件 `DROP TABLE download_tickets`，而 `DownloadTicket` 模型已在 R27 删除、全新库不会建它 → `OperationalError: no such table: download_tickets`。改为 `DROP TABLE IF EXISTS`（upgrade/downgrade 两处）
2. **第二步崩**：`b2c3d4e5f6a7` 无条件 `ADD COLUMN is_link`，而显式 DDL 是照当时的模型写的、已含该列 → `duplicate column name: is_link`。改为先探测列是否存在
3. **3.9 下迁移链不可用**：`c3d4e5f6a7b8` 的 `down_revision: str | None` 是模块级注解、又没有 `from __future__ import annotations` → Python 3.9 导入即抛 `TypeError: unsupported operand type(s) for |`。本地（3.9）因此完全不能跑迁移，生产（3.11）才没暴露
4. **全新库缺表/缺列/缺索引**：新增收敛迁移 `d4e5f6a7b8c9`（幂等）
   - 建 `product_categories`（非 ORM 表，历史链一处都没有；缺它 → 产品按品类过滤、产品导入、AI 上下文全报 `no such table`）+ `idx_pc_category`，DDL 按生产实测原样照搬（FK 指向的是 `device_categories`）
   - 补全新库缺的 **16 处列**（`created_by` 系列 + 字典表 `description/accuracy/resolution`、`manufacturers.sort_order`、`quotations.download_count`）
   - 补 **26 个索引**：模型 `index=True` 但两边都缺的 15 个（含 **11 个 `created_by`**）+ 生产手工建而全新库没有的 11 个；按「列组合」判重，避免同列出现两个同义索引
   - 清掉全新库会多出来的死表 `download_tickets`

**收敛验证（实测）**
- 全新库 vs 生产：表 **33 = 33**、列无缺、索引列组合**双向一致**
- 生产副本上跑该迁移：索引 32 → 47（**只 +15**，即那 15 个模型索引），数据零变动（products 396 / login_logs 678 / product_categories 731）

**生产执行与验证**：`alembic upgrade head` → `c3d4e5f6a7b8` → `d4e5f6a7b8c9`，索引 32 → 47，`created_by` 索引 0 → **11**，数据 396/731 不变，`integrity_check` = ok；随后实打会用到这两处的接口——`/products`（created_by 归属过滤）200、`/products?category_id=1`（关联表）200、`/categories/tree` 200，journald 2 分钟内错误关键字命中 0

**测试:** backend **439 passed** (1 skipped, +2)：`tests/test_migrations.py` —— 从零建库可用性（表/列/索引断言）+ 重复 `upgrade` 幂等

**遗留（留给文档/运维批处理）**：部署命令里没有 `alembic upgrade head`，迁移目前靠手工执行 —— 这是「迁移静默滞后」的根源，应在 DEPLOY.md 的部署流程里补上

**变更统计:** 5 文件, +309/-66

## 历史变更 (2026-09-17, R32)

### R32: 安全批量修复 ② — 功能缺陷（导入页不可用、对比入口参数、长密码、图片清理）(2026-09-17)

续 R31 的代码审查，本批 4 项都是**已在生产成立的功能缺陷**。

**1) Excel 导入页整体不可用**
- 根因：`ImportView.vue` 的 `onFileSelect` 里 `const headers: Record<string,string> = {}` **遮蔽了同名的 `headers` ref**，`headers.value = res.headers` 写到了局部对象上 → 模板 `v-if="headers.length"` 恒为假，选完文件后列映射表/导入按钮永不出现
- 修复：局部变量改名 `authHeaders`；两处 `fetch` 补 `res.ok` 校验（预览失败提示后端错误、导入失败不再谎报「成功导入 N 条」）

**2) 对比页入口参数不一致 → 2/3 条入口是空页**
- 根因：`AiChat.vue` 与 `SolutionDetailView.vue` 跳转用 `?product_ids=`，而 `ProductCompareView` 只读 `route.query.ids`（同一文件另一处 `AiChat.vue:321` 用的是 `ids`，属自相矛盾）
- 修复：跳转统一为 `ids=`；后端 API 的 `product_ids` 是另一回事，未动。E2E 断言从「body 可见」改为「是否真的带着 ids 调了对比接口」（旧断言对参数写错也无感）

**3) 密码 >72 字节可注册但永远登录失败**
- 根因：`hash_password` 截断到 72 字节，`verify_password` 不截断 → bcrypt 对 >72 字节抛 `ValueError`，被 `except (ValueError, TypeError)` 吞成「密码错误」。约 25 个中文字符即触发
- 修复：verify 同样截断（与 bcrypt 的固有语义一致）；**存量用户不受影响**——他们的哈希本来就是按截断值生成的，修复后原长密码可直接登录

**4) 产品图片文件从不被清理（静默）**
- 根因：`_cleanup_image_files` 里 `upload_root` 带 `..` 而 `filepath` 被 `normpath` 归一化 → `filepath.startswith(upload_root)` **恒为 False**，删除产品/替换图片时本地文件永不删除，孤儿文件累积且无任何报错
- 修复：改用 `Path.resolve()` + `is_relative_to`（与 `storage.delete_file` 一致），并保留 `../` 越界防护

**测试:** backend **437 passed** (1 skipped, +8) / vitest **69 passed** (+3) / vue-tsc 0
- 导入页 3 条：列映射渲染（正是遮蔽 bug 的回归）、预览失败提示、导入失败不谎报
- 长密码 6 条：5 种长度的 hash/verify 往返 + API 登录端到端
- 图片清理 2 条：本地文件被删 + `../` 越界不删

**生产验证（部署后实测）:** 部署产物里 2 处跳转为 `compare?ids=`（剩余 1 处 `product_ids` 是后端 API 参数，正确）；用 **96 字节**密码的临时用户登录 → **HTTP 200**（旧实现必然 401），临时用户已清理；数据零污染（396/731/6/6/10 与变更前一致）

**补充 — 真机走查发现并当日修复（`ab84676`）:** 用浏览器在生产走查导入流程，第 1、2 步通过（列映射正常渲染、提示「成功导入 0 条」不谎报），但第 3 步暴露一个遗漏：上传坏文件后错误提示正确，**上一次成功预览的「列映射」表格与「确认导入 N 条」按钮仍留在页面上** → 用户可能在失败提示之后把上一个文件的残留数据再导一遍。已改为在预览异常分支清空 `headers/rows/previewRows/mapping`。第二轮复验：三步全 PASS，失败后 DOM 中「列映射」标题/表格/下拉框/按钮数量均为 0，产品总数仍为 396。
> 附带核实：走查中观察到「一次选文件发两次预览请求」，经 vitest 断言（一次 change 只发一次请求）+ 页面事件计数（请求数与 change 事件数严格 1:1）确认是**自动化工具重复设置文件**所致，非应用重复提交。

**变更统计:** 9 文件, +195/-25

## 历史变更 (2026-09-17, R31)

### R31: 安全批量修复 ① — 上传加固 + 越权 + 主数据写权限 (2026-09-17)

来源：对全仓做的一次分方向代码审查（后端质量/安全/前端/测试运维），以下 4 项为**已逐条复核**的真实缺陷，每项带回归测试。

**1) 上传可写任意扩展名 + uploads 无鉴权静态托管 → 同源存储型 XSS（最严重）**
- 根因：`agent.py` 上传时 `mime_type` 直接采信客户端 `Content-Type`，扩展名取自用户文件名（`x.html` 谎报 `image/png` 即通过）；`main.py` 又把整个 uploads 目录无鉴权静态挂载，而 JWT 存在 `localStorage`、nginx 未加任何安全响应头 → 诱导管理员打开该 URL 即可读走 token 接管账号
- 修复：新增 `storage.detect_upload_extension()`，按**文件内容**判定（图片魔数 / OOXML 的 zip 内部结构 / OLE2 / 纯文本白名单），扩展名由服务端决定；`UploadsStaticFiles` 只放行允许上传的扩展名，200 响应统一加 `X-Content-Type-Options: nosniff`
- 安全性核对：生产 uploads 现存 **937** 个文件的扩展名（png/pdf/txt/jpg/xlsx/docx/json/jpeg/doc）**全部在白名单内**，不影响既有图片/文档访问

**2) `POST /quotations` 传他人 `solution_id` 可整体复制其方案（缺归属校验）**
- 修复：补 `check_ownership(sol, user, strict=True)`（同仓 `ai_tools.py` 同一动作本就有校验，属遗漏）

**3) BOM 快照/导出绕过成本价可见性**
- 根因：快照 J 列写死 `cost_price` 且原样返回；导出在有快照的分支完全不看 `show_cost`（该变量成了死变量）→ 管理员关掉成本可见性后普通用户照样导出逐条成本
- 修复：`get_bom_snapshot` 与 `_write_snapshot_to_xlsx` 都按 `show_cost` 剥离/跳过 J 列

**4) 主数据改归管理员（原为「任何登录用户可改删」）**
- 根因：`check_ownership(strict=False)` 对 `created_by IS NULL` 直接放行，而生产主数据几乎全为 NULL（实测 manufacturers 48/48、suppliers 55/55、dict_sensor_metrics 36/36、dict_comm_methods 18/18、dict_power_supplies 11/11、device_categories 42/50、dict_comm_protocols 15/17）
- 修复：新增 `auth.require_admin`，**29 个**主数据写接口（品类/规格定义/厂商/供应商/字典/BOM 模板）改用它；前端 `DictionariesView`/`CategoriesView`/`SuppliersView` 同步按角色隐藏编辑入口
- 业务数据（产品/方案/报价单）**不受影响**，仍按归属校验

**测试:** backend **429 passed** (1 skipped, +26) / vitest **66 passed** (+4) / vue-tsc 0
- 上传：13 条内容判定参数化 + 7 条端到端（含「.html 谎报 png 被拒且不落盘」「扩展名跟内容走」）
- 越权：他人方案 403 + 本人方案仍 201；BOM 快照/导出非 admin 无 J 列、admin 有
- 主数据：普通用户 5 类写操作 403 + admin 正常 + 普通用户业务写操作不受影响

**生产验证（部署后实测）:** 现存 png → 200 且带 `nosniff`；磁盘上真实存在的 `.html` → 两个挂载点均 **404**；普通用户 5 类主数据写操作全 **403**、admin 同请求 404/201；普通用户创建/删除自己的报价单正常（201/200）；数据零污染（396/731/48/55/6/6/10/17 与变更前一致，临时用户与探针数据已清理）

**变更统计:** 16 文件, +582/-85（含 4 个前端视图/测试）

## 历史变更 (2026-09-17, R30)

### R30: 登录审计加固 — 地区静默失效、XFF 免信代理、ip2region 离线化 (2026-09-17)

生产 L0–L4 全量测试暴露的两个问题都在「审计数据不可信」这条线上：登录日志「地区」大面积为空、限流可被伪造请求头绕过。前两项已随 `c8a06ac` 部署（本次补记入变更日志），第三项为本次改造。

**1) 地区静默失效**
- 根因：ipapi.co 免费额度耗尽时返回 **HTTP 200 + 纯文本付费提示**；旧实现直接 `resp.json()`，`JSONDecodeError` 被裸 `except Exception` 吞掉且只记 DEBUG（生产 sink 是 INFO）→ 静默变空。实测某日 189 条登录记录中 188 条地区为空，无人察觉
- 修复（`auth_routes.py`）：先判 content-type（非 JSON 走独立分支记 WARNING）、各失败分支均记 WARNING、结果加缓存（成功 24h / 失败 5min / 上限 2048 条）
- 生产验证：`login_logs` 恢复记录真实 IP 113.132.197.169 + "Xi'an, China"

**2) XFF 可绕过限流**
- 根因（`auth.py` `client_ip()`）：无条件采信 XFF 首跳 → 客户端自带一个 XFF 即可改写限流 key，同时绕过全局限流与登录爆破限流（10 次/300s），并污染 `login_logs` 的 IP/地区审计
- 修复：新增 `TRUSTED_PROXIES`（默认 `127.0.0.1,::1`），仅直连对端可信才采信转发头；优先 `X-Real-IP`，否则取 XFF **最右跳**（与 nginx `$proxy_add_x_forwarded_for` 的追加语义一致）
- 生产验证：连发 11 次、每次伪造不同 XFF，第 11 次仍 429

**3) IP 地区改为离线优先（本次）**
- 改造前：地区查询挂在登录必经路径上，每个陌生 IP 首次登录最多阻塞 **3s**，且完全依赖第三方免费配额
- 改造后：**ip2region 离线库为主，未命中才回落 ipapi.co**
  - 组件：`py-ip2region==3.0.4`（官方 Python binding，Apache-2.0）+ `backend/data/ip2region_v4.xdb`（11MB，入 git，随 `git pull` 下发）
  - 新增配置 `IP2REGION_XDB`（默认 `data/ip2region_v4.xdb`，相对 `backend/` 解析，不依赖进程 CWD）
  - 离线库返回 `国家|省份|城市|ISP|国家代码`，缺失字段为 `"0"`；保留地址段是 `Reserved|Reserved|Reserved|0|0` → **视同「查不到」回落在线**，而不是记成「在 Reserved 地区登录」
  - IPv6 地址查 v4 库必然抛错，属预期回落场景 → 只记 DEBUG，不刷 WARNING、不阻断登录
  - 库缺失/损坏 → 首次用到时记一次 WARNING 并永久回落在线（不阻断登录，且不每次刷日志）
  - 进程内单例 + `threading.Lock` 双检（同步路由跑在线程池里），首次加载预载 VectorIndex（512KB）
- 实测（本机 Python 3.9.6）：首次调用含加载 **1.37ms**，单次查询约 **6µs**（2000 次 12.3ms），命中离线库时外部请求 **0 次**；对比改造前最长 3s
- 生产实测：113.132.197.169 → 「西安市, 中国」（此前经 ipapi.co 得到 "Xi'an, China"）

**测试:**
- backend pytest: **403 passed** (1 skipped)，+13（离线命中不发外部请求 1 + Reserved 回落 1 + 库缺失只告警一次 1 + 查库异常回落 1 + 离线结果缓存 1 + 本地地址短路 1 + 返回格式 7）
- 原有在线分支的 13 条用例通过 fixture 强制「离线未命中」隔离，语义不变
- 基线核对（`pytest --collect-only` 实测）：R29 前 364 → R29 后 373（R29 记的 372 passed + 1 skipped 正确）→ c8a06ac +18 = 391 → 本次 +13 = 404

**文档:** `DEPLOY.md` 新增「IP 地区离线库」一节（SHA256 pin、验证命令、更新方式）与「为什么不加第二级兜底源」（生产 31/31 命中率实测，结论：不加，含再评估信号）；后端部署命令补 `pip install`，并去掉会静默丢弃服务器改动的 `git stash + stash drop`

**日志落点（本次实测发现，已写进代码注释）:** 地区相关的 WARNING 走 stdlib `logging.getLogger("uvicorn")`，落点是 **journald**（`journalctl -u product-db`），**不进** `backend/app.log` —— loguru 只接管自己的 logger，仓库里 21 处 `logging.getLogger` 同理（实测 `grep -c uvicorn app.log` = 0，而 `journalctl` 里能看到 `ip2region 离线库已加载`）。所以「地区静默失效」的告警在两处都要看，只看 `app.log` 会误判为「又没有告警」。

**变更统计:** 7 文件, +305/-25（`git diff --stat c8a06ac..bf81d95`，不含新增的 11MB 数据文件）

## 历史变更 (2026-09-16, R29)

### R29: 方案页 AI 多轮对话修复 — 会话 ID 类型 + 历史序列合法性 + DSML 还原 (2026-09-16)

**现象**: `solutions/{id}` 页 AI 方案助手只能聊一轮，第二轮起完全无响应（无报错、无提示）。

**根因 1 — 会话 ID 类型不匹配（P0，用户直接症状）**
- `schemas/ai.py` `AiChatRequest.conversation_id` 声明为 `Optional[str]`，前端 `JSON.stringify` 传的却是数字 → Pydantic v2 不做隐式转换 → **422 Unprocessable Entity**
- 前端 SSE 客户端（`api.ts` `streamAiChat`、`AiChat.vue`）只判 `res.body` 不判 `res.ok`，而 422 返回的是 JSON 错误体、不含任何 `data:` 行 → 生成器静默结束、不抛错不提示
- 引入于 R18 (`c58025a`) 的裸 dict → Pydantic schema 改造；R27 修好前端会话 ID 捕获（`conversationCaptured`）后引爆 —— 此前方案页 `chatCid` 恒为 `null`，歪打正着绕过了 422
- 影响面：方案页内嵌 AI **与**全局浮动 `AiChat.vue`（后者从 R18 起同样只能聊一轮）

**根因 2 — 多轮上下文消息序列非法（P1）**
- keyword-extraction / mock 路径只持久化 `tool` 消息、不写配对的 assistant `tool_calls`（`ai.py` 共 5 处）
- `get_messages_for_context` 原样拼回 → 孤儿 `tool` 行（`tool_call_id` 为空、无前置 `tool_calls`）
- DeepSeek 返回 **400**，异常被 `run_agent` 吞掉 → 静默降级到 mock agent → 第二轮答案是关键词傻搜结果（实测问"网关"库中有货，却答"没有找到匹配的产品"）
- 附带：`ORDER BY created_at` 无并列项，而同批写入的消息 `created_at` 精确到同一微秒 → 历史顺序不确定

**根因 3 — 工具声明缺失 + DSML 泄露（P1）**
- `ai.py` 自 commit `292d725` 起 `TOOL_DEFINITIONS` 只 import 未使用，`engine.chat()` 从未传 `tools=` → `run_agent` 里 `if msg.get("tool_calls")` 整段工具执行分支是死代码
- 模型被提示词要求调工具、却没拿到工具声明，只能把 DeepSeek 原生 tool-call 标记当**正文**输出
- Round 0 有 DSML 兜底解析，Round 1 没有 → 第二轮把这串原始标记直接流给用户
- 修复前被根因 2 的 400 掩盖（第二轮在 400 就死了，走不到这一步）

**修复:**
- **P0 类型对齐**: `schemas/ai.py` → `conversation_id: Optional[int]`
- **P0 前端不再静默**: `api.ts` 新增 `readErrorDetail()`；`streamAiChat` 与 `AiChat.vue` 读 body 前补 `if (!res.ok) throw new ApiError(...)`
- **P1 历史合法性**: `get_messages_for_context` 重写 —— 只回放合法序列（丢弃孤儿 `tool` 行、丢弃未被应答的 assistant `tool_calls`、截断窗口不从一轮中间开始）；排序补 `id` 并列项；`get_conversation` 同修
- **P1 写入侧**: 5 处 keyword/mock 路径不再持久化合成的 `tool` 行（Round 0 检索产物是内部中间态，不是真实 tool call）
- **P1 DSML**: 新增 `_parse_dsml_tool_calls()` 把纯文本形态的工具调用还原为标准 `tool_calls`（兼容全角/半角竖线、多 invoke、参数内 JSON）；chat LLM 补 `tools=TOOL_DEFINITIONS`；还原失败时不再把原始标记当正文输出

**测试:**
- backend pytest: **372 passed** (1 skipped)，+9（会话 ID int 回归 1 + 历史序列合法性 4 + DSML 还原 4）
- frontend vitest: **62 passed**，+1（`streamAiChat` 遇 422 抛 `ApiError`）
- vue-tsc: 0 errors
- 端到端 3 轮实测（真实 DeepSeek key）：第 2/3 轮均正确引用前文、未降级 mock、无标记泄露

**变更统计:** 6 文件, +298/-35

## 历史变更 (2026-08-02, R28)

### R28: 生产文件丢失事故 — 根因修复 + 全量恢复 + 生产部署 (2026-08-02)

**事故**: 生产环境 25 条 product_files 中 21 条引用的文件在磁盘上不存在（全部为 2026-06-04~06-07 上传），另有 9 张 product_images 副图缺失。

**根因**: `POST /agent/cleanup-uploads` 会删除 uploads 目录中所有超过 7 天的文件（本意是清理 Agent 临时上传），导致产品文档/图片被误删。本地开发库的 48 个破损主图同因。

**修复** (commit 43ea6a8): cleanup 只删除"未被任何 DB 记录引用"的旧文件（products.image_url / product_images.url / product_files.file_url 三重引用保护），并新增 TDD 测试 `test_cleanup_keeps_db_referenced_files`。

**生产部署 (R27 + 修复)**:
- 生产已更新至 5c1e7d1 (R27 安全修复) + 43ea6a8 (cleanup 修复)，服务重启验证 health OK
- 生产 DB stamp 到 head + 应用幂等迁移 `c3d4e5f6a7b8`（补 login_logs 索引），schema 与 models 完全一致
- 修正生产 `.env` 的 `DATABASE_PATH`（原为本地 Mac 路径）
- 前端 dist 重新构建部署

**数据恢复**:
- 生产库同步到本地：SQLite WAL 模式必须用 `VACUUM INTO`/`.backup` 快照，直接 cp 会丢 WAL 数据
- 从本机 OneDrive `供应商/` 目录按字节级核对找回 16 个产品文件（欧创 6 + 智绘源 4 + 微光 4 + 迭代 1 + 商米 1），另 4 个（iBreaker/PMC-340/R720F×2）来自本机 Downloads
- 欧创 4 个原本无文件的产品补挂规格书（CG52LD/DP35LW/DS10LW/CC51LR）
- 用户补传 10 张图片（替换 9 条坏记录）
- test.txt 测试残留记录已删除

**当前状态**: 生产与本地一致 — product_files 28 条 0 缺失、product_images 73 条引用 0 缺失、alembic 均到 head。

**遗留风险**: ~~生产尚无自动备份（无 cron/定时器）~~ → **2026-09 已落地**：`deploy/systemd/product-db-backup.{service,timer}`（用户级，每日 03:30，保留 14 份），实测 2026-09-17 03:30:57 成功运行。uploads 的镜像仍是手动命令。

## 历史变更 (2026-08-02, R27)

### R27: 全面评测修复 — 安全边界 + 迁移 + 工程卫生 (2026-08-02)

基于全量评测（代码审查 + 测试实跑 + 真实启动验证）修复的问题：

**严重修复:**
- **DB 迁移漂移**: 实跑 `alembic upgrade head` 会触发 `fix_explicit_ddl` 删表重建（数据灾难），且该迁移本身缺 `product_files` 表。改为 stamp 到 head + 新增 `c3d4e5f6a7b8_sync_schema_to_models.py` 只补缺失列（product_files.is_link/link_url + login_logs 索引）。当前 models 与 DB schema 完全一致
- **成本价泄露**: `GET /quotations/{id}`、`/quotations/{id}/items`、`/quotations/{id}/bom` 对非 admin 剥离 product_snapshot.cost_price（响应层过滤，不再写入时剥离，admin 仍可见）
- **AI 工具越权**: `ai_tools.create_quotation` 增加用户上下文（user_id）、`check_ownership(strict=True)`、`created_by`、`quote_number`；`run_agent`/`run_mock_agent` 透传 user_id
- **所有权缺口**: 产品依赖 CRUD 补 `check_ownership(strict=True)`；`/products/export`、`/products/compare` 补 `filter_by_ownership`
- **SSRF DNS 重绑定**: `validate_url` 增加解析后 IP 校验（堵住 `*.nip.io`/数值 IP 绕过），`upload_from_url` 改为流式下载并限制大小
- **上传内存风险**: 新增 `storage.read_limited()` 流式限读，upload-image / ai-fetch-file / product-files / agent-upload 全部接入
- **LIKE 转义**: `escape_like` 增加反斜杠转义；ai_tools `_search_kw` 与 agent `_execute_tool` 补齐 `escape=LIKE_ESCAPE`（全仓 0 处遗漏）

**中等修复:**
- `/auth/profile` 密码修改补 8 位最小长度校验（与注册/重置一致）
- 审批任务绑定 user_id，非本人/admin 不能审批；`asyncio.Event` → `threading.Event`（修复 Python 3.9 下 2 个测试失败）
- 登录限流与登录日志改用 X-Forwarded-For 首跳 IP（反代场景正确）〔**已被 R30 推翻**：无条件信任首跳可被客户端伪造 XFF 绕过限流，现改为仅信任可信代理〕
- 编辑 AI prompt 不再清空全部 AI 对话历史
- `streamAiChat` 会话 ID 解析修复（方案页内嵌 AI 多轮对话不再断链）
- 过时 E2E 更新（LLM 配置卡片断言改为 Base URL 字段）
- 破损图片清理：48 个 product.image_url + 58 条 product_images 引用本地已丢失文件 → 清空/删除（备份 `product_db.db.bak.*_brokenimg`）
- 未登录不再请求 `/ai/stats`（消除 401 噪音）

**清理:**
- 删除死代码 `_cached_dict_query`、`DownloadTicket` 模型（无表无引用）、main.py 过时注释与未用导入
- README/系统功能说明 测试数量更新（341/60/96 — 历史值，当前为 440/69/96）

## 历史变更 (2026-07-23, R26)

### R26: 全面迭代 — 导出模板改进、成本列、Agent Token 统计、拖拽排序、安全加固

**导出模板改进:**
- 按钮改名: 「导出 xlsx」→「导出表格」(2 文件)
- 所有导出表格「备注」列右侧增加「成本」列 (Excel 列 M)
- 成本列纯数值无样式，M 列独立于 A-L 样式网格，可安全删除
- 导出信息行: 删除「公司」→ 改为 `客户 / 项目 / 日期`
- 导出页脚: 「产品数据库」→ 用户名

**Agent Token 统计:**
- Agent SSE 流拦截 Hermes 返回的 usage，写入 `ai_usage_logs` (operation="agent_chat")
- Admin 面板 AI 统计自动纳入 agent 用量
- `_call_hermes`: `aiter_bytes()` → `aiter_lines()` 文本行流

**方案产品清单增强:**
- 拖拽排序: HTML5 drag-and-drop，拖拽行半透明 + 目标蓝色顶线
- `PUT /solutions/{id}/items/reorder` — 批量更新 sort_order
- 单价格式化: `¥1,234` + `—` 备选 (null 安全)
- 方案项 `unit_price` 不再强制 0 — `base_price` 为 0/None 时留空
- 生成报价单按方案排序正确复制 (`order_by sort_order`)

**部署文档:**
- `DEPLOY.md` — 完整部署架构/命令/位置/Nginx/systemd 配置

**安全修复 (CRITICAL):**
- C1: LIKE 注入防护 — 26 处 `ilike()` 加 `escape=LIKE_ESCAPE` (8 文件)
- C3: 产品成本导出 — 非 admin 隐藏 M 列成本值
- C4: 报价单快照 — 创建时 strip `cost_price`，导出时检查 field_visibility

**测试:** backend pytest 298/298 / frontend vue-tsc 0 / vitest 60/60 / E2E 94/96 (2 预存失败)

**变更统计:** 17 commits, 14 files, +380/-70

## 历史变更 (2026-07-23, R25)

### R25: 移除产品列表导出按钮

- 产品列表页「导出」按钮功能失效，暂移除

## 历史变更 (2026-07-16, R24)

### R24: 产品文件链接功能

**新功能:**
- 产品文件卡片支持添加 URL 链接，与文件混合展示
- POST `/products/{id}/links` — 创建链接（JSON: `{label, link_url}`）
- PATCH `/products/files/{id}` — 编辑文件/链接的 label，链接可更新 link_url
- 前端「添加链接」按钮 + 对话框，链接标题点击新标签跳转
- 链接操作：打开 + 编辑 + 删除

**模型变更:**
- `ProductFile` 加 `is_link` (Boolean) + `link_url` (String 500) 列
- `to_dict()` 返回新字段

**修复:**
- `7db0c6d785b3_initial_schema.py` `import *` inside function → 修复 Python 3.9 兼容
- `add_login_log_indexes.py` `down_revision` typo 修正

**测试:** backend pytest 339/341 / frontend vue-tsc 0 / vitest 60/60

## 历史变更 (2026-07-07, R23)

### R23: 安全加固 + 代码质量 + Bug 修复

**安全加固 (P0):**
- Raw SQL → ORM: `products.py` 2 处 `text()` JOIN 查询替换为 SQLAlchemy Core `select()` + `.join()`，消除 SQL 注入面
- 全局速率限制: 新增 `slowapi` 中间件，200 req/day + 60 req/min per IP
- DEV_MODE 生产防护: 检测 systemd `INVOCATION_ID`，`DEV_MODE=true` 下拒绝启动，需 `FORCE_DEV_MODE=true` 覆盖

**前端清理 (P0):**
- `package.json`: 删除 `react`/`react-dom` 依赖（Vue 项目残留）

**代码质量 (P1):**
- `ai.py` `run_agent()`: 提取 `_build_db_context()` + `_score_and_dedup_products()`，429→336 lines (-22%)
- `agent.py` `_execute_tool()`: `get_product_detail` batch 查询 DictCommMethod（消除 N+1）+ eager load manufacturer/category
- `admin_routes.py` `test_llm_config`: 同步 `requests` → `httpx`（全项目统一 HTTP 库）
- `main.py`: `import mimetypes` 移至文件顶部

**Bug 修复:**
- `ai_tools.py:313`: `create_quotation` 工具删除 `project_name=sol.project_name` 传参（`Quotation` 模型无此列，调必抛 `TypeError`）

**测试:** backend pytest 129/129 / frontend vue-tsc 0 errors, vitest 60/60

**变更统计:** 9 files, +159/-111

## 历史变更 (2026-07-07, R22)

### R22: 用户隔离 — Agent 历史 + 登录日志地区

**Agent 会话历史用户隔离:**
- `AgentView.vue`: localStorage 前缀 `agent_` → `agent_{userId}_`，不同用户独立存储
- `inject('currentUser')` 获取当前用户 ID
- 新增 E2E 测试 `e2e/agent-isolation.spec.ts` (2 tests)

**登录日志地区补全:**
- `auth_routes.py`: 失败登录 + 注册 补 `_lookup_ip_region(ip)`
- 之前仅登录成功调用，失败/注册 → region=NULL → 前端显示"—"
- 新增 E2E 测试 (admin 登录日志 2 tests +)

**产品搜索增强 — 厂商名:**
- `products.py`: 搜索 OR 条件新增厂商名 JOIN
- 搜索"智嵌"（厂商名）从 1 条 → 6 条（之前仅 description 含"智嵌"的 1 条能匹配）
- 搜索覆盖: name / model / sku / description / pinyin / 品类名 / **厂商名**（新增）

**AI 助手用户隔离审计:**
- AiChat.vue: 后端 `AIConversation` 表 `filter_by(user_id=user.id)` ✅
- SolutionDetailView.vue: 同后端 ✅
- AgentView.vue: localStorage `agent_{userId}_` ✅ 已修复
- Agent 后端: 无状态代理 ✅
- 后端 3 端点 (`GET/DELETE /ai/conversations`) 全部校验所有权

**.gitignore:** 添加 `frontend/test-results/`, `backend/test-results/`, `frontend/playwright-report/`

**测试:** backend pytest 129/129 / frontend vue-tsc 0 errors, vitest 60/60 / E2E: 96 tests (2 agent + 2 login-log + 2 error-scenarios + 75 full-regression + 19 API + 4 perf), 1 pre-existing failure (LLM config — R20 API key input removed)
（括号内相加为 104 ≠ 96，是当时的记录笔误；当前各文件实测分布见 R34：full-regression 53 / error-scenarios 17 / api-health 19 / perf 4 / agent-isolation 2 / core-flows 1 = 96）

## 历史变更 (2026-07-07, R21.1)

### R21.1: 测试覆盖率大幅提升 + Bug 发现 (2026-07-07)

**测试覆盖率提升 (+212 tests, +17%):**

后端从 129 tests / 62% 覆盖率提升至 341 tests / 79% 覆盖率。

新增 5 个测试文件:
- `test_auth_extended.py` (29 tests): SHA256→bcrypt 自动升级、JWT 过期/篡改/不存在用户、query token 仅限 GET、登录速率限制、密码修改、注册流程、权限隔离
- `test_supplement.py` (56 tests): 产品边界(必填校验/特殊字符/分页/view_count)、存储服务(文件保存/删除/魔数校验/大小限制)、AI 工具执行(16 tests)、安全测试(SQL注入/XSS/路径遍历)、方案总价重算、报价单 BOM 编辑器、批量删除
- `test_round2.py` (49 tests): 字典 CRUD 全覆盖(48%→95%)、规格生成器(51%→90%)、产品 helper(63%→76%)、Excel 样式(63%→79%)、产品导入、报价单导出边界
- `test_round3.py` (43 tests): LLM 引擎 mock(54%→94%)、审批管理器(73%→100%)、AI 提取(38%→75%)、存储 upload_from_url(60%→91%)、Agent 工具执行、AI 聊天 LLM mock
- `test_round4.py` (35 tests): AI 对话 CRUD、build_context、run_agent LLM mock(关键词匹配/多方案/工具调用/品牌过滤/价格排序/DSML)、Agent 文件上传、BOM 快照同步/导出、产品 AI 抓取 URL 重定向

**覆盖率 >90% 的模块:**
- approval_manager.py 100%, schemas/* 100%, utils/escape.py 100%
- ai_engine.py 94%, dictionaries.py 95%, categories.py 95%
- solutions.py 93%, storage.py 91%, spec_generator.py 90%

**发现的 Bug (2 个):**
1. `ai_tools.py:312` — `create_quotation` 工具传递 `project_name` 给 `Quotation()` 构造函数，但 Quotation 模型没有该字段，导致 TypeError。测试中记录为已知问题。
2. `excel_style.py:274` — `num_to_chinese_uppercase()` 对 ≥1 亿的数字处理错误。`pos % 8` 导致第 9 位(亿)映射到 index 0，`100000000` 返回"壹万圆整"而非"壹亿圆整"。`_CN_RADICES` 只有 9 个元素但代码用 `pos % 8`。

**测试结果:**
- Backend pytest: **341/341 pass** (1 skipped, 4.5min)
- Frontend vitest: 60/60 pass (unchanged)
- Coverage: **79%** (from 62%)

**变更统计:** 5 文件新增

## 历史变更 (2026-07-06, R21)

### R21: 时区显示修复 + 端口统一 + 环境配置完善

**时区显示修复:**
- 新增 `frontend/src/utils/time.ts` — `formatTime()` 统一将 UTC 时间转本地时区显示
- 10 处 raw `created_at`/`updated_at` → `formatTime()`
- SQLite 存 UTC 但返回 naive datetime（无时区戳），JS 按本地时区解析 → 显示晚 8 小时
- 修复：`formatTime` 检测 naive ISO 自动追加 `Z` 后缀，强制 UTC 解释
- AgentView 删除本地 `formatTime`，统一用共享版

**端口统一 (8002→8000):**
- 生产 systemd + Nginx 端口改为 8000，与开发环境一致
- 本文档同步更新

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

## 历史变更 (2026-07-01, R19.1)

### R19.1: 页脚增加公安备案号 (2026-07-01)

- footer 增加公安备案号: 陕公网安备61019002004032号（`App.vue` 新增链接，`main.css` 调整样式）
- footer 改为 flexbox 布局，双链接并排显示，`gap: 12px`

**变更统计:** 2 文件, +5

## 历史变更 (2026-06-27, R19)

### R19: 测试覆盖率提升 + 生产环境 E2E 验证 (2026-06-27)

**测试覆盖率提升 (+84 测试, +43%):**

后端新增 45 测试 (`test_agent_admin_files.py`):
- Agent 端点: config, prompt, cleanup-uploads, upload, approval, approvals, test-approval, chat (8 tests)
- Admin 端点: users CRUD, login-logs, fields, ai-settings, llm-config, llm-models, ai-usage, download-logs (28 tests)
- Product Files: list, upload, download, delete (7 tests)
- 权限测试: 非 admin 访问 admin 端点返回 403 (2 tests)

前端新增 22 测试 (`views.test.ts`):
- LoginView: 表单渲染、输入框、登录按钮 (4 tests)
- ProductsView: 列表头部、搜索框、筛选器 (5 tests)
- SolutionsView: 表格头部 (4 tests)
- QuotationsView: 表格头部 (4 tests)
- AdminView: 面板头部、API 调用 (3 tests)
- NotFoundView: 404 消息、返回链接 (2 tests)

E2E 新增 17 测试 (`error-scenarios.spec.ts`):
- Auth 错误: 无 token 重定向、无效 token、过期 token (5 tests)
- 404 处理: 不存在页面、返回链接 (2 tests)
- 表单验证: 空用户名、错误密码、缺少必填字段 (3 tests)
- API 错误恢复: 网络错误、500 错误 (2 tests)
- 边界情况: 空搜索、快速点击、长文本、无 token API (5 tests)

**生产环境 E2E 验证:**
- 新增 `playwright.prod.config.ts` — 远程服务器测试配置（无 webServer）
- product-db.cn 全量 92 测试通过（core-flows + full-regression + api-health + error-scenarios + perf-check）
- 性能指标: 产品列表 507ms, SPA 导航 71ms, API 响应 ~5ms

**测试结果:**
- Backend pytest: **129/129 pass** (34.7s)
- Frontend vitest: **60/60 pass** (1.8s)
- vue-tsc: 0 errors
- Playwright E2E (本地): **92/92 pass** (2.5min)
- Playwright E2E (生产): **92/92 pass** (3.5min)

**变更统计:** 6 文件新增

## 历史变更 (2026-06-26, R18)

### R18: 安全加固 — 权限收敛 + 漏洞修复 + 代码质量 (2026-06-26)

**权限收敛:**
- products.py PUT/DELETE: `check_ownership(strict=True)` — 普通用户只能改/删自己产品
- `check_ownership` strict 模式修复: NULL 旧数据拒绝写入，admin 判断改用 `_get_admin_ids()`

**安全加固 (5 严重 → 0):**
- S1: DEV_MODE 启动横幅 + auto-admin 日志警告
- S2: JWT `?token=` 限制仅 GET 请求
- S5: SHA256 遗留哈希加 warning log（自动升级已在 auth_routes）
- S7: BOM 模板删除补 `check_ownership(strict=True)`
- S9: product_files 4 端点所有权检查（读→view, 写→strict）
- S10: `/settings` + `/settings/{key}` 加 admin 检查
- N2: cleanup-uploads 加 admin 检查
- N6: BOM snapshot 4 端点加方案所有权检查
- agent.py:297 LIKE 注入: keyword + manufacturer_name 加 `escape_like()`

**代码质量:**
- M1: 10 model 文件 + 6 router 文件 `datetime.now()` → `datetime.now(timezone.utc)`
- D1: python-jose → PyJWT 2.13, 移除 ecdsa/rsa/pyasn1 依赖
- B1: 17 个 POST 创建端点 → `status_code=201`
- B3: AI/Agent 3 端点 raw dict → Pydantic schema (`schemas/ai.py`)
- F6: api.ts 23 处 `data: any` → `Record<string, unknown>`, 返回类型修正
- F8: flattenTree 集中到 markdown.ts
- M2: 8 张表 `created_by` 列加 `index=True`

**前端:**
- F10: AiChat.vue 删除 48 行死代码 `mdToHtml`
- F15: 404 路由 + NotFoundView.vue
- F17: SolutionDetailView 流式渲染 50ms 节流（减少 ~90% 重渲染）
- 登录页: 注册字段填写说明 + 注册关闭时隐藏链接

**测试:** backend pytest 84/84, frontend vue-tsc 0 errors

**评级:** B+ → **A-**

**变更统计:** 36 文件, +317/-244

## 历史变更 (2026-06-19, R17.1)

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

## 历史变更 (2026-06-18, R17)

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

- Agent system prompt 从硬编码改为管理页 AI 设置可编辑（DB 存储）
- 新增 `GET /agent/config`、`GET /agent/prompt` 端点，返回 `db_path` / `api_base` / `prompt`
- `config.py` 新增 `AGENT_API_BASE` / `DATABASE_PATH` 配置项
- `AgentView` 头像静态化 + `▊` 高频闪烁光标（SSE 完成后消失）
- 页脚加陕ICP备2026015306号
- 修复 pdb 前端部署路径（`frontend/dist`）+ Hermes `execute_code` allowlist

**变更统计:** 10 文件, +152/-83

## 历史变更 (2026-06-16, R15)

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

## 历史变更 (2026-06-08, R12.2)

### R12.2: 提示词 DB 化 + URL 按钮修复

- 提示词 DB 化: `build_extraction_prompt` 从 `ai_extract_prompt` 读取, 管理页可编辑+重置
- 产品 URL 按钮: 裸 `www.` 域名自动识别, async/await 提取, 自动 `https://` 前缀
- 管理页优化: 提示词加重置按钮 + 分割线
- 新建产品页: 依赖关系卡片可见, 保存后跳转编辑页
- AI 卡片拖拽区文字改为"粘贴图片、拖拽文件到此处 或"

## 历史变更 (2026-06-07, R12.1)

### R12.1: AI按钮恢复, 依赖卡片/自动滚动/URL提取联动

- 恢复产品 Header AI 智能录入按钮 + 产品 URL 右侧 AI 识别按钮
- `AiExtractCard` 暴露 `fetchFromUrl()` — URL 联动填入 + 自动提取
- AI 提取完成自动滚动到预览区
- 新建产品页显示依赖卡片（提示先保存），保存后跳转编辑页
- 修复 `v-else` 孤儿（SolutionsView / QuotationsView / AdminView）
- `ai-drop` CSS 移至 main.css 全局

**变更统计:** 前端 3 文件（`AiExtractCard.vue` / `DependencyEditor.vue` / `ProductFormView.vue`）

## 历史变更 (2026-06-07, R12)

### R12: 全面优化 — 性能/架构/CSS/LLM/OCR/组件/安全

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
- AGENTS.md R12 变更日志 + 文档索引
- 系统功能说明.md 数据统计 + 组件列表更新
- docs/architecture.md + docs/database.md 已补充最新架构

## 历史变更 (2026-06-06, R11)

### R11: 代码审计修复 + 架构/数据库文档 (2026-06-06)

**安全修复:**
- 11 处 PUT/DELETE 端点补全 `check_ownership()`（字典 8 + 供应商 2 + delete_manufacturer）
- 所有 `except: pass` 改为至少 log 警告（ai_extract / ai / auth_routes / product_files）
- `upload_image` 加 `file.size` 预检防大文件 OOM
- `uploadProductImage` 加 `resp.ok` 检查

**类型安全:**
- 8 个 Dict CRUD 端点 `data: dict` → Pydantic Schema（Create/Update × 4 类型）
- 新增 CommMethod / Protocol / PowerSupply / SensorMetric 的 Create/Update schemas

**错误处理:**
- `onAiFetch` 加 HTTP 状态码检查 + finally；`onAiFill` 加 try-catch
- 4 个 dict load 函数加 try-catch；`deleteSup` 加错误处理，`loadCategories` 加空对象回退

**数据一致性:**
- regex fallback spec key 英→中（`ip_rating` → 防护等级 等）
- `quotation_items.product_id` 改 nullable（BOM 手动行用 NULL 代替哨兵 0）
- 导出改用 `product_categories` 多对多筛选（与列表查询逻辑对齐）

**代码整洁:**
- products / ai / quotation 模块级 `import logging`；移除未用 `literal_column`；suppliers 重复 import 修复
- `DictItem` 接口补 `accuracy` / `resolution`；`_log_ai_usage` 加 try/finally 防连接泄漏

**文档:**
- 新增 `docs/architecture.md`（架构总览）+ `docs/database.md`（数据库设计）
- 系统功能说明.md 更新数据统计 + 文档索引

**验证:** pytest 78/78, vitest 38/38, vue-tsc 0 errors, smoke 11/11

**变更统计:** 19 文件, +994/-120

## 历史变更 (2026-06-05, R9-R10)

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

## 历史变更 (2026-06-05, R7-R8)

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
| Database | SQLite（dev 与 prod 都是；生产库 `/opt/product-db/backend/product_db.db` 为唯一权威源） |
| Frontend | Vue 3 + TypeScript + Vite + CSS Variables |
| Icons | Lucide Icons (lucide-vue-next) |
| AI | DeepSeek API (LlmEngine async) + Tool Calling + SSE |
| Auth | JWT (python-jose) + bcrypt (passlib) + 登录频率限制 |
| XSS | DOMPurify (所有 v-html 已清洗) |
| SSRF | validate_url() + 手动重定向验证 |
| Logging | loguru (structured + rotation) |
| Testing | pytest 440 collected（439 passed + 1 skipped）+ vitest 69 tests + Playwright 96 tests |
| Deployment | systemd + nginx + rsync（`deploy/` 下备份/探针/就绪门控脚本；`docker-compose.yml` 是早期实验、**非生产路径**） |

## 开发命令

```bash
# 后端
cd backend && source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pytest tests/ -v

# 前端
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173    # 本地 vite (^6.3)，不用 npx vite（可能拿全局 v8）
npx vitest run
npx vue-tsc --noEmit

# E2E 测试
npx playwright test e2e/full-regression.spec.ts --reporter=list   # 全功能 (53 tests)
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
├── models/              # 32 张业务表 (product_categories 多对多)
│   ├── product.py, category.py       # 核心 (产品支持多品类)
│   ├── dictionary.py, mapping.py     # 字典+映射
│   ├── solution.py, quotation.py     # 方案+报价
│   ├── dependency.py, bom_template.py
│   ├── supplier.py, user.py
│   ├── ai_models.py, ai_usage_log.py # AI
│   ├── login_log.py, system_setting.py, field_setting.py
│   └── download_log.py               # 下载审计
├── routers/             # 14 个路由模块
│   ├── products.py, product_import.py, product_files.py
│   ├── categories.py, suppliers.py
│   ├── solutions.py, quotations.py, bom_templates.py
│   ├── ai.py, agent.py, auth_routes.py, admin_routes.py
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
└── tests/               # pytest 440 collected（439 passed + 1 skipped）

frontend/src/
├── App.vue              # 主布局 (暗侧边栏 + 全局搜索 + toast + 用户菜单)
├── api.ts               # 集中式 API 客户端 + SSE streamAiChat
├── router.ts            # 18 条 path（16 条组件路由 + 2 条 redirect；含 JWT 过期检测与 admin 守卫）
├── types.ts             # TypeScript 类型定义 (Product, Category, Solution...)
├── utils/
│   └── markdown.ts      # 共享 HTML/markdown 格式化工具
├── views/               # 16 个页面视图
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
└── __tests__/           # vitest 62 tests
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
- SQLite 32 张业务表, ~6,000 行, 单文件运行
- 图片: 90% 远程 URL, 10% 本地 `app/uploads/`
- `product_category_helper.py` 消除 5 处 raw SQL, 统一 ORM 参数化查询

## 关键约定

- 模型统一 `to_dict()` 方法，Product 支持 map 参数防 N+1
- 通用 partial update: `apply_partial_update(obj, data, fields)`
- **权限**: `filter_by_ownership()` 过滤列表, `check_ownership()` 校验单资源 (admin 看全部, 普通用户看 NULL/自己/admin)
- **created_by**: 8 表 (products, categories, manufacturers, suppliers, 4 dict) 创建时自动设为 `user.id`
- DEV_MODE=True 时免登录 (自动创建 admin/admin)，生产必须 False
- **环境拓扑**: 代码单向流动 `本机(唯一改动源) → GitHub → 生产服务器`；**数据库方向相反，以服务器为准** —— 禁止用本地 `backend/product_db.db` 覆盖生产库，两库数据本就不同（详见 DEPLOY.md「环境拓扑」「数据库归属」）
- 生产服务器是纯部署目标，其本地改动一律丢弃（`git stash && git stash drop` 是有意为之）；但**绝不执行 `git clean -fd`**（会删掉未跟踪的 `static/index.html`，2026-08 首页 404 的成因）
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
