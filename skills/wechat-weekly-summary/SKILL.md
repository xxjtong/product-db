---
name: wechat-weekly-summary
description: "This skill should be used when the user wants to scan WeChat or Feishu/Lark messages for the current or a specified week, and produce a structured summary report. Triggers include phrases like 扫描本周微信消息, 汇总飞书消息, 整理本周聊天记录, 读取本周群聊消息, or any request combining WeChat or Feishu with 本周/这周/消息汇总/聊天记录."
---

# WeChat / Feishu Weekly Message Summary

## Purpose

Automate the process of:
1. Opening WeChat or Feishu on macOS
2. Scanning the chat list to find conversations active this week
3. Reading message content from each conversation via screenshot + OCR
4. Producing a structured Markdown summary report

## Prerequisites

- **macOS only** — uses `screencapture`, `cliclick`, AppleScript, Swift/Vision OCR, and **Quartz CGEvent** (PyObjC)
- **`cliclick`** must be installed: `brew install cliclick`
- **Quartz (PyObjC)** — available by default on macOS Python, no installation needed
- **No Accessibility permissions required** — v9.4+ uses Quartz CGWindowListCopyWindowInfo and CGEventCreateKeyboardEvent instead of System Events
- Target app (WeChat) must be installed and logged in
- **v10**: Volcengine ARK API key configured in `~/.hermes/config.yaml` → `providers.doubao.api_key` (automatically read by script, no env var needed)

---

## 微信桌面端界面布局与操作方法

### 一、主界面三栏布局

```
┌──────────────────────────────────────────────────────────────┐
│  导航栏(0~60px)  │  会话列表(60~310px)  │  聊天详情(310px~W)  │
│                  │                      │                    │
│  [头像]          │  [搜索框]   [+]      │  标题栏(0~60px)    │
│  [聊天] ◀激活    │  ─────────────────   │  ────────────────  │
│  [通讯录]        │  会话1   时间        │  消息区            │
│  [收藏]          │  会话2   时间        │  (60px~H-160px)   │
│  [朋友圈]        │  会话3   时间        │                    │
│  [视频号]        │  ...                │                    │
│                  │  ⚠️ 倒序排列:        │  ────────────────  │
│  [手机]          │   最新在上           │  功能栏(H-160~H-120)│
│  [设置]          │   最早在下           │  输入区(H-120~H)   │
└──────────────────────────────────────────────────────────────┘
```

### 二、导航栏（左侧，0~60px，极窄固定）

| 位置 | 组件 | 说明 |
|------|------|------|
| 顶部 | 用户头像 | 约(30,30)位置，点击进入个人页 |
| 中部 | 聊天/通讯录/收藏/朋友圈/视频号 | 图标阵列，"聊天"为默认激活 |
| 底部 | 手机连接状态 + 设置按钮 | 左下角"更多/设置"菜单 |

### 三、会话列表栏（中间，60~310px，固定250px宽）

| 区域 | 说明 |
|------|------|
| 顶端 | 搜索框（占栏宽80%）+ "+"号发起群聊按钮 |
| 列表区 | Y=60px向下延伸，每个条目约70px高 |

**单个会话条目结构**（从左到右）：

| 子区域 | 内容 | 尺寸 |
|--------|------|------|
| 左侧头像 | 圆形，直径48~52dp，距左边缘12~16dp | ~50px |
| 中间文字 | 第一行：会话名称（加粗16~17sp）<br>第二行：消息预览（灰色13~14sp）<br>群聊格式："发送者昵称: 消息内容" | 占宽50%~70% |
| 右侧信息 | 时间标签（浅灰11~12sp）<br>未读标记（红色圆点/数字）<br>免打扰图标 | 40~60px |

**⚠️ 列表排列规则（CRITICAL）**：
- **倒序排列**：最新消息的会话在最上方，最旧的在最下方
- 置顶会话固定在列表最上方（灰色图钉图标）
- 要查找历史会话，必须**持续向下滚动**
- 条目间有极浅灰分割线（0.5pt），从头像右侧延伸

**日期显示规则**：

| 时间 | 显示格式 | 示例 |
|------|---------|------|
| 今天 | `HH:MM` | `11:13` |
| 昨天 | `昨天 HH:MM` | `昨天 18:05` |
| 本周内 | `星期X` | `星期五` |
| 更早 | `MM/DD` 或 `M月D日` | `03/30` |

### 四、聊天详情区（右侧，310px~W，动态拉伸）

| 区域 | 坐标 | 内容 |
|------|------|------|
| 标题栏 | 0~60px | 左侧返回"<"、中间会话名称、右侧"..."（聊天信息） |
| 消息区 | 60px~H-160px | 对方消息靠左（白色气泡）、己方消息靠右（绿色气泡）<br>时间提示居中（如"昨天 19:30"）<br>**向上滚动加载更早的历史消息** |
| 功能栏 | H-160~H-120px | 表情、文件、截图、搜索等图标 |
| 输入区 | H-120~H | 文本编辑框 + 发送按钮 |

**聊天记录浏览方法**：
- 向上滚动（鼠标滚轮/触控板双指上滑）加载更早消息
- 每次加载约20~30条，直到全部加载完毕
- 向下滚动或点击右下角"跳到底部"按钮回到最新消息
- 点击标题栏"..."→"查找聊天记录"→"日期"可按日历定位

## ⚠️ 服务号/订阅号处理策略（绝对核心规则）

### 规则声明
**服务号/订阅号/公众号/微信团队/微信支付 → 完全跳过，不予读取！** 理由：
- 点击后进入**二级页面**（非正常聊天详情），脚本无法像普通会话那样滚动读取消息
- 即使通过预览能获取到一条消息摘要，用户也**明确要求完全避开**，不保留任何内容
- 误入后要立即退出，不执行任何OCR读取操作

| 会话名称 | 点击后行为 | 处理方式 |
|----------|-----------|---------|
| **服务号** | 进入服务号列表 | ✅ **彻底跳过：不点击、不查看、不记录内容** |
| **订阅号** | 进入订阅号文章列表 | ✅ 同上 |
| **订阅号消息** | 同"订阅号" | ✅ 同上 |
| **微信团队** | 官方服务页面 | ✅ 同上 |
| **微信支付** | 支付通知列表 | ✅ 同上 |

### 识别方式
- 在会话列表中通过 OCR 识别会话名称
- 名称匹配关键词：`["服务号", "订阅号", "订阅号消息", "公众号", "微信团队", "微信支付"]`
- **不作模糊匹配**，精确匹配以上名称才跳过
- 扫描时，OCR 识别到任一关键词，直接跳过该条目，不点击不记录

### 误入退出流程（安全网）
如果因 OCR 误识别或点击偏移误入：

1. **检测**：OCR 标题栏区域 `(CHAT_X_START+5, 10, 80, 40)` 检测 `"<"` 或 `"< 服务号"` / `"< 订阅号"`
2. **退出（首选）**：点击标题栏左侧 `"<"` 左箭头返回 — 坐标 `wx+CHAT_X_START+25, wy+30`
3. **退出（备用）**：按 ESC 键，最多3次
4. **验证**：确认已返回普通会话列表界面
5. **不执行任何OCR读取**：即使在二级页面中看到内容，也**不保存不记录**

