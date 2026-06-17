"""Human-in-the-loop approval manager for Hermes agent tool calls.

When Hermes calls a write-operation tool, the request is suspended via
asyncio.Event until a human approves/rejects through the frontend modal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 120  # Max wait for human approval


@dataclass
class ApprovalTask:
    """A suspended tool call waiting for human approval."""

    task_id: str
    tool_name: str
    tool_label: str      # Human-readable: "创建报价单"
    tool_input: dict     # The tool call arguments
    summary: str         # One-line summary: "为 岭南大学 创建报价单，总价¥636,301"
    details: dict        # Extra context for the modal card
    event: asyncio.Event = field(default_factory=asyncio.Event)
    result: Optional[dict] = field(default=None)  # {"approved": True/False, "reason": "..."}
    created_at: float = field(default_factory=lambda: __import__("time").time())


class ApprovalManager:
    """Singleton manager for pending approval tasks."""

    def __init__(self):
        self._tasks: dict[str, ApprovalTask] = {}
        self._lock = asyncio.Lock()

    def create(
        self,
        tool_name: str,
        tool_label: str,
        tool_input: dict,
        summary: str,
        details: Optional[dict] = None,
    ) -> ApprovalTask:
        """Create a new approval task and return it."""
        task_id = uuid.uuid4().hex[:12]
        task = ApprovalTask(
            task_id=task_id,
            tool_name=tool_name,
            tool_label=tool_label,
            tool_input=tool_input,
            summary=summary,
            details=details or {},
        )
        self._tasks[task_id] = task
        logger.info("ApprovalTask %s created: %s", task_id, summary)
        return task

    async def wait_for_decision(self, task_id: str) -> dict:
        """Wait for human decision on a task. Returns result dict."""
        task = self._tasks.get(task_id)
        if not task:
            return {"approved": False, "reason": "Task not found"}

        try:
            await asyncio.wait_for(task.event.wait(), timeout=TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning("ApprovalTask %s timed out", task_id)
            task.result = {"approved": False, "reason": "审批超时"}
        finally:
            self._tasks.pop(task_id, None)

        return task.result or {"approved": False, "reason": "No decision"}

    def decide(self, task_id: str, approved: bool, reason: str = "") -> bool:
        """Record human decision and wake the waiting coroutine."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.result = {"approved": approved, "reason": reason}
        task.event.set()
        logger.info("ApprovalTask %s: %s (reason: %s)", task_id, "approved" if approved else "rejected", reason)
        return True

    def get_pending(self) -> list[ApprovalTask]:
        """List all pending tasks (for status polling)."""
        return [t for t in self._tasks.values() if not t.event.is_set()]


# Global singleton
approval_manager = ApprovalManager()
