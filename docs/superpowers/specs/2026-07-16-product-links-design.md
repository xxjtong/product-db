# 产品链接功能设计

## 概述

产品详情页「产品文件」卡片增加 URL 链接添加功能，与现有文件混合展示。

## 设计

### 后端

**模型变更** — ProductFile 表加 2 列：

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_link` | Boolean, default False | 区分链接/文件 |
| `link_url` | String(500), nullable | 链接 URL |

**新增 API：**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/products/{product_id}/links` | 创建链接，JSON body: `{label, link_url}` |
| PATCH | `/products/files/{file_id}` | 更新 label（文件/链接通用），链接可额外更新 link_url |

**现有 API 适配：**
- GET `/products/{product_id}/files` — 同时返回文件和链接，混合排序
- DELETE `/products/files/{file_id}` — 链接只删 DB 记录，不删磁盘文件

### 前端

**ProductFiles.vue 改动：**

1. 「上传」按钮旁增加「添加链接」按钮
2. 点击弹出对话框：URL 输入框 + 标题(label)输入框
3. 列表表格适配：
   - 链接行：🔗 图标，标题可点击（target="_blank" 跳转 link_url）
   - 链接行：类型列显示「链接」，大小列显示「-」
   - 文件行：保持现有样式
4. 操作按钮：链接显示 🔗打开 + ✏️编辑 + 🗑️删除
5. 链接和文件按 sort_order 混合排序

## 范围

- 1 个 migration
- 2 个新 API 端点
- 1 个前端组件增强
- 不涉及：链接预览、favicon 抓取、链接有效性检测
