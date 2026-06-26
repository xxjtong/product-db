"""Schemas for AI / Agent endpoints."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class AiChatRequest(BaseModel):
    input: str
    conversation_id: Optional[str] = None


class AgentApprovalRequest(BaseModel):
    approved: bool = False
    reason: str = ""


class AgentChatRequest(BaseModel):
    messages: list  # forwarded to Hermes; flexible shape
    stream: bool = True
    model: str = "hermes-agent"
