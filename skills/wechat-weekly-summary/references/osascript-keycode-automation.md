# osascript key code 微信自动化完整指南

> **创建**: 2026-06-22 | **版本**: v12

## 原理

macOS 安全策略阻止 `osascript keystroke` 发送文本按键:
```
错误: "osascript"不允许发送按键 (1002)
```

但 `key code` 使用**硬件键码**（CGEvent keyboard event）而非文本级注入，可以绕过此限制。

## 常用 key code 映射表

| 键 | key code | 修饰键 | 用途 |
|----|----------|--------|------|
| f | 3 | cmd down | Cmd+F 搜索 |
| v | 9 | cmd down | Cmd+V 粘贴 |
| c | 8 | cmd down | Cmd+C 复制 |
| a | 0 | cmd down | Cmd+A 全选 |
| w | 13 | cmd down | Cmd+W 关闭 |
| return | 36 | — | Enter 发送 |
| tab | 48 | — | Tab 切换焦点 |
| esc | 53 | — | ESC 关闭弹窗 |
| arrow-up | 126 | — | 上箭头 |
| arrow-down | 125 | — | 下箭头 |
| arrow-left | 123 | — | 左箭头 |
| arrow-right | 124 | — | 右箭头 |
| page-up | 116 | — | Page Up |
| page-down | 121 | — | Page Down |
| space | 49 | — | 空格 |
| delete | 51 | — | 删除键 |

## 已验证场景

### 1. 搜索并打开会话

```applescript
tell application "WeChat" to activate
delay 0.5
tell application "System Events"
    key code 3 using command down   -- Cmd+F
    delay 0.5
end tell
# 通过 pbcopy + Cmd+V 粘贴中文搜索词
# key code 9 using command down
# key code 36 (Enter)
```

### 2. 发送消息

```applescript
# 复制消息内容到剪贴板，然后:
tell application "System Events"
    key code 9 using command down   -- Cmd+V 粘贴
    delay 0.3
    key code 36                     -- Enter 发送
end tell
```

### 3. 关闭窗口/弹窗

```applescript
tell application "System Events"
    key code 53                     -- ESC
end tell
```

### 4. 返回会话列表

```applescript
tell application "System Events"
    key code 13 using command down  -- Cmd+W 关闭当前窗口
end tell
```

## Python 封装

```python
import subprocess, time

KEY = {
    "f": 3, "v": 9, "c": 8, "a": 0, "w": 13,
    "return": 36, "tab": 48, "esc": 53,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "pgup": 116, "pgdn": 121, "space": 49, "delete": 51,
}

def osa_key(code: int, modifier: str = None):
    """通过 osascript key code 发送按键"""
    if modifier:
        cmd = f'tell app "System Events" to key code {code} using {modifier}'
    else:
        cmd = f'tell app "System Events" to key code {code}'
    subprocess.run(["osascript", "-e", cmd])
    time.sleep(0.2)

def osa_mod(key_name: str, mod: str):
    """osa_key(KEY[key_name], mod)"""
    osa_key(KEY[key_name], mod)

def activate_wechat():
    subprocess.run(["osascript", "-e", 'tell app "WeChat" to activate'])
    time.sleep(0.5)

def wechat_search(name: str):
    """在微信中搜索并打开指定联系人/群聊"""
    activate_wechat()
    osa_mod("f", "command down")    # Cmd+F
    time.sleep(0.5)
    subprocess.run(["pbcopy"], input=name.encode())
    osa_mod("v", "command down")    # Cmd+V
    time.sleep(0.5)
    osa_key(KEY["return"])          # Enter
    time.sleep(1)

def wechat_send(msg: str):
    """在当前聊天中发送消息"""
    subprocess.run(["pbcopy"], input=msg.encode())
    osa_mod("v", "command down")    # Cmd+V
    time.sleep(0.3)
    osa_key(KEY["return"])          # Enter

def wechat_esc():
    osa_key(KEY["esc"])

def wechat_close_window():
    osa_mod("w", "command down")    # Cmd+W
```

## 兼容性矩阵

| 操作 | cliclick | Quartz CGEvent | osascript keystroke | osascript key code |
|------|----------|---------------|---------------------|--------------------|
| 鼠标点击 | ✅ | — | ❌ (AX 不可用) | — |
| 键盘输入(ASCII) | — | ✅ (键盘事件) | ❌ (安全策略) | ✅ |
| 键盘组合键 | ✅ | ✅ | — | ✅ |
| 中文输入 | ❌ | ❌ | — | ❌ (用 pbcopy+Cmd+V) |
| 滚轮滚动 | ❌ (不支持) | ✅ | ❌ | — |
| 方向键 | ❌ (微信不响应) | — | ❌ | ✅ (arrow-*) |
| Page Up/Down | ❌ (微信不响应) | — | ❌ | ✅ |
| ESC | ✅ | ✅ | ❌ | ✅ |
| 权限需求 | Accessibility | 无 | 无 | 无 |

## 搜索框行为修正

v9.3 文档声明"不要用搜索框"——因为在手操时点击微信搜索框会默认进入"搜一搜"模式。

**v12 修正**: 通过 `Cmd+F` (key code 3 + command down) 可以正确触发微信的会话搜索功能。

```
鼠标点击搜索框  → "搜一搜"模式 → 公众号/视频号/文章 (不可用)
Cmd+F 快捷键    → 会话搜索模式 → 联系人/群聊名称 (✅ 可用)
```

## 排障

| 问题 | 原因 | 解决 |
|------|------|------|
| key code 不生效 | 微信窗口不在前台 | 先 `tell app "WeChat" to activate` + 等 0.5s |
| 窗口被遮挡 | IDE/浏览器盖住微信 | `open -a WeChat` 强制激活 |
| 中文输入乱码 | key code 不支持中文 | 用 `pbcopy` + Cmd+V 粘贴 |
| Cmd+F 无效 | WeChat 版本过旧 | 确认 WeChat 4.x+ |
| key code 触发登录提示 | 命中了微信的全局快捷键 | 不要用 key code 40 (= k, Cmd+K) |