### 报告中的表示
- 扫描报告**不包含**任何服务号/订阅号内容
- 报告中可提及一句：`*服务号/订阅号内容已按配置跳过*`
┌──────────────────────────────────────────────────────────────┐
│  聊天详情区                                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ < 服务号               搜索栏                            │ │
│  │ ────────────────────────────────────────────────────── │ │
│  │ 搜索栏下方：                                           │ │
│  │  "服务号"                                              │ │
│  │ ────────────────────────────────────────────────────── │ │
│  │  [公众号1]                                            │ │
│  │  [公众号2]                                            │ │
│  │  ...                                                 │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```
- **左上角**：显示"`< 服务号`"，其中"`<`"是点击退出返回会话列表的左箭头按钮
- **搜索栏下方**：有"服务号"文字标识当前页面类型
- **右侧**：显示服务号/公众号列表，而非正常聊天详情
- **退出方法**：点击"`<`"左箭头，不是点击"服务号"文字，是点击箭头本身！

### 5. 逐日累积扫描策略（v11 推荐）

每周扫描按天分批执行，每天完成后检查结果再继续：

```bash
# 周一 (6/8): 只扫周一
python3 scripts/scan_wechat_v10.py --start-date 2026-06-08 --end-date 2026-06-08

# 周二 (6/9): 扫周一+周二（累积）
python3 scripts/scan_wechat_v10.py --start-date 2026-06-08 --end-date 2026-06-09

# 周三~周五: 逐步扩大 end-date
```

**原理**: 微信列表按活动时间倒序排列。周一会话=周一有交互，历史只需看周一。周二的会话=最近一次在周二，需看周一+周二。以此类推，周五需看周一~周五。

**进度监控**: 脚本跑在后台时，每 1-2 分钟 `tail -5 /tmp/wechat_scan_xxx.log` 检查进度，不要一次 `sleep 300+` 让用户干等。

### 6. VLM Provider 切换

脚本支持 Doubao 和 MiMo 两种视觉模型，修改 `VLM_PROVIDER` 变量切换：

```python
VLM_PROVIDER = "mimo"  # doubao | mimo
```

| Provider | 模型 | 代理 | 注意 |
|----------|------|------|------|
| doubao | doubao-seed-2-0-lite-260215 | 直连 | 国内端点 |
| mimo | mimo-v2.5 | HTTP 127.0.0.1:1087 | 推理模型，max_tokens=8000，需 fallback 到 reasoning_content |

MiMo V2.5 是推理模型，`content` 可能为空（token 被 reasoning 吃光），脚本已自动 fallback 到 `reasoning_content`。

### 7. 点击坐标重试机制（v11）

标题验证不匹配时自动重试，依次尝试偏移：`[0, -70, 70, -140, 140]`。

实测发现偏移主要是 -70px（Doubao y_center 系统性偏下 1 个会话），少数需要 -140px。

### 8. 列表见底自动停止（v11）

连续 3 屏所有会话都已见过 → 自动退出扫描循环，不再浪费 20+ 屏空滚。

### 9. 扫描完成后自检摘要（v11）

每次扫描结束自动打印：
```
📋 扫描自检完成
  总会话: 12 | 成功: 7 | 失败: 0
  威发: 成功2 失败0
  ❌ 失败会话: ...
  ✅ 已读会话: ...
```

### 5. 补充扫描遗漏群聊（CRITICAL — 用户指定扫描特定群聊）

**场景**: 自动扫描完成后，用户发现某个群聊（如"倪好辣"）因名称不含"威发"但实际包含威发相关联系人，需要补充扫描。

**处理流程**:
```
1. 定位群聊（从会话列表手动滚动查找）
2. 进入群聊读取聊天内容
3. 检测是否有用户发言
4. 如果有用户发言 → 加入报告
5. 返回会话列表
```

**⚠️ 微信搜索框的陷阱（CRITICAL）**:
- 点击搜索框后，微信默认进入 **"搜一搜"模式**（搜索全平台内容），而非会话列表搜索
- "搜一搜"模式下输入关键词搜索的是公众号/视频号等，不是会话
- **不要用搜索框定位群聊！** 改用滚动会话列表的方式手动查找
- 退出搜索：按ESC或点击搜索框右侧"×"关闭搜索，回到会话列表

**手动定位群聊方法**:
1. 先点击列表区域获取焦点
2. 滚动到列表顶部（向上滚30次）
3. 逐步向下滚动，每滚3-5次OCR一次
4. 在OCR结果中搜索目标群聊名称关键词
5. 找到后计算点击坐标并点击进入

**用户发言检测**:
- 用户微信昵称可能为"童"、"童小军"、"童G"等变体
- 检测关键词列表: `USER_IDENTIFIERS = ["童", "童小军", "童G", "图多多"]`
- 在OCR聊天内容中搜索这些关键词
- 如检测到，在报告中标注: `> ✅ **该群聊确认有童（你）的发言**，涉及...`
- 也可通过消息气泡颜色区分（绿色=己方，白色=对方），但OCR无法直接识别颜色

### 六、坐标系

- macOS使用逻辑坐标（cliclick、AppleScript、screencapture -R）
- Retina屏幕物理像素 = 2 × 逻辑坐标
- 窗口坐标通过AppleScript动态获取，不硬编码

---

## ⚠️ 关键技术约束（必读）

### 0. 窗口最小化 = 无法截图（CRITICAL — 2026-05-15 实测）

macOS 最小化（Dock 中）的窗口**不渲染**，所有截图方法均失败：
- `screencapture` 拍到的是窗口消失前的缓存坐标位置，实际内容已不可见
- cua-driver `capture(app="WeChat")` 返回 0x0
- `osascript position/size` 返回的是最小化前缓存坐标，不可信
- **恢复方法**: `open -a WeChat` 或 `osascript -e 'tell app "WeChat" to activate'`
- **可操作状态**: 窗口在其他 Space、被遮挡、置于后台 — 均正常截图

### 1. 微信状态检查 — 每次操作前必须确保在微信普通会话列表界面（CRITICAL）

**这是第一条关键经验，必须在每次操作微信前执行！**

| 检查项 | 检测方法 | 恢复操作 |
|--------|---------|---------|
| 激活主窗口 | `activate_app("WeChat")` | 如果焦点在其他窗口，激活微信 |
| 检测二级页面 | `detect_subpage()` — OCR标题栏查找"< 服务号" | 点击"<"左箭头或ESC退出 |
| 检测会话列表 | OCR列表区域查找日期/搜索关键词 | 点击左侧导航栏"聊天"按钮 |

**实现方式**:
```python
def ensure_wechat_ready(bounds, max_retries=5):
    """确保微信处于普通会话列表界面 — 每次操作前必须调用"""
    for attempt in range(max_retries):
        # 1. 激活微信窗口
        activate_app("WeChat")
        
        # 2. 检测是否在服务号/订阅号二级页面
        if detect_subpage(bounds):
            print("⚠️ 检测到进入了服务号/订阅号界面")
            exit_subpage(bounds)  # 点击"<"退出
            return True
        
        # 3. 检测是否在普通会话列表
        # OCR列表区域，检查是否有日期格式或"搜索"等特征
        if 检测到会话列表特征:
            print("✅ 微信已在普通会话列表界面")
            return True
        
        # 4. 可能打开了其他窗口，点击导航栏"聊天"按钮
        click_at(导航栏聊天按钮坐标)
    
    return False  # 经过重试仍未恢复
