"""Round 17 回归：DEV_MODE 的 systemd 护栏不能误伤 CI（R78 末尾发现）。

## 背景

`main.py` 里有一道安全护栏：`DEV_MODE=true` 在 systemd 下拒绝启动，除非 `FORCE_DEV_MODE=true`
——目的是防止有人在生产机上开着免登录的 DEV_MODE 跑服务。

但它判断的是 `INVOCATION_ID`，而 systemd 注入的这个变量是**继承**的：GitHub Actions 的
runner 自身就是个 systemd 服务，作业进程会带着它 → CI 被误判成生产机：
uvicorn 起不来、pytest 在 collect 阶段 `SystemExit`（报 `collected 0 items` + INTERNALERROR）。

后果是**仓库的 CI 从 ci.yml 建立（2026-06-01）起就一直红着**，直到 2026-09-22 才被发现。

所以这里把四种组合都钉住：CI 里放行，生产机（systemd、无 CI）照样拒绝。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

BASE_ENV = {
    "SECRET_KEY": "test-secret-key-for-pytest-32charmin",
    "DATABASE_URL": "sqlite:///:memory:",
    "DEV_MODE": "true",
}


def _import_main(**overrides) -> subprocess.CompletedProcess:
    """在子进程里 `import app.main`，返回结果（护栏在导入时就执行）。"""
    env = {k: v for k, v in os.environ.items() if k not in ("INVOCATION_ID", "FORCE_DEV_MODE", "CI")}
    env.update(BASE_ENV)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env, capture_output=True, text=True, errors="replace",
        cwd=str(BACKEND_DIR), timeout=60,
    )


class TestDevModeSystemdGuard:
    def test_refuses_under_systemd(self):
        """生产机场景：systemd（有 INVOCATION_ID）、没有 CI → 必须拒绝。"""
        proc = _import_main(INVOCATION_ID="abc123")
        assert proc.returncode != 0, "systemd 下 DEV_MODE 必须拒绝启动"
        assert "refused under systemd" in proc.stderr + proc.stdout

    def test_allows_in_ci(self):
        """CI 场景：GitHub runner 也有 INVOCATION_ID，但它设了 CI=true → 必须放行。

        这条就是本次修的那个 bug —— 修复前它会让 pytest 一个用例都收集不到。
        """
        proc = _import_main(INVOCATION_ID="abc123", CI="true")
        assert proc.returncode == 0, (
            f"CI 里不该被 systemd 护栏拦住\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )

    def test_allows_with_force_flag(self):
        """显式覆盖：FORCE_DEV_MODE=true 是文档里给出的逃生门，必须有效。"""
        proc = _import_main(INVOCATION_ID="abc123", FORCE_DEV_MODE="true")
        assert proc.returncode == 0

    def test_allows_without_systemd(self):
        """本机开发场景：没有 INVOCATION_ID → 放行。"""
        proc = _import_main()
        assert proc.returncode == 0

    def test_disabled_dev_mode_is_unaffected(self):
        """DEV_MODE=false（生产正常配置）时护栏根本不参与。"""
        proc = _import_main(DEV_MODE="false", INVOCATION_ID="abc123")
        assert proc.returncode == 0
