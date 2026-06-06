# 数据库设计

SQLite 单文件, 33 张表, ~7,000 行数据。

## 表总览

```
products ───────────── 产品核心 (392 rows)
  ├── 多对多关联 (7 张中间表)
  │   ├── product_categories          (724)
  │   ├── product_comm_methods        (511)
  │   ├── product_comm_protocols      (223)
  │   ├── product_power_supplies      (413)
  │   ├── product_sensor_capabilities (446)
  │   ├── product_hardware_interfaces (265)
  │   └── product_dependencies        (128)
  ├── product_files   (20)
  └── product_images  (176)

字典 (4 张)
  ├── dict_comm_methods     (18)  通讯方式
  ├── dict_comm_protocols   (17)  协议
  ├── dict_power_supplies   (11)  供电
  └── dict_sensor_metrics   (36)  传感器指标

组织 (2 张)
  ├── manufacturers  (48)  厂商
  └── suppliers      (55)  供应商

品类 (1 张)
  └── device_categories (50)  树形品类
      └── category_spec_definitions  品类规格定义

业务 (4 张)
  ├── solutions          (10)  方案
  ├── solution_items     (16)  方案行项目
  ├── quotations         (7)   报价单
  └── quotation_items    (19)  报价单行项目

BOM (2 张)
  ├── solution_bom_snapshots  (2)   BOM 快照
  └── bom_templates           (1)   BOM 模板

AI (3 张)
  ├── ai_conversations  (88)   对话
  ├── ai_messages       (983)  消息
  └── ai_usage_logs     (270)  Token 统计

系统 (6 张)
  ├── users             (3)    用户
  ├── login_logs        (251)  登录审计
  ├── download_logs     (16)   下载审计
  ├── system_settings   (7)    KV 配置
  ├── field_settings    (4)    字段可见性
  └── alembic_version          迁移版本
```

## 核心 ER

```
users (id, username, role, is_active)
  │
  │ created_by (8 张表 FK)
  │
  ├── manufacturers (id, name, sort_order)
  ├── suppliers (id, name, contact, phone)
  ├── device_categories (id, parent_id, name, slug, level)
  │
  └── products (23 列)
       ├── category_id (遗留单列)
       ├── manufacturer_id → manufacturers
       ├── supplier_id → suppliers
       ├── specs (JSON), urls (JSON), custom_fields (JSON)
       ├── parent_id (自引用: 变体)
       │
       ├── product_categories (多对多)
       ├── product_comm_methods (多对多 + details)
       ├── product_comm_protocols (多对多 + direction)
       ├── product_power_supplies (多对多 + voltage_range)
       ├── product_sensor_capabilities (多对多 + accuracy)
       ├── product_hardware_interfaces
       ├── product_dependencies (自引用 + 品类引用)
       │
       ├── product_files (1:N)
       └── product_images (1:N)

业务流:
  solutions → solution_items → products
    └── solution_bom_snapshots

  quotations → quotation_items → products
    └── quotation_items.product_snapshot (JSON 快照)
```

## 核心表详解

### products (392 rows)

```
列              类型           说明
────────────────────────────────────────────
id              INTEGER PK
model           VARCHAR(100)   型号 (NOT NULL)
name            VARCHAR(200)   产品名 (NOT NULL)
sku             VARCHAR(100)   始终 = model
category_id     INTEGER FK     遗留单列, 逐步废弃
manufacturer_id INTEGER FK     → manufacturers
supplier_id     INTEGER FK     → suppliers
unit            VARCHAR(20)    单位
base_price      NUMERIC        销售价
cost_price      NUMERIC        成本价 (非admin隐藏)
description     TEXT           功能描述 (客户可见)
image_url       VARCHAR(500)   图片
product_url     VARCHAR(500)   产品链接
status          VARCHAR(20)    active|discontinued|planned
parent_id       INTEGER       变体父产品 (自引用)
specs           TEXT (JSON)    规格 {"防护等级":"IP67",...}
urls            TEXT (JSON)    附加链接
custom_fields   TEXT (JSON)    自定义字段
pinyin_search   TEXT           预计算拼音
view_count      INTEGER       查看次数
created_by      INTEGER FK    → users
created_at      DATETIME
updated_at      DATETIME

索引: name, model, sku, category_id, status, parent_id
```

### device_categories (50 rows, 树形)

```
列          类型           说明
────────────────────────────────────
id          INTEGER PK
parent_id   INTEGER       父品类 (NULL=根)
name        VARCHAR(100)  品类名
slug        VARCHAR(100)  URL 标识 (UNIQUE)
level       INTEGER       层级 (0=根)
sort_order  INTEGER       排序
is_active   BOOLEAN       启用
created_by  INTEGER FK    → users

树形示例:
  传感器 (level=0)
    ├── 温度 (level=1)
    ├── 湿度 (level=1)
    ├── 光照 (level=1)
    └── 占用传感器 (level=1)
  网关 (level=0)
    ├── LoRaWAN网关 (level=1)
    └── 边缘网关 (level=1)
```

### 多对多关联 (7 张中间表)