```

**使用位置**: 脚本开始时、每次关键操作前、从聊天详情返回列表后

## 滚动方案进化史（关键经验）

### v9.0~v9.3: Quartz CGEvent scroll (FAILED silently)
```python
Quartz.CGEventCreateScrollWheelEvent(...)
Quartz.CGEventPost(kCGHIDEventTap, scroll)
```
**问题**: `CGEventPost(kCGHIDEventTap, ...)` 需要 Accessibility 权限，没有的话**静默失败**（rc=0 但不滚动）。

### v9.4: cliclick kp:key (WORKS with Accessibility)
```python
subprocess.run(["/opt/homebrew/bin/cliclick", "kp:arrow-down"])
subprocess.run(["/opt/homebrew/bin/cliclick", "kp:page-up"])
```
**关键**: 必须
1. **终端授予 Accessibility 权限**（系统设置 → 隐私与安全性 → 辅助功能 → 勾选「终端」）
2. **点击目标区域获取键盘焦点后**再发送按键

### 有效按键列表
`cliclick kp:` 支持（通过错误信息获知）：
`arrow-down`, `arrow-up`, `arrow-left`, `arrow-right`, `page-up`, `page-down`, `esc`, `enter`, `tab`, `space`, `return`, `delete`, `fwd-delete`, `home`, `end`

**注意**: ⚠️ `cliclick kp:escape` 是**无效**的！必须是 `kp:esc`。

## 窗口坐标方案进化史

### v9.0~v9.3: AppleScript System Events (FAILED)
```applescript
tell application "System Events"
  tell process "WeChat" to get position of front window
end tell
```
**问题**: 需要 Accessibility 权限，没有则阻塞超时。

### v9.4: Quartz CGWindowListCopyWindowInfo (WORKS without Accessibility)

```python
import Quartz
windows = Quartz.CGWindowListCopyWindowInfo(
    Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
    Quartz.kCGNullWindowID)
for win in windows:
    owner = win.get('kCGWindowOwnerName', '')
    # 微信的 owner 是 "微信"（中文），不是 "WeChat"！
    if owner == "微信":
        bounds = win.get('kCGWindowBounds', {})
        x, y, w, h = bounds['X'], bounds['Y'], bounds['Width'], bounds['Height']
```

**关键发现**:
- 微信主窗口 owner = `"微信"`（中文），不是 `"WeChat"`
- 微信可能有多个窗口（layer 0=主窗口，layer=3+ 浮动小窗口）
- 必须按面积取最大窗口，排除 layer>=3 的浮动窗口

### 2.1 微信搜索框陷阱（CRITICAL — 不要用搜索框定位会话！）

| 陷阱 | 说明 |
|------|------|
| 搜索框默认进入"搜一搜" | 点击搜索框后，输入文字搜索的是公众号/视频号等全平台内容，**不是会话** |
| 无法定位特定群聊 | "搜一搜"模式下无法精确找到指定名称的会话 |
| 正确方案 | **手动滚动会话列表**逐屏OCR查找，或使用微信"查找聊天记录"功能 |

**正确查找特定群聊的方法**:
1. 按ESC关闭搜索（如果已打开）
2. 滚动会话列表到顶部
3. 逐步向下滚动，每滚3-5次OCR一次
4. 在OCR结果中搜索目标群聊名称

### 2.2 用户发言检测（v9.3 新增）

在读取群聊内容时，检测是否有用户（童）的发言：

| 检测方式 | 说明 |
|---------|------|
| OCR关键词搜索 | 在聊天内容中搜索用户昵称变体 |
| 用户标识符列表 | `["童", "童小军", "童G", "图多多"]` — OCR可能识别为不同变体 |
| 报告标注 | 如检测到用户发言，在会话记录末尾标注确认信息 |
| 绿色气泡 | 己方消息靠右绿色气泡，但OCR无法识别颜色 |

**Quartz CGEvent 滚动代码**:
```python
import Quartz, time

def scroll_at(cx, cy, delta, count=1):
    """在指定位置滚动
    delta>0 向上, delta<0 向下, |delta|=120约滚1行
    """
    move = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved,
        Quartz.CGPoint(cx, cy), Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
    time.sleep(0.1)
    for _ in range(count):
        scroll = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitPixel, 1, delta)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, scroll)
        time.sleep(0.03)
```

### 2. IDE焦点抢占（CRITICAL）

在 WorkBuddy 或其他 IDE 终端中执行命令时，**终端进程会抢占 macOS 窗口焦点**，导致 GUI 自动化操作作用于 IDE 窗口而非目标应用。

**解决方案**: 必须通过 `nohup` 后台执行：
```bash
cat > /tmp/_run.sh << 'SCRIPT'
#!/bin/bash
sleep 1
python3 scripts/scan_wechat_v9.py
SCRIPT
chmod +x /tmp/_run.sh
nohup /tmp/_run.sh > /tmp/scan_output.txt 2>&1 &
```

### 3. 操作方式选择

| 操作 | 可用方式 | 不可用方式 |
|------|---------|-----------|
| **点击** | `cliclick c:x,y`（系统级鼠标事件，不受焦点影响） | AppleScript `click at {x,y}` 对微信/飞书 UI **无效** |
| **滚动** | **Python Quartz CGEvent**（唯一可靠方案） | `cliclick scroll`（不支持）、AppleScript 方向键（不可靠） |
| **截图** | `screencapture -x -Rx,y,w,h`（指定区域） | 全屏截图后裁剪（效率低） |
| **键盘输入** | AppleScript `keystroke` + `pbcopy`/`pbpaste` 粘贴中文 | 直接输入中文（输入法干扰） |

### 4.2 聊天区滚动获取焦点（v9.4 CRITICAL）

在聊天内容中使用 page-up 滚动历史消息前，**必须点击聊天内容区域获取键盘焦点**：

```python
# 进入阅读聊天内容后立即点击内容区底部获取焦点
click_at(chat_cx, chat_y + chat_h - 30, hold=0.3)
time.sleep(0.3)

# 然后每次滚动前也重新点击确保焦点
click_at(chat_cx, chat_cy, hold=0.2)
for _ in range(8):
    press_key("page-up")
```

不加 focus click 的话，page-up 键会发到错误的区域（列表栏），导致聊天内容无法滚动。

### 4.3 列表滚动获取焦点（v9.4 CRITICAL）

在列表中使用 arrow-down 滚动前，同样需要先点击列表区域获取焦点：

```python
def scroll_list_down(cx, cy, amount=5):
    # 先点击列表区域获取键盘焦点
    subprocess.run([cliclick, f"c:{cx},{cy}"], capture_output=True)
    time.sleep(0.15)
    for _ in range(amount):
        subprocess.run([cliclick, "kp:arrow-down"], capture_output=True)
        time.sleep(0.05)
