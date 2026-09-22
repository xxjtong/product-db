"""Round 16 回归：备份保留策略必须按**名字**排快照，不能按 mtime（R78 顺带修）。

## 为什么这条值得单独测

`rsync -a` 含 `-t`，会把**源目录的 mtime** 盖到目标快照目录上 —— 同一源目录下建出来的
uploads 快照，mtime 全是同一个值。于是 `ls -1t`（旧实现）排出来是乱序，保留策略会删掉
**刚建好的那份**、留下旧的，而「份数」检查照样显示正常，从日志上看不出来。

2026-09-22 实测（KEEP=3 连跑三次）：
    快照完成: 20260922_185709
      清理旧 uploads 快照 20260922_185709     ← 自己把自己删了
    份数: 3  保留上限: 3                      ← 数目对，内容错

这会直接摧毁 uploads 快照的意义（它的用途正是「误删后从历史快照捞回」）。
db 快照是文件、mtime 属自己，但也一并改成名字排序保持一致。

## 测试方式
直接跑真实的 `deploy/backup-db.sh`（临时目录 + OFFSITE_ENABLED=0），
不 mock —— 排序这件事只有真跑才能验出来。
"""
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "deploy" / "backup-db.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("sqlite3") is None or shutil.which("bash") is None or not SCRIPT.exists(),
    reason="需要 sqlite3 + bash + deploy/backup-db.sh",
)


def _make_db(path: Path) -> None:
    """造一个能过行数哨兵（products / users >= 1）的最小库。"""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE products (id INTEGER PRIMARY KEY);
        CREATE TABLE users (id INTEGER PRIMARY KEY);
        CREATE TABLE ai_conversations (id INTEGER PRIMARY KEY);
        INSERT INTO products (id) VALUES (1);
        INSERT INTO users (id) VALUES (1);
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def env(tmp_path):
    home = tmp_path / "work"
    (home / "uploads").mkdir(parents=True)
    (home / "uploads" / "a.txt").write_text("file-a")
    db = home / "product_db.db"
    _make_db(db)
    return {
        "DB_PATH": str(db),
        "BACKUP_DIR": str(home / "backups" / "db"),
        "UPLOADS_PATH": str(home / "uploads"),
        "UPLOADS_BACKUP_DIR": str(home / "backups" / "uploads-snapshots"),
        "OFFSITE_ENABLED": "0",          # 测试不联网
        "HOME": str(tmp_path),           # 防脚本万一读到 $HOME
    }, home


def _run_bash(env: dict, keep: int) -> subprocess.CompletedProcess:
    """跑脚本。

    `errors="replace"` 不能省：脚本被打断时 stderr 里可能留下半个多字节字符
    （例如 `$VAR（` 那种写法会让 bash 把全角括号的**首字节**当成变量名的一部分），
    默认的严格解码会在这里抛 UnicodeDecodeError，把「脚本输出不对」变成
    「测试自己崩了」，反而看不出问题。
    """
    return subprocess.run(
        ["bash", str(SCRIPT), str(keep)],
        env={**os.environ, **env},
        capture_output=True, text=True, errors="replace", timeout=60,
    )