```
product_comm_methods (复合 PK: product_id + method_id)
  details VARCHAR(255)  ← "RJ45×2, 10/100Mbps"

product_comm_protocols (复合 PK: product_id + protocol_id)
  direction VARCHAR(20)  ← "both" | "up" | "down"

product_power_supplies (复合 PK: product_id + power_id)
  voltage_range VARCHAR(100)  ← "9-24V DC"
  battery_life VARCHAR(100)   ← "5年"

product_sensor_capabilities (复合 PK: product_id + metric_id)
  measure_range VARCHAR(100)  ← "-30~70"
  accuracy VARCHAR(100)       ← "±0.2"
  resolution VARCHAR(50)      ← "0.1"

product_categories (复合 PK: product_id + category_id)
  纯 FK, 无额外列

product_hardware_interfaces (独立 ID)
  interface_name VARCHAR(50)
  quantity INTEGER, description VARCHAR(255)

product_dependencies
  product_id FK             → 谁依赖
  depends_on_product_id FK  → 依赖哪个产品
  depends_on_category_id FK → 或依赖某品类
  dependency_type VARCHAR   → required | optional
```

### 字典表

```
dict_comm_methods (18 rows)
  method_type VARCHAR(20)  wired|wireless
  name VARCHAR(50)         WiFi/Ethernet/LoRaWAN/4G/5G...
  description TEXT
  [created_by]

dict_comm_protocols (17 rows)
  name VARCHAR(50)         MQTT/HTTP/ModbusRTU/BACnet...
  description TEXT
  [created_by]

dict_power_supplies (11 rows)
  supply_category VARCHAR(50)  DC/PoE/Battery/AC
  name VARCHAR(50)             5V DC/12V DC/24V DC...
  description TEXT
  [created_by]

dict_sensor_metrics (36 rows)
  name VARCHAR(50)         温度/湿度/CO2/PM2.5/光照...
  unit VARCHAR(20)         ℃/%RH/ppm/lux...
  accuracy TEXT            ±0.3°C (典型)
  resolution TEXT          0.1°C
  description TEXT
  [created_by]
```

### AI 表

```
ai_conversations (88)
  user_id FK, title VARCHAR(200)
  created_at, updated_at

ai_messages (983)
  conversation_id FK (INDEX)
  role VARCHAR(20)       user|assistant|system|tool
  content TEXT
  tool_calls TEXT(JSON)  AI 发起的工具调用
  tool_call_id VARCHAR  工具结果关联
  created_at

  上下文: 每次请求取最近 20 条

ai_usage_logs (270)
  user_id FK (INDEX)
  operation VARCHAR(50) chat|ai_fetch|ai_fetch_text
  model VARCHAR(50)
  tokens_in, tokens_out INTEGER
  duration_ms FLOAT
  success, error
  created_at
```

### 业务表

```
solutions (10)
  name, description, client_name, project_name
  status, total_cost, total_price, notes
  [created_by], created_at, updated_at

solution_items (16)
  solution_id FK (INDEX), product_id FK
  quantity, unit_price, discount_rate, remark, sort_order

quotations (7)
  solution_id FK (INDEX), quote_number, title
  client_name, client_contact, valid_days, tax_rate
  status, total_amount, notes, download_count
  [created_by], created_at, updated_at

quotation_items (19)
  quotation_id FK (INDEX)
  product_id FK (nullable — BOM 手动行可用 NULL)
  product_snapshot TEXT(JSON)  ← 产品快照防漂移
  quantity, unit_price, amount
  discount_rate, remark, sort_order
```

## JSON 字段策略

```
products.specs
  {"防护等级": "IP67", "尺寸": "240×164×90.9mm", "重量": "500g"}
  key 统一中文, value 带单位

products.urls
  [{"label": "规格书", "url": "https://..."}, ...]

products.custom_fields
  预留扩展

quotation_items.product_snapshot
  {"name": "...", "sku": "...", "model": "...", "description": "..."}
  目的: 产品后续变更不影响已报价数据

solution_bom_snapshots.snapshot
  {cells: [...], colWidths: [...]}
  BOM 表格完整状态

ai_messages.tool_calls
  [{"id": "call_xxx", "function": {"name": "search_products", "arguments": "..."}}]
```

## 索引

**27 个索引**, 覆盖:

```
查询加速:
  products.name / model / sku / status / category_id
  solution_items.solution_id
  quotation_items.quotation_id
  quotations.solution_id
  ai_messages.conversation_id (2 个)
  ai_conversations.user_id
  product_files.product_id
  product_dependencies.product_id
  download_logs.user_id

唯一约束:
  users.username
  manufacturers.name
  device_categories.slug
  system_settings.key
  field_settings.field_name
```

## 权限数据模型

```
8 张业务表含 created_by:
  products, device_categories, manufacturers, suppliers,
  dict_comm_methods, dict_comm_protocols,
  dict_power_supplies, dict_sensor_metrics

created_by 值语义:
  NULL     → 系统/legacy (所有人可见)
  user.id  → 用户自己创建
  1        → admin 创建 (所有人可见)

filter_by_ownership():
  admin → 看全部
  普通 → NULL OR user.id OR 1

check_ownership():
  admin → 通过
  普通 → item.created_by NOT IN (NULL, user.id, 1) → 403
```

## 设计原则

1. **多对多 > JSON 数组** — 字典引用完整性 + 可反向查询 + 属性级字段
2. **快照 > 实时引用** — 报价单 product_snapshot 防历史数据漂移
3. **遗留兼容** — category_id 单列 + product_categories 多对多 并存过渡
4. **预计算** — pinyin_search 加速中文搜索, view_count 追踪热度
5. **审计优先** — login_logs / download_logs / ai_usage_logs
6. **SQLite 友好** — 单文件零配置, FK 默认 OFF, WAL 模式