```

**所有脚本循环必须指定最大迭代次数，禁止 `while True`**

| 循环类型 | 最大次数 | 说明 |
|---------|---------|------|
| 列表滚动定位 | ≤100次 | 约100屏足够覆盖大多数列表 |
| 会话扫描循环 | ≤50屏 | 每屏约8个会话，50屏=400个 |
| 聊天详情滚动读取 | ≤20次 | 大多数会话20屏内可读完 |
| 点击/OCR重试 | ≤5次 | 含服务号检测和自动退出重试 |

### 5. 进入服务号检测（CRITICAL — 自动恢复机制）

**每次OCR前自动检测是否误入了服务号/订阅号界面**

| 检测时机 | 检测内容 | 处理方式 |
|---------|---------|---------|
| 每次OCR前 | 标题栏是否有"< 服务号"或"< 订阅号" | 自动退出后再执行OCR |
| 检测方法 | `detect_subpage()` 函数 | OCR标题栏区域查找"<"字符 |
| 退出方法 | `exit_subpage()` 函数 | 点击左箭头"<"或ESC键 |
| 备用方案 | 3次ESC强制退出 | 防止退出失败导致死循环 |

**实现方式**:
```python
def ocr_with_subpage_check(path, bounds):
    """执行OCR，但先检查是否进入了服务号/订阅号二级页面"""
    # 检查是否进入了二级页面
    if detect_subpage(bounds):
        print("⚠️ 检测到进入了服务号/订阅号二级页面，准备自动退出...")
        # 尝试退出二级页面
        success = exit_subpage(bounds)
        if not success:
            # 备用：3次ESC强制退出
            for i in range(3):
                press_escape()
                if not detect_subpage(bounds):
                    break
    
    # 执行OCR
    return ocr(path)
```

### 6. 超时保护（CRITICAL — 安全机制）

**⚠️ 防止脚本失控抢夺鼠标控制权**

| 安全规则 | 说明 |
|---------|------|
| 单次操作超时 | GUI操作超过 **60秒** 无正确输出 → 立即停止脚本 |
| 超时触发 | 抛出 `TimeoutError`，释放鼠标控制权 |
| 保护范围 | 点击、滚动、键盘输入等所有GUI操作 |

**实现方式**:
```python
# 每次GUI操作前检查超时
def check_timeout(operation_name):
    if (current_time - last_success_time) > 60:
        raise TimeoutError(f"操作超时: {operation_name}")

# 每次成功操作后重置计时
def reset_success_time():
    last_success_time = time.time()
```

### 6. 列表倒序排列（CRITICAL）

微信会话列表**倒序排列**（最新在上，最旧在下），找历史会话必须**向下滚动**。

### 6. 日期范围可配置

报告时间范围为可配置项，通过 `--start-date` / `--end-date` 参数指定，默认取上周一到上周日。

---

## Workflow

### 逐日扫描模式（用户偏好 — CRITICAL 日期累积逻辑）

**微信会话列表按最后活动时间倒序**。显示"周二"的会话意味着最后一次交互在周二，**该会话周一也有内容**。因此逐日扫描时必须累积日期范围，不能只看当天：

```
第1天(周一): --start-date 6/8 --end-date 6/8     → 仅周一
第2天(周二): --start-date 6/8 --end-date 6/9     → 周一+周二
第3天(周三): --start-date 6/8 --end-date 6/10    → 周一~周三
...
```

**每天跑完停下来汇报，等用户确认再继续下一天。** 详见 `references/cumulative-date-scanning.md`。

### Step 0 — Build OCR Tool (first-time only)

Check if the OCR binary exists at `scripts/ocr_tool`. If not, build it:

```bash
python3 scripts/build_ocr.py
```

The OCR tool uses Apple's Vision Framework for accurate Chinese+English recognition.
It produces one line of text per recognized region, sorted top-to-bottom.

### Step 1 — 定位起始日期

滚动微信会话列表到目标周的起始日期：

1. 激活微信：`osascript -e 'tell application "WeChat" to activate'`
2. 获取微信窗口坐标：AppleScript `position` + `size`
3. 计算列表区域坐标
4. 用 Quartz CGEvent **向下**滚动列表（列表倒序，向下=更早）
5. 每滚3~5次OCR一次，检测日期格式
6. 发现目标日期后停止（最多100次滚动）

### Step 2 — 边扫描边读取（v10 推荐用 Doubao VLM）

⚠️ **必须使用"边扫描边读取"策略**，不要"先扫描后读取"！

**v10 推荐方案**：用 Doubao 视觉模型一次识别整屏会话列表，返回 JSON（name + date + y_center 精确坐标）。
```
截图层区域 → Doubao API → JSON [{name, date, y_center}, ...] → 精确点击 → 读聊天 → 返回继续
```
- 调用方法：`doubao_list_sessions(image_path, list_y, list_h)` 返回精确 click_y_est
- 无需偏移修正重试（坐标精确）
- API key 从 `config.yaml` 自动读取
- 详见 `references/vlm-recognition.md`

**旧方案（回退用）**：ocr_tool + parse_ocr_to_sessions（估算 Y 坐标，需 ±105px 偏移修正）：
```
OCR当前列表 → 解析会话名+日期 → 判断是否目标 → 是则点击读取 → 返回继续滚动
```
- OCR行顺序：名称→预览→日期
- 遇到日期行时，向上找最近的非日期行 = 会话名
- 同一日期只取第一个非日期行
- 过滤群聊预览消息（如"02陈熌赫妈妈：[视频号]"）

**点击定位**:
- 点击位置 = list_y + name_line_idx * pixels_per_line + pixels_per_line/2
- pixels_per_line = list_h / len(ocr_lines)
- ⚠️ 点击可能偏移到相邻会话（±1个会话），这是已知限制

**特殊会话处理**:
- 服务号、订阅号、订阅号消息、微信团队、微信支付 → **跳过（黑名单，不点击不查看！）**
- 误入二级页面：点击标题栏左侧"<"左箭头返回（坐标 `wx+CHAT_X_START+25, wy+30`），备用按ESC
- 所有循环限制最大迭代次数（见上表）

### Step 3 — 读取聊天内容（可配置深度）

进入聊天详情后：
1. OCR当前可见消息区
2. 向上滚动加载历史消息（最多 **n_scrolls 次**，默认8次）
3. 遇到早于目标日期的消息时停止
4. 过滤系统消息（"xxx撤回了一条消息"等）
5. 返回列表继续扫描

**⚡ 快速模式**: 将 `n_scrolls` 设为 0（只读可见区域，约15~20行）或 3（快速滚几下）。周报场景用 0~3 次就够，省 40% 时间。详见 `references/speed-optimization.md`。

### Step 4 — 生成报告

1. 合并所有会话聊天记录（JSON格式）
2. 按话题分类整理（非按会话分类）
3. 生成Markdown格式周汇总报告

### Step 5 — 补充扫描遗漏群聊（用户指定时执行）

当用户指出某个群聊名称不含关键词（如"威发"）但实际是相关会话时：

1. **关闭搜索框**（如已打开）：按ESC或点击"×"
2. **定位群聊**：手动滚动会话列表，逐屏OCR查找目标名称
3. **进入群聊**：点击进入，读取聊天内容（同Step 3流程）
4. **检测用户发言**：在OCR结果中搜索用户标识符
5. **更新报告**：将群聊记录加入对应分类，标注用户发言情况
6. **返回列表**：点击列表区域返回会话列表

---

## 日期范围配置

报告时间范围为可配置项，通过命令行参数指定：

```bash
# 指定日期范围
python3 scan_wechat_v9.py --start-date 2026-03-30 --end-date 2026-04-05