def _run(env, keep: int) -> subprocess.CompletedProcess:
    proc = _run_bash(env, keep)
    assert proc.returncode == 0, (
        f"脚本退出码 {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    return proc


def _names(root: Path, pattern: str = "*"):
    return sorted(p.name for p in root.glob(pattern))


class TestRetentionOrdering:
    def test_newest_uploads_snapshot_survives_pruning(self, env):
        """KEEP=3 建三份 t1<t2<t3 → 再用 KEEP=2 跑一次。

        注意这**最后一次运行本身也会生成一份 t4**，所以正确结果是留下 {t3, t4}：
        t1、t2 被清掉，t3 保留，且本次新建的 t4 一定在。

        旧实现（`ls -1t`，快照目录的 mtime 被 rsync 盖成源目录那一个值）排序是乱序，
        可能把 **t4 自己删掉**而留下 t2、t3 —— 下面的 `created[1] not in survivors`
        就是专门抓这个的（那种情况下 t2 会残留在 survivors 里）。
        """
        e, home = env
        up_dest = Path(e["UPLOADS_BACKUP_DIR"])

        created = []
        for _ in range(3):
            _run(e, keep=3)
            # KEEP=3 时不会触发清理，当前最大名字就是本次刚建的那份
            created.append(max(_names(up_dest, "*")))
            time.sleep(1.2)   # 快照名精确到秒，必须跨秒，否则名字会撞上

        assert len(set(created)) == 3, f"三次快照名应互不相同，实际 {created}"
        t1, t2, t3 = sorted(created)

        _run(e, keep=2)

        survivors = _names(up_dest, "*")
        assert len(survivors) == 2, f"应只剩 2 份，实际 {survivors}"
        assert t1 not in survivors, "最旧的一份应被清掉"
        assert t2 not in survivors, "第二旧的一份也应被清掉"
        assert t3 in survivors, "第三份必须保留"
        assert max(survivors) > t3, "本次新建的那份必须留下（旧实现可能把它自己删掉）"

    def test_newest_db_snapshot_survives_pruning(self, env):
        e, home = env
        db_dest = Path(e["BACKUP_DIR"])

        created = []
        for _ in range(3):
            _run(e, keep=3)
            created.append(max(_names(db_dest, "product_db.db.bak.*")))
            time.sleep(1.2)

        t1, t2, t3 = sorted(created)
        _run(e, keep=2)

        survivors = _names(db_dest, "product_db.db.bak.*")
        assert len(survivors) == 2, f"应只剩 2 份，实际 {survivors}"
        assert t1 not in survivors and t2 not in survivors
        assert t3 in survivors and max(survivors) > t3

    def test_uploads_snapshot_is_complete_after_link_dest(self, env):
        """硬链接快照必须是**完整镜像**（每份都能独立恢复），不是增量。"""
        e, home = env
        for _ in range(2):
            _run(e, keep=3)
            time.sleep(1.2)

        up_dest = Path(e["UPLOADS_BACKUP_DIR"])
        for snap in up_dest.iterdir():
            assert (snap / "a.txt").read_text() == "file-a", f"{snap.name} 不是完整镜像"


class TestErrorPaths:
    """错误分支也要能打出**那句该打的话**。

    这些行的中文提示后面紧跟全角括号，写成 `$VAR（` 时 bash 会把括号当成变量名的一部分
    → `set -u` 下直接 `unbound variable` 退出，真正的原因再也看不到（L153 曾是这样：
    文档里写的「OFFSITE_ENABLED=0 临时关闭异地」这条路一走就炸）。统一用 `${VAR}` 修掉。
    """

    def test_offsite_disabled_is_a_clean_skip(self, env):
        e, home = env
        proc = _run(e, keep=3)          # env 里就是 OFFSITE_ENABLED=0
        # unbound variable 这类是打到 stderr 的，日志文件里看不到 —— 两处都要查
        assert "unbound variable" not in proc.stderr
        log = (Path(e["BACKUP_DIR"]) / "backup.log").read_text(encoding="utf-8")
        assert "跳过异地副本（OFFSITE_ENABLED=0）" in log
        assert "完成（本地 OK，异地 OK）" in log   # 关闭异地不算失败

    def test_unreachable_offsite_keeps_local_snapshot_and_logs_reason(self, env):
        e, home = env
        e = {**e, "OFFSITE_ENABLED": "1",
             "OFFSITE_HOST": "127.0.0.1", "OFFSITE_PORT": "9",   # discard 端口，立刻拒绝
             "OFFSITE_USER": "nobody", "OFFSITE_DIR": "/tmp/never"}

        proc = _run_bash(e, 3)
        # 异地失败 → 非 0，但**本地快照必须还在**
        assert proc.returncode != 0, "异地失败应当以非 0 退出"
        assert _names(Path(e["BACKUP_DIR"]), "product_db.db.bak.*"), "本地 db 快照不得因异地失败而丢失"
        assert _names(Path(e["UPLOADS_BACKUP_DIR"]), "*"), "本地 uploads 快照不得因异地失败而丢失"

        log = (Path(e["BACKUP_DIR"]) / "backup.log").read_text(encoding="utf-8")
        assert "连不上" in log, f"日志里应说明连不上异地，实际:\n{log[-500:]}"
        assert "unbound variable" not in proc.stderr, "错误分支不该因变量名写法而自己炸掉"
