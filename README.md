# 产品数据库

IoT 产品选型对比、规格书生成、方案设计系统。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy 2.0 |
| 数据库 | SQLite（本地）/ PostgreSQL（生产） |
| 前端 | Vue 3 + TypeScript + Vite |
| UI | CSS Variables + Lucide Icons |

## 项目结构

```
product-db/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── database.py          # SQLAlchemy 配置 + JSONBType
│   │   ├── auth.py              # JWT 认证（dev 模式免登录）
│   │   ├── config.py            # 配置（DB、JWT、AI Gateway）
│   │   ├── models/              # 数据模型（13 张表）
│   │   │   ├── product.py       # 产品
│   │   │   ├── category.py      # 品类 + 规格定义
│   │   │   ├── dictionary.py    # 字典表（通讯/协议/供电/传感器）
│   │   │   ├── mapping.py       # 映射表（产品↔字典）
│   │   │   ├── dependency.py    # 产品依赖
│   │   │   ├── solution.py      # 方案 BOM
│   │   │   ├── bom_template.py  # BOM 模板 + 快照
│   │   │   ├── quotation.py     # 报价单
│   │   │   ├── supplier.py      # 供应商
│   │   │   └── user.py          # 用户
│   │   ├── routers/             # API 路由
│   │   │   ├── products.py      # 产品 CRUD + AI 识别 + 规格书 + 对比
│   │   │   ├── categories.py    # 品类 + 规格定义管理
│   │   │   ├── suppliers.py     # 供应商管理
│   │   │   ├── solutions.py     # 方案 BOM + 完整性检查
│   │   │   ├── quotations.py    # 报价单
│   │   │   ├── bom_templates.py # BOM 模板 + 快照 + Excel 导出
│   │   │   ├── dictionaries.py  # 字典表管理
│   │   │   └── ai.py            # AI 产品助理（SSE）
│   │   ├── services/
│   │   │   ├── spec_service.py  # 规格校验 + 产品对比
│   │   │   └── storage.py       # 文件存储
│   │   └── schemas/             # Pydantic schemas
│   ├── init_dicts.py            # 字典数据初始化
│   ├── import_milesight_v2.py   # Milesight 产品导入
│   └── migrate_quote_to_productdb.py  # quote-system 数据迁移
└── frontend/
    ├── src/
    │   ├── App.vue              # 主布局（暗色侧边栏 + 内容区）
    │   ├── api.ts               # API 客户端
    │   ├── router.ts            # 路由（12 个页面）
    │   ├── types.ts             # TypeScript 类型
    │   ├── components/          # 通用组件
    │   │   ├── PageHeader.vue
    │   │   ├── SearchInput.vue
    │   │   ├── Pagination.vue
    │   │   ├── TagBadge.vue
    │   │   ├── Modal.vue
    │   │   └── ConfirmDialog.vue
    │   └── views/               # 页面视图
    │       ├── ProductsView.vue          # 产品列表（筛选 + 对比选择）
    │       ├── ProductDetailView.vue     # 产品详情 + 规格展示
    │       ├── ProductFormView.vue       # 产品表单（动态spec + AI录入）
    │       ├── ProductCompareView.vue    # 产品对比矩阵
    │       ├── CategoriesView.vue        # 品类管理 + 规格定义编辑
    │       ├── DictionariesView.vue      # 字典表管理
    │       ├── SuppliersView.vue         # 供应商管理
    │       ├── SolutionsView.vue         # 方案列表
    │       ├── SolutionDetailView.vue    # 方案详情（BOM + 依赖检查）
    │       ├── QuotationsView.vue        # 报价单列表
    │       └── QuotationDetailView.vue   # 报价单详情 + 导出
    ├── vite.config.ts
    └── package.json
```

## API 概览

| 路由 | 说明 |
|------|------|
| `GET /api/products` | 产品列表（分页 + 筛选 + 搜索） |
| `POST /api/products` | 创建产品 |
| `GET /api/products/{id}` | 产品详情 |
| `PUT /api/products/{id}` | 更新产品 |
| `DELETE /api/products/{id}` | 删除产品 |
| `POST /api/products/ai-fetch` | AI 识别录入（URL/文本 → 产品数据） |
| `GET /api/products/{id}/spec-sheet` | 产品规格书（HTML/PDF） |
| `GET /api/products/compare` | 产品对比矩阵 |
| `GET /api/products/export` | 产品 Excel 导出 |
| `GET /api/categories` | 品类列表 |
| `GET /api/categories/{id}/spec-definitions` | 品类规格定义 |
| `GET /api/suppliers` | 供应商列表 |
| `GET /api/solutions` | 方案列表 |
| `GET /api/solutions/{id}/check` | 方案完整性检查 |
| `GET /api/solutions/{id}/suggest` | 缺失依赖推荐 |
| `GET /api/quotations` | 报价单列表 |
| `POST /api/ai/chat` | AI 产品助理（SSE 流式） |
| `GET /api/dicts/*` | 字典表查询 |

## 本地开发

```bash
# 后端
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd frontend
npm install
npx vite --host 0.0.0.0 --port 5173
```

浏览器访问 `http://localhost:5173`，dev 模式下无需登录。

## 数据模型

产品围绕三个层次组织：

1. **通用维度**（所有产品）：通讯方式、通讯协议、供电方式 → 通过字典表 + 映射表管理
2. **品类特有参数**（如网关的 LoRa 芯片、传感器的检测精度）→ 由 `category_spec_definitions` 定义，存储在 `products.specs` JSONB
3. **硬件接口 / 传感能力** → 独立映射表

```
products ──M2M──> dict_comm_methods
products ──M2M──> dict_comm_protocols
products ──M2M──> dict_power_supplies
products ──1:M──> product_hardware_interfaces
products ──M2M──> dict_sensor_metrics
products ──FK──> device_categories
products ──FK──> manufacturers
products ──FK──> suppliers
products.specs = JSONB (品类特有参数)
```

## 业务流

```
品类管理 → 规格定义 → 产品录入（手动 / AI识别 / Excel导入）
                              │
                  ┌───────────┼───────────┐
                  ▼           ▼           ▼
              产品列表    产品对比    规格书生成
              (动���筛选)  (差异矩阵)  (HTML/PDF)
                  │
                  ▼
            选入方案 BOM → 依赖检查 → 兼容性检查 → 生成报价单
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
            缺失依赖告警            自动推荐补齐产品
```

## License

MIT