# 默认取上周（自动计算上周一~上周日）
python3 scan_wechat_v9.py
```

默认日期计算逻辑：
```python
from datetime import datetime, timedelta
today = datetime.now()
this_monday = today - timedelta(days=today.weekday())
last_monday = this_monday - timedelta(days=7)
last_sunday = this_monday - timedelta(days=1)
```

---

## 运行指令

```bash
# v10 推荐：Doubao VLM 精确坐标扫描
python3 scripts/scan_wechat_v10.py --start-date 2026-05-11 --end-date 2026-05-17

# v9.x 旧方案：OCR 估算坐标（回退用）
python3 scripts/scan_wechat_v9_5.py --start-date 2026-03-30 --end-date 2026-04-05

# 默认上周
python3 scripts/scan_wechat_v10.py
```

---

---

## 优化路线图（2026-05-10 更新）

| 优先级 | 修改 | 预期提升 | 状态 |
|--------|------|---------|------|
| **P0** | **VLM 视觉识别列表解析** — 用 Doubao/Gemini 替代 ocr_tool 解析会话列表，返回精确坐标 JSON | **消除点击偏移根因**（60%→~100%） | ✅ **v10 已实现（2026-05-17）** |
| **P0** | **坐标偏移重试** — 标题不匹配时自动 ±70/140px 重试 | 0 失败 | ✅ **v11 已实现（2026-06-14）** |
| **P0** | 列表见底自动停止 — 连续 3 屏全见过 break | 省 10+ 分钟 | ✅ **v11 已实现（2026-06-14）** |
| **P0** | **MiMo V2.5 多模型支持** — 支持 Doubao/MiMo 切换 | 备选模型 | ✅ **v11 已实现（2026-06-14）** |
| **P0** | **自检摘要** — 每次扫描结束打印成功/失败统计 | 实时反馈 | ✅ **v11 已实现（2026-06-14）** |
| **P1** | 聊天内容读取也改用 VLM（替代 ocr_tool） | 提升消息识别准确率 | 🔲 待实现 |
| **P1** | save_partial() 部分保存 + try/finally 保护 | 防数据丢失 | ✅ v9.5 已完成 |
| **P2** | **聊天滚动修复**（移除 activate_app + click_at，delta +600） | +15~20% | ✅ v9.5.4 已完成 |
| **P3** | 动态布局校准 calibrate_layout() | 窗口缩放适应 | ✅ v9.5.5 已完成 |
| **P4** | 点击偏移扩大重试（已被 v11 取代） | — | ⚫ 被 v11 取代 |
| **P7** | **SightFlow 视觉后端集成** | 跳过 Accessibility 限制 | 🔲 极早期 |

### 工具兼容性关键发现

**微信 macOS 版不暴露内部 UI 给 Accessibility API** — 这意味着任何依赖 AX 树的自动化工具（Hermes `computer_use`、Peekaboo、cliclick、**WeChat-MCP**）都**无法直接定位微信内部元素**（会话列表、消息气泡、输入框）。只能定位到窗口级别。

实测证实（2026-05-15）：
- WeChat 主窗口 AX 树仅 3 个元素：AXButton (close), AXButton (minimize), AXButton (maximize)
- WeChat-MCP 的 `find_search_field` 查找 `kAXTextAreaRole + title="Search"` 永远找不到
- `fetch_messages_by_chat` 始终返回 error: "Could not find WeChat search text field via Accessibility API"
- 这是 Qt Quick/QML 渲染架构的结果：不向 macOS Accessibility API 暴露应用层控件

解决方案方向：
- **VLM 视觉驱动**（截图→AI识别控件坐标）— SightFlow 采用此方案
- **纯截图流**（screencapture → vision_analyze → 手动定位坐标）— 当前唯一可用方案
- SightFlow 是目前唯一真正解决微信内部 UI 自动化的开源项目（但极早期，238⭐）

## 自动化方案选型原则（用户明确指示）

**绝对禁止 DB 访问方式。** 用户明确表态：微信是闭源 App，没有提供 DB 访问接口，不应用任何
DB 解密/读取方式（包括 wechat-skill 的 LLDB 密钥提取、chatlog-bot 的 SQLCipher 解密、
wechat-db-decrypt-macos 等）。**只允许 UI 层方案：**

| 允许 | 禁止 |
|------|------|
| screencapture + vision_analyze | 数据库解密 (SQLCipher) |
| cua-driver 点击/滚动/按键 | LLDB hook / 进程注入 |
| 纯 Accessibility API 读 UI 控件文本 | 内存扫描提取密钥 |
| CGEvent 模拟输入 | iPad 协议模拟 |
| SightFlow VLM 视觉驱动 | wechat-skill 的 send hijack |

**当前唯一可行方案**: `screencapture` 截图 + `vision_analyze` (Doubao) 解析。

**已排除的路线**:
- WeChat-MCP (BiboyQG) Accessibility API 读取 — 2026-05-15 实测：WeChat 4.x 的 AX 树仅暴露 macOS 窗口按钮(close/minimize/maximize)，无内部 UI 控件。`tools/call fetch_messages_by_chat` 始终返回 `"Could not find WeChat search text field via Accessibility API"`。
- SightFlow VLM 视觉驱动 — 极早期(238⭐)，尚未稳定。

参见 `references/automation-tool-landscape.md` 和 `references/im-automation-tools.md`。

### 视觉模型选型 (WeChat 截图分析)

2026-05-15 实测对比 `doubao-seed-2-0-lite-260215` vs `gemini-2.5-flash`：

| 维度 | Doubao | Gemini |
|------|--------|--------|
| 聊天列表识别 | 全对 | 全对 |
| 消息内容 OCR | 完整 + 时间戳 | 完整，缺时间戳 |
| 侧边栏图标识别 | 9/9 全对 | 6/9，视频号/小程序/看一看顺序混淆 |
| 中文 OCR 精度 | 优秀 | 良好 |
| 费用 | ~$0 (火山赠金) | $0 (Google AI Studio 免费层) |

**结论**: Doubao 中文 OCR 和微信图标识别更准，保持为主力。Gemini 免费且日常截图分析够用，
可作为备选（火山赠金用完后切换）。

**Provider compatibility matrix**: See `references/vision-provider-compatibility.md` for which APIs support vision/multimodal input — DeepSeek (NO), MiMo (model-dependent), Doubao (YES), Gemini (YES).

## v10 已知修复 (2026-06-14)

### 修复1: 列表见底死循环

**症状**: 列表扫描到第 22 屏后每屏只剩 1 个会话（最底部），但循环继续滚到 50 屏才停，浪费大量时间。

**修复**: 在 `scan_wechat_v10.py` 的 Phase 2 循环末尾加入连续空屏检测：
- 定义 `consecutive_all_seen = 0` 在循环外
- 每屏处理后，如果所有条目都已 `seen_names`，`consecutive_all_seen += 1`
- 连续 3 屏无新会话 → `break` 退出

### 修复2: Doubao VLM 点击 +70px 偏移

**症状**: 点击会话 N 时偏上 1 个会话高度，打开会话 N-1。标题核验全失败（点击"杨少军 威发"打开"翟亮zl"）。

**根因**: `click_y = list_y + int(y_img / 2)` 计算出的坐标比实际位置偏高约 70px（1 个会话条目高度）。

**修复**: 改为 `click_y = list_y + int(y_img / 2) + 70`，成功率从 ~30% 提升到 ~83%（5/6）。

## 当前瓶颈（✅ v10 已解决）

v10 用 Doubao VLM 直接返回精确 y_center 坐标，彻底绕过 ocr_tool 的 Y 坐标估算问题。点击偏移不再是瓶颈。

旧问题（v9.5.5~v9.5.6，供参考）：

v9.5.5 成功率 62%，11 个失败全部是 OCR 点击偏移（click_y_est 偏差 3+ 会话，±105px/5次重试无法覆盖）。根因：

```
pixels_per_line = list_h / len(ocr_lines)
click_y = list_y + name_idx * pixels_per_line + pixels_per_line/2
```

`len(ocr_lines)` 包含了日期行、预览行、空行等非会话条目行，导致 `pixels_per_line` 偏小，`click_y` 偏差可达 100~200px。

**修复方向**：
- **方案A**：modify `build_ocr.swift` 使 `ocr_tool` 返回每个识别区域的 bounding box (x,y,w,h)
- **方案B**：改用固定条目高度估算 `click_y = list_y + session_index * 70 + 35`

### 方案C（✅ 已测试，推荐）：VLM 视觉识别替代 OCR

2026-05-17 实测：用 Doubao 视觉模型直接识别会话列表截图，返回结构化 JSON（name + date + y_center）。一次 API 调用识别 7 个会话，全对，精度远超 ocr_tool。

| 方案 | 点击精度 | 速度 | 费用 |
|------|---------|------|------|
| ocr_tool（方案A 未实施） | ~60% 成功率 | 毫秒级 | 免费 |
| **VLM（Doubao）** | **接近 100%** | ~1-2s/屏 | 火山赠金 / Gemini 免费 |

**优势**：
- 每个会话返回**精确 y_center 像素坐标**，无需 `pixels_per_line` 估算
- 一次识别整个列表区域，无需逐行 OCR 拼凑
- 自动识别公众号/服务号等需跳过的会话类型
- 中文识别率比本地 OCR 更高

**坐标映射**（Retina 2x → 逻辑坐标）：
```python
logical_y = y_center / 2                    # Retina → 逻辑
screen_y = wy + LY + logical_y              # LY = 列表区相对窗口 Y 偏移
screen_x = wx + LX + LW / 2                 # 列表区水平居中
```

详见 `references/vlm-recognition.md`。

---

## Common Issues & Fixes

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| 滚动不生效 | cliclick v5.1 不支持 scroll | **必须用 Quartz CGEvent 滚动** |
| 方向键不滚动 | 焦点不在列表区域 | 用 Quartz CGEvent 代替方向键 |
| ⭐ **cliclick kp:arrow-down/kp:page-up 完全无效**（实测 2026-04-26） | 即使 `cliclick` 已授予 Accessibility 权限，`kp:arrow-down` 对微信列表滚动也**不生效**。`kp:page-up` 同样无法滚动聊天内容区域 | **必须使用 Quartz CGEvent 滚动**。不要相信 cliclick 键盘事件可以滚动微信 UI。列表中点击获取焦点后再发方向键也没用。 |
| ⭐ **Quartz CGEvent 滚动唯一有效** | `CGEventCreateScrollWheelEvent` + `kCGScrollEventUnitPixel` 配合 `CGEventPost(kCGHIDEventTap)` | 参考技能中的 `scroll_at()` 函数。`delta` 正=向上，负=向下，`-120` 约滚 1 行。需先移动鼠标到目标区域。 |
| ⭐ **点击偏移 ±1~2 个会话** | `pixels_per_line = list_h / len(lines)` 不精确。OCR 行数≠会话条目数（日期行、预览行、空行混杂），导致 Y 坐标偏差 60~120px | **方案A**：改用 `ocr_tool` 返回 bounding box（需修改 Swift OCR 工具）。**方案B**：点击后验证标题，如标题与预期不匹配则微调 Y 坐标重试。**方案C**：用 Apple Vision 的 VNRequest 获取每个文本区域的精确 bounding rect。 |
| ⭐ **超时保护直接杀死脚本，已扫数据丢失**（实测 2026-04-26） | `check_timeout()` 抛出未捕获的 `TimeoutError`，脚本直接退出，`all_chat_data` 中的部分扫描结果全部丢失 | 主循环外层加 `try/except/finally`，在 `finally` 中保存 `all_chat_data` 到临时文件。或改用 `try/except TimeoutError` 优雅降级（跳过当前会话继续）。 |
| ⭐ **"公众号"黑名单可能失效**（实测 2026-04-26） | v1 扫描中，名称为"公众号"的会话未被 `is_special_session()` 跳过，而是被当作普通会话处理并被点击 | 确认 `SPECIAL_SESSIONS` 中包含 `"公众号"`。如果仍失效，可能是 OCR 识别的字符串包含不可见字符（如零宽空格）。加 `repr()` 调试输出名称。另：`SPECIAL_SESSIONS` 点击会进入二级页面，优先用黑名单匹配白名单（白名单 = 已知可安全点击的会话）。 |
| ⭐ **预览弹窗检测拖慢10x（实测 2026-05-10）** | `close_preview_windows()` 在每个点击操作后都调用 `detect_preview_window()`，检查 layer≥3 的微信窗口。实测发现**每次点击都会触发**，但 ESC 关不掉，回退到点击窗口左上角。浪费 4~6s/会话，30会话=2~3分钟。V9.3 没有这个逻辑反而跑得最快。 | **在 v9.5.x 脚本中先注释掉 `close_preview_windows()` 调用**。只在真正需要时（如聊天滚动卡死）手动启用。 |
| ⭐ **聊天详情区域 `page-up` 滚动无效**（实测 2026-04-26） | `read_chat_content()` 中 `press_key("page-up")` 使用 cliclick 发送，点击聊天区后再发 page-up 仍无效果 | 改用 **Quartz CGEvent** 在聊天区域向上滚动（delta=120）。或在点击进入聊天后使用 `osascript` 模拟 `page up` 键：`osascript -e 'tell application "System Events" to key code 116'`（116=PageUp）。 |
| ⭐ **列表到底后无限循环滚动**（v10 实测 2026-06-14） | `MAX_SCAN_SCREENS=50`，到底后每屏 1 个重复会话仍继续滚 | **v11 已修复**：加 `consecutive_all_seen` 计数器，连续 3 屏全见过自动 break |
| ⭐ **VLM 点击偏移系统性偏高 1~2 会话**（v10 实测 2026-06-14） | Doubao/MiMo 返回的 y_center 在列表不同位置精度不一致，+88px 固定偏移不够 | **v11 已修复**：标题验证不匹配时自动重试 [-70, 70, -140, 140] px，实测 -70px 覆盖 80% 情况 |
| ⭐ **MiMo V2.5 content 为空**（2026-06-14） | 推理模型 token 被 reasoning 吃光，content 为 null | 增大 max_tokens 到 8000，并 fallback 到 reasoning_content |
| ⭐ **逐日扫描 end-date 错误**（2026-06-14） | 周二只设 6/9~6/9，漏掉周一活跃但周二无新消息的会话 | 改用累积范围：周二 = 6/8~6/9，周三 = 6/8~6/10 |
| ⭐ **背景进程进度检查（用户偏好）** | `sleep 300+` 不加中间检查，用户长时间看不到进展 | 每 1-2 分钟 `tail` 日志汇报当前进度（扫到第几屏、正在读哪个会话） |
| ⭐ **脚本没有 partial save，中断即丢弃** | 所有 `all_chat_data` 只在最后一次性写入 | 每次成功读取一个会话后就追加写入临时 JSON 文件。`finally` 块中也做一次保存。 |
| 🆕 **osascript keystroke 被拦截**（2026-06-22） | macOS 安全策略: `"osascript"不允许发送按键` | **用 `key code` 替代 `keystroke`**（硬件键码，不被拦截） |
| 🆕 **搜索框进"搜一搜"模式** | 鼠标点击搜索框进全平台搜索 | **用 Cmd+F (key code 3 + cmd) 进入会话搜索模式** |
| 🆕 **cliclick kp:arrow-* 微信无效**（确认） | 微信不响应 cliclick 方向键 | 滚动改用 Quartz CGEvent；箭头导航改 `osascript key code` |

| 搜索定位不准 | "先扫描后读取"策略不可靠 | **用"边扫描边读取"策略** |
| 点击偏到相邻会话 | OCR行位置→Y坐标映射不精确 | 接受±1偏差，或让ocr_tool返回bounding box |
| 服务号/订阅号死循环 | 进入二级页面无法返回 | **黑名单跳过（不点击不查看）+ 点击左箭头退出** |
| 列表滚动无限循环 | 未设最大迭代次数 | **所有循环必须指定最大迭代次数** |
| 日期范围不灵活 | 硬编码在脚本中 | 使用 `--start-date` / `--end-date` 参数 |
| IDE抢占焦点 | 终端窗口获取焦点 | `nohup` 后台执行 |
| 中文输入乱码 | 输入法干扰 | `pbcopy` + Cmd+V 粘贴中文 |
| OCR内容是IDE而非微信 | 截图时微信不在前台 | AppleScript `set frontmost` + `delay` |
| AppleScript click无效 | 微信不支持Accessibility click | 改用 `cliclick c:x,y` |
| 搜索框定位群聊失败（旧） | 鼠标点击搜索框进"搜一搜" | **用 Cmd+F (key code 3+cmd) 进入会话搜索（v12 推荐）**，或手动滚动列表 |
| 遗漏不含关键词的相关群聊 | 如"倪好辣"无"威发"字样 | **用户指定后手动补充扫描（Step 5）** |
| 无法确认群聊是否有用户发言 | OCR不识别气泡颜色 | **关键词搜索用户昵称变体** |
| **❌ System Events获取窗口坐标超时** | **终端没有Accessibility权限** | **改用 Quartz CGWindowListCopyWindowInfo** |
| **❌ capture_region中System Events阻塞** | **同上** | **直接调用screencapture，移除System Events** |
| **❌ press_escape需要Accessibility** | **同上** | **改用 Quartz CGEventCreateKeyboardEvent** |

---

## Version History

| Version | Date | Key Changes | Success Rate |
|---------|------|-------------|-------------|
| **v12** | **2026-06-22** | **osascript key code 键盘操控**（替代 keystroke/方向键）、**恢复搜索功能**（Cmd+F 触发会话搜索，推翻"不要用搜索框"禁令）、key code 映射表、窗口遮挡三重激活、补充扫描改用搜索定位 | 🆕 |
| v11 | 2026-06-14 | 完整重构：双模型、标题重试、自检摘要、累计扫描 | 100% (12会话) |
| v10.1 | 2026-06-14 | 列表死循环修复、VLM 点击偏移修复 | ✅ |

| v6 | 2026-04-07 | 初始版本，cliclick scroll | 0%（滚动失败） |
| v8 | 2026-04-08 | 边扫描边读取策略 | 部分成功（滚动不可靠） |
| v9.0 | 2026-04-08 | Quartz CGEvent滚动，先扫描后读取 | 6%（2/32会话） |
| **v9.2** | **2026-04-08** | **Quartz + 边扫描边读取 + 可配置日期** | **93%（27/29威发会话）** |
| **v9.3** | **2026-04-08** | **+服务号检测增强 +微信搜索框陷阱规避 +用户发言检测 +补充扫描流程** | **93%+ 补充扫描能力** |
| **v9.4** | **2026-04-26** | **全面扫描所有会话**（不限于威发）、默认本周、跳过服务号/订阅号/公众号/微信团队/微信支付/文件传输助手、**Quartz获取窗口坐标**（替代AppleScript/System Events，无需Accessibility权限）、**cliclick kp: 滚动**（替代Quartz CGEvent，需Accessibility）、**修复kp:escape→kp:esc**、**滚动前先点击获取焦点** | **❌ 失败**（cliclick kp:arrow-down/page-up 完全无效，仅处理4个会话后超时，点击偏移±1~2个会话） |
| **v9.5.2 (推荐)** | 2026-04-27 | **单脚本方案**。滚动：Quartz CGEvent delta=-600 + activate + focus click。标题核验 + ±70px 偏移重试。聊天历史：ESC×2 + 聊天区点击 + 大delta 滚动，new_lines=0 连续 2 次判底。预览弹窗：detect/close (layer≥3)。error_msg 清空修复。日期定位：周一×3+更早×1。60s 操作超时。 | **76%（37/49）** |
| **v9.5.3** | 2026-04-27 | **方向修复**：Phase 2 从向下改**向上**滚动（定位周一后目标周在上面），停止条件从"早于×5"改"晚于 WEEK_END×5"。activate_app 三重激活（cliclick+osascript+open -a）。**窗口焦点问题**：后台进程在 macOS 上无法可靠将微信置前，导致 ensure_wechat_ready 反复失败。需前台运行或手动先将微信窗口置前。 | 未完整验证 |
| **v9.6 (废弃)** | 2026-04-27 | 拆分为逐会话独立脚本。**结论：不推荐。** 会话间状态管理（返回列表、滚动位置、窗口焦点）极度困难。ESC 不返回列表需点"<"，但"<"在列表状态下破坏流程。单脚本方案在成功率和复杂度上均更优。 | **0%** |
| **v9.5.4 (推荐)** | 2026-04-27 | **根因修复+偏移增强**：① 移除滚动前 activate_app + click_at；② 修正 scroll_chat_up delta: -600→+600；③ 恢复v9.3直接滚动风格；④ 点击偏移扩大至±105px（5次重试)；⑤ 保留标题核验+部分保存+预览弹窗检测。v9.5.4 实测验证聊天滚动修复（210行，0次+0新行）。 | **71%（17会话，超时截断）** |
| **v9.5.5 (推荐)** | 2026-04-27 | **动态布局校准 + 实测验证**：每轮任务先截图全窗口→OCR导航栏/会话列表/聊天区→动态计算各区域坐标。窗口缩放/分辨率变化时不再依赖硬编码常量。实测：29会话(16威发)，18成功(62%)，283行，0次滚动+0新行。耗时~20min。偏移失败11个（OCR click_y_est 偏差过大，±105px无法覆盖≥3会话偏移）。 | **62%（29会话）** |
| **v9.5.6 (推荐)** | 2026-04-28 | **点击精度修复**：parse_ocr_to_sessions 中 item_height 改为按会话条目数（日期行数）而非 OCR 总行数计算。旧: `list_h/27行≈23px` → 新: `list_h/9会话≈70px`，精度提升~3倍。配合±105px偏移修正覆盖±1会话偏差。实测：27会话(15威发)，18成功(67%)，286行，0次滚动+0新行，9次偏移失败(↓18%)。 | **67%（27会话）** |
| **诊断** | 2026-04-27 | 跨会话根因分析：聊天滚动失效可能因点击聊天中心命中消息气泡；窗口焦点是 macOS 硬限制；点击偏移可扩大范围修复。制定P0-P4优化路线图。 | N/A |
| **v11 (推荐)** | **2026-06-14** | **完整重构**：① MiMo V2.5 Vision 支持 + Doubao 双模型切换；② 标题不匹配自动 ±140px 五档重试（0→-70→+70→-140→+140），消除全部点击偏移失败；③ 扫描自检摘要（成功/失败/威发统计）；④ 连续3屏全见过自动退出；⑤ 逐日累积日期范围扫描策略；⑥ MiMo 推理模型 content 为空时 fallback reasoning_content。 | **0 失败 (12会话，2026-06-14 实测)** |
| **v10.1** | **2026-06-14** | **列表滚到底死循环修复**：阶段2扫描到列表底部后每屏仅1个会话且全已seen，但循环仍跑满 MAX_SCAN_SCREENS(50)。新增连续3屏无新会话检测 → 自动break退出。详见 `references/list-bottom-loop-fix.md`。 | ✅ |

### ⚠️ 背景进程进度检查（用户偏好）

GUI 扫描脚本在后台运行时，**不要只 wait 干等**。每隔 1-2 分钟 `tail` 日志汇报进度（扫到第几屏、当前读取哪个会话），让用户知道在进展。用户不耐烦长时间沉默。

在 macOS 上从 IDE/终端后台进程运行 GUI 自动化时，`activate_app`（osascript/open -a/cliclick 点击标题栏）**均不可靠**。其他应用窗口（Teams、Outlook、Chrome）会遮挡微信。**解决方案**：
1. **前台运行**脚本（终端保持在前台但微信窗口需可见）
2. 或先手动将微信窗口置前，再启动后台扫描
3. 或先最小化/隐藏遮挡窗口

---

## Output Format

```markdown
# 微信聊天记录汇总报告
**扫描时间范围**: 2026年03月30日（周一）~ 04月05日（周日）

