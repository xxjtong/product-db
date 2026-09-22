"""Round 9 回归：审批状态机收尾（R73）。

- `wait_for_decision` 不再用线程池阻塞等待 —— 取消后不留残留线程
- `create → decide → wait` 的竞态窗口不应傻等到超时
- `reaper_loop` 周期回收过期任务（原先只在 `create()` 时顺带做，没有定时器）
- `get_pending` 只列「未决策且未失效」的任务
"""
import asyncio
import threading
from contextlib import suppress

from app.services.approval_manager import (
    ApprovalManager, approval_manager, reaper_loop, STALE_SECONDS,
)
import app.services.approval_manager as am


def _mk(mgr, **kw):
    return mgr.create(tool_name="t", tool_label="创建报价单", tool_input={}, summary="s", **kw)


class TestWaitIsCancellable:
    def test_cancel_does_not_leave_blocking_thread(self, monkeypatch):
        """取消等待后不该多出线程。

        旧实现是 `run_in_executor(None, threading.Event.wait, TIMEOUT)` —— 协程被取消时
        那个线程仍在阻塞（ThreadPoolExecutor 无法取消已提交的任务），要等满超时才释放；
        高频断线时线程池会被占满（R68 审查发现）。这里给一个很大的超时值：若是旧实现，
        测试结束时那个线程还挂着。
        """
        monkeypatch.setattr(am, "TIMEOUT_SECONDS", 30)
        mgr = ApprovalManager()
        task = _mk(mgr)
        before = threading.active_count()

        async def run():
            t = asyncio.create_task(mgr.wait_for_decision(task.task_id))
            await asyncio.sleep(0.02)          # 让它进到等待里
            t.cancel()
            with suppress(asyncio.CancelledError):
                await t

        asyncio.run(run())

        assert threading.active_count() <= before, "取消等待不该留下阻塞线程"
        assert task.detached is True, "断开后仍要标记失效（接口据此回 409）"
        assert mgr.get(task.task_id) is not None, "任务不该被清掉（留给回收）"

    def test_decision_wakes_waiter(self, monkeypatch):
        monkeypatch.setattr(am, "TIMEOUT_SECONDS", 5)
        mgr = ApprovalManager()
        task = _mk(mgr)

        async def run():
            t = asyncio.create_task(mgr.wait_for_decision(task.task_id))
            await asyncio.sleep(0.02)
            assert mgr.decide(task.task_id, True, "ok") is True
            return await t

        assert asyncio.run(run()) == {"approved": True, "reason": "ok"}

    def test_decision_before_wait_returns_immediately(self, monkeypatch):
        """`create → decide → wait` 这个极短窗口不能傻等到超时。"""
        monkeypatch.setattr(am, "TIMEOUT_SECONDS", 30)
        mgr = ApprovalManager()
        task = _mk(mgr)
        mgr.decide(task.task_id, False, "提前拒绝")

        async def run():
            # 超过 1s 没返回就说明还在等，直接判失败
            return await asyncio.wait_for(mgr.wait_for_decision(task.task_id), timeout=1)

        result = asyncio.run(run())
        assert result == {"approved": False, "reason": "提前拒绝"}


class TestReaperLoop:
    def test_reaper_evicts_stale_in_background(self):
        t = approval_manager.create(tool_name="t", tool_label="x",
                                    tool_input={}, summary="过期任务")
        t.created_at -= STALE_SECONDS + 5
        try:
            async def run():
                loop_task = asyncio.create_task(reaper_loop(interval=0.05))
                await asyncio.sleep(0.3)
                loop_task.cancel()
                with suppress(asyncio.CancelledError):
                    await loop_task

            asyncio.run(run())
            assert approval_manager.get(t.task_id) is None, "过期任务应被后台回收"
        finally:
            approval_manager._tasks.pop(t.task_id, None)

    def test_reaper_survives_evict_exception(self, monkeypatch):
        """回收抛异常不能让循环退出（否则一次意外就永久失去回收）。"""
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            raise RuntimeError("boom")

        monkeypatch.setattr(approval_manager, "evict_stale", boom)

        async def run():
            loop_task = asyncio.create_task(reaper_loop(interval=0.05))
            await asyncio.sleep(0.25)
            loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await loop_task

        asyncio.run(run())
        assert calls["n"] >= 2, f"失败后应继续下一轮，实际只跑了 {calls['n']} 次"


class TestPendingList:
    def test_decided_task_is_not_pending(self):
        mgr = ApprovalManager()
        task = _mk(mgr, user_id=99991)
        assert [t.task_id for t in mgr.get_pending(user_id=99991)] == [task.task_id]

        mgr.decide(task.task_id, True, "")
        assert mgr.get_pending(user_id=99991) == [], "已决策的不该再列出来"

    def test_detached_task_is_not_pending(self):
        mgr = ApprovalManager()
        task = _mk(mgr, user_id=99992)
        task.detached = True
        assert mgr.get_pending(user_id=99992) == []
