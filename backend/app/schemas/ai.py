"""Schemas for AI / Agent endpoints."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class AiChatRequest(BaseModel):
    input: str
    conversation_id: Optional[int] = None


class AgentApprovalRequest(BaseModel):
    approved: bool = False
    reason: str = ""


class AgentChatRequest(BaseModel):
    messages: list  # forwarded to Hermes; flexible shape
    stream: bool = True
    model: str = "hermes-agent"


class AgentSuggestionsRequest(BaseModel):
    """最近几轮对话，用于生成快捷追问按钮。"""
    messages: list  # [{role, content}, ...]；content 可以是字符串或多模态数组
