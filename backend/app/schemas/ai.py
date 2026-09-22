"""Schemas for AI / Agent endpoints."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class AiChatRequest(BaseModel):
    input: str
    conversation_id: Optional[int] = None
    # 入口来源，仅用于用量统计：floating（全局浮窗）/ solution（方案详情页助手）
    source: str = ""
    # 方案上下文。带上**且有权限**时才会把写工具（create_quotation）交给模型；
    # 否则模型只能凭空猜一个 solution_id 去建单（见 R71）。
    solution_id: Optional[int] = None


class AgentApprovalRequest(BaseModel):
    approved: bool = False
    reason: str = ""


class AgentChatRequest(BaseModel):
    # 只收正常对话轮次：system 由服务端注入、model 由服务端固定（R60），不从这里传
    # stream 也不收（R64）：这个端点的契约就是 SSE 透传，固定 True。
    # 客户端多传的字段会被 pydantic 忽略（extra 默认 ignore），不会 422。
    messages: list


class AgentStopRequest(BaseModel):
    """客户端「主动停止」的带外信号，stream_id 与 /agent/chat 的 X-Stream-Id 一致。"""
    stream_id: str = ""


class AgentSuggestionsRequest(BaseModel):
    """最近几轮对话，用于生成快捷追问按钮。"""
    messages: list  # [{role, content}, ...]；content 可以是字符串或多模态数组
