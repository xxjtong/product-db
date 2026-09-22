"""Human-in-the-loop approval manager for Hermes agent tool calls.

When Hermes calls a write-operation tool, the request is suspended via
asyncio.Event until a human approves/rejects through the frontend modal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 120  # Max wait for human approval
# 没有等待者的任务由 create() 顺带回收（见 wait_for_decision 的取消分支）
STALE_SECONDS = TIMEOUT_SECONDS * 2


@dataclass
class ApprovalTask:
    """A suspended tool call waiting for human approval."""

    task_id: str
    tool_name: str
    tool_label: str      # Human-readable: "创建报价单"
    tool_input: dict     # The tool call arguments
    summary: str         # One-line summary: "为 岭南大学 创建报价单，总价¥636,301"
    details: dict        # Extra context for the modal card
    user_id: int = None  # User who triggered the tool call (approval owner)
    event: threading.Event = field(default_factory=threading.Event)
    result: Optional[dict] = field(default=None)  # {"approved": True/False, "reason": "..."}
    created_at: float = field(default_factory=time.time)
    # 等待者已经消失（客户端断开）：此时再决策没有任何意义 —— 决策结果的唯一用途
    # 是唤醒那个正在等它的协程，而它已经没了。标出来，让接口明确拒绝而不是假装成功。
    detached: bool = False


class ApprovalManager:
    """Singleton manager for pending approval tasks."""

    def __init__(self):
        self._tasks: dict[str, ApprovalTask] = {}

    def create(
        self,
        tool_name: str,
        tool_label: str,
        tool_input: dict,
        summary: str,
        details: Optional[dict] = None,
        user_id: int = None,
    ) -> ApprovalTask:
        """Create a new approval task and return it."""
        self._evict_stale()
        task_id = uuid.uuid4().hex[:12]
        task = ApprovalTask(
            task_id=task_id,
            tool_name=tool_name,
            tool_label=tool_label,
            tool_input=tool_input,
            summary=summary,
            details=details or {},
            user_id=user_id,
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
            loop = asyncio.get_running_loop()
            decided = await loop.run_in_executor(None, task.event.wait, TIMEOUT_SECONDS)
            if not decided:
                logger.warning("ApprovalTask %s timed out", task_id)
                task.result = {"approved": False, "reason": "审批超时"}
        except asyncio.CancelledError:
            # 客户端断开（点「停止」/关页面/断网）时这里被取消。**不要把任务清掉**：
            # 清了之后界面上这条待审批就凭空消失，用户再点「授权执行」会拿到 404
            # （2026-09 线上实测，POST /agent/approval/{id} → 404）。
            # 但也不能让它继续可决策：等待者已经没了，决策无处送达（R64 起标 detached，
            # 接口会明确回 409 而不是假装成功）。撤销的任务留给 _evict_stale 回收。
            task.detached = True
            logger.warning("ApprovalTask %s 等待被取消（客户端断开），任务已标记失效待回收", task_id)
            raise
        else:
            self._tasks.pop(task_id, None)

        return task.result or {"approved": False, "reason": "No decision"}

    def _evict_stale(self) -> None:
        """回收长时间没人处理的任务。

        正常路径由 wait_for_decision 在拿走结果时删除；但客户端断开后任务会留在
        队列里（见上面的取消分支），于是需要这个兜底 —— 否则排队列表只增不减。
        """
        cutoff = time.time() - STALE_SECONDS
        stale = [tid for tid, t in self._tasks.items() if t.created_at < cutoff]
        for tid in stale:
            self._tasks.pop(tid, None)
            logger.warning("ApprovalTask %s 超过 %ds 无人处理，已回收", tid, STALE_SECONDS)

    def decide(self, task_id: str, approved: bool, reason: str = "") -> bool:
        """Record human decision and wake the waiting coroutine."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.result = {"approved": approved, "reason": reason}
        task.event.set()
        logger.info("ApprovalTask %s: %s (reason: %s)", task_id, "approved" if approved else "rejected", reason)
        return True

    def get_pending(self, user_id: Optional[int] = None) -> list[ApprovalTask]:
        """List pending tasks (for status polling).

        传 user_id 时只返回该用户的任务 —— 普通用户不应看到他人的待审批内容
        （task.tool_input 里含业务明细），管理员传 None 看全部（R55）。
        已失效（detached，等待者已断开）的不列出来：它们点不动了，列出来只会误导。
        """
        tasks = [t for t in self._tasks.values() if not t.event.is_set() and not t.detached]
        if user_id is not None:
            tasks = [t for t in tasks if t.user_id == user_id]
        return tasks

    def get(self, task_id: str) -> Optional[ApprovalTask]:
        """Get a task by id (without removing it)."""
        return self._tasks.get(task_id)


# Global singleton
approval_manager = ApprovalManager()
