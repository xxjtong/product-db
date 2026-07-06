---
name: wechat-weekly-summary
description: "Scan WeChat conversations from the past week, extract chat content from non-personal conversations (group chats, work-related), and generate a structured Markdown weekly report. Use when the user asks to scan WeChat messages, generate a weekly summary, or review recent chat activity."
---

# WeChat Weekly Summary

## Purpose

Automatically scan WeChat on macOS to:
1. Open WeChat, find conversations active this week
2. Read message content from each conversation (screenshot + OCR/VLM)
3. Generate a structured Markdown weekly report

## How It Works (High-Level)

```
Phase 1: Navigate conversation list to this week's section
   ↓
Phase 2: Per screen → VLM recognizes conversations → filter by date
   ↓         For each: click → enter chat → scroll up read history → OCR → go back
   ↓
Phase 3: Generate Markdown report with session summaries
```

## Key Technical Insight: osascript `key code`

WeChat on macOS **does not expose internal UI to Accessibility API**. This breaks many automation approaches:

| Approach | Status | Why |
|----------|--------|-----|
| `cliclick kp:arrow-down` | ❌ Dead | WeChat ignores cliclick keyboard events |
| `cliclick kp:page-up` | ❌ Dead | Same |
| `osascript keystroke` | ❌ Blocked | macOS security: "不允许发送按键" |
| Quartz CGEvent scroll | ✅ Works | Mouse wheel simulation |
| **`osascript key code`** | ✅ **Works** | Hardware key codes bypass keystroke restriction |

See `references/osascript-keycode-automation.md` for the full key code mapping and Python wrappers.

## Prerequisites

- **macOS only** — uses `screencapture`, `cliclick`, Quartz CGEvent, AppleScript
- `cliclick`: `brew install cliclick`
- Volcengine/Doubao API key for VLM vision (or MiMo as fallback)
- WeChat must be installed and logged in
- The main scanning script (`scan_wechat_v10.py` or later) must be accessible

## Quick Start

```bash
# Scan last week (default)
python3 scripts/scan_wechat_v10.py

# Scan specific date range
python3 scripts/scan_wechat_v10.py --start-date 2026-06-16 --end-date 2026-06-22

# Scan with output path
python3 scripts/scan_wechat_v10.py --output ~/Desktop/weekly_report.md
```

## Script Architecture

| Script | Purpose |
|--------|---------|
| `scan_wechat_v10.py` | Main scanner: VLM list recognition + OCR chat reading |
| `scan_wechat_v11.py` | Dual-model VLM (Doubao/MiMo) + title retry + cumulative dates |
| `scripts/keycode_utils.py` | **v12** osascript key code wrappers (ESC, arrows, pgup/pgdn, Cmd+F) |
| `build_ocr.swift` | Swift Vision OCR tool source |
| `ocr_tool` | Compiled OCR binary for local text extraction |

## Key Code Utilities (v12)

The `scripts/keycode_utils.py` module provides clean Python wrappers for osascript key code operations, replacing broken cliclick keyboard commands:

```python
from keycode_utils import osa_key, wechat_esc, wechat_arrow

wechat_esc()                          # ESC (key code 53)
osa_key(126)                          # Arrow up
osa_key(125)                          # Arrow down
osa_key(116)                          # Page up
osa_key(121)                          # Page down
osa_key(3, "command down")            # Cmd+F (session search)
osa_key(9, "command down")            # Cmd+V (paste)
```

## Output Format

```markdown
# 微信聊天记录汇总报告
**扫描时间范围**: YYYY年MM月DD日 ~ MM月DD日

## 执行摘要
| 指标 | 数值 |
|------|------|
| 扫描会话总数 | XX 个 |
| 威发相关会话 | XX 个 |

## 威发相关会话
### [群聊名称]
**最后活跃**: MM月DD日
**聊天内容摘录**：
...

## 个人会话
### [联系人名称]
...
```

## File Reference

| File | Purpose |
|------|---------|
| `SKILL.md` | This file |
| `references/osascript-keycode-automation.md` | Complete osascript key code guide (mapping, wrappers, troubleshooting) |
| `scripts/keycode_utils.py` | Reusable key code Python module |
| `scripts/scan_wechat_v10.py` | Main scanning script (copy from Hermes skill) |