## 执行摘要
| 指标 | 数值 |
|------|------|
| 扫描会话总数 | XX 个 |
| 威发相关会话 | XX 个 |

## 威发相关会话
### 会话名
**最后活跃**: 03月30日
**聊天内容 OCR 摘录**：
...

## 个人会话
### 会话名
...
```

---

## File Reference

| File | Purpose |
|------|---------|
| `scripts/scan_wechat_v10.py` | **v10 推荐** 主扫描脚本（Doubao VLM 精确坐标 + OCR 聊天读取） |
| `scripts/scan_wechat_v12.py` | **v12 推荐** 主扫描脚本（新增 osascript key code 搜索定位 + 键盘发送 + Cmd+F 会话搜索） |
| `scripts/scan_wechat_list.py` | **v9.6 列表扫描**：只滚动+OCR识别会话名和日期，不点击任何会话，输出JSON |
| `scripts/scan_wechat_session.py` | **v9.6 单会话读取**：接收会话名，定位→点击→滚动聊天历史→输出内容，60s超时 |
| `scripts/scan_wechat_batch.py` | **v9.6 批量协调器**：读列表JSON→逐会话调用session脚本→每完成一个反馈→汇总报告 |
| `scripts/scan_wechat_v9.py` | v9.3/v9.4 扫描脚本（含用户发言检测，v9.4 已知 cliclick 滚动失败） |
| `scripts/scan_chatlist.py` | 旧版列表扫描脚本 |
| `scripts/read_chats.py` | 旧版聊天内容读取脚本 |
| `scripts/build_ocr.swift` | Swift Vision OCR 源码 |
| `scripts/build_ocr.py` | 编译 OCR 工具 |
| `scripts/ocr_tool` | 编译后的 OCR 二进制 |
| `.learnings/LEARNINGS.md` | 开发教训与最佳实践（9条） |
| `.learnings/ERRORS.md` | 错误记录与根因分析（8条） |
| `.learnings/FEATURE_REQUESTS.md` | 功能需求与实现方案（9条） |
| `references/troubleshooting.md` | 故障排除指南 |
| `references/wechat_interface_guide.md` | 微信界面布局详细说明（含移动端） |
| `references/speed-optimization.md` | 速度优化指南：禁用弹窗检测 + 减少滚动深度 |
| `references/vlm-providers.md` | **v11** VLM 多 Provider 配置（Doubao/MiMo 切换） |
| `references/list-bottom-loop-fix.md` | 列表滚到底死循环修复 (2026-06-14) |
| `references/cumulative-date-scanning.md` | **新增** 逐日累积扫描日期范围逻辑 (2026-06-14) |
| `references/im-automation-tools.md` | **新增** IM 自动化工具（Peekaboo vs SightFlow）评估报告，含 AX 树 vs VLM 架构对比和微信不可见 UI 的发现 |
| `references/osascript-keycode-automation.md` | **v12** osascript key code 微信自动化完整指南（原理/映射表/Python封装/排障） |
## 🆕 v12: osascript `key code` 键盘操控（2026-06-22）

macOS 安全策略阻止 `osascript keystroke`，但 `key code` 使用硬件键码可绕过。
详见 `references/osascript-keycode-automation.md`（完整指南：映射表/Python封装/排障）。

**核心发现**: Cmd+F (key code 3 + command down) 触发**会话搜索模式**，与鼠标点击搜索框("搜一搜")不同。
```
鼠标点击搜索框 → "搜一搜" → 公众号/视频号/文章 (不可用)
Cmd+F 快捷键   → 会话搜索 → 联系人/群聊名称 (可用)
```

Python 封装示例:
```python
def osa_key(code, mod=None):
    cmd = f'tell app "System Events" to key code {code}'
    if mod: cmd += f' using {mod}'
    subprocess.run(["osascript", "-e", cmd])

def wechat_search(name):
    osa_key(3, "command down")      # Cmd+F
    subprocess.run(["pbcopy"], input=name.encode())
    osa_key(9, "command down")      # Cmd+V
    osa_key(36)                     # Enter

def wechat_send(msg):
    subprocess.run(["pbcopy"], input=msg.encode())
    osa_key(9, "command down")      # Cmd+V
    osa_key(36)                     # Enter
```

---
