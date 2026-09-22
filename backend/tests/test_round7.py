"""Round 7 回归：`/categories/tree` 的可见域与 `/categories` 对齐。

此前树不过归属过滤，非 admin 能在树里看到别人创建的品类，而列表接口看不到 ——
产品列表的品类筛选器读的正是这棵树（`fetchCategoryTree`），同一个页面两套口径。
"""
import os
import tempfile

_test_db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["DEV_MODE"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-32charmin"

from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models.user import User
from app.models.category import Category
from app.auth import hash_password, create_token
from tests.conftest import create_test_schema, drop_test_schema

client = TestClient(app)
API = "/product-db/api"


def _seed_users():
    create_test_schema()
    db = SessionLocal()
    if not db.query(User).filter_by(username="admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))
    for name in ("u1", "u2"):
        if not db.query(User).filter_by(username=name).first():
            db.add(User(username=name, password_hash=hash_password("password1"), role="user"))
    db.commit()
    ids = {u.username: u.id for u in db.query(User).all()}
    db.close()
    return ids


def _headers(username: str):
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(username=username).first()
        return {"Authorization": f"Bearer {create_token(u.id, u.username)}"}
    finally:
        db.close()


def _seed_category(name, *, owner_id, parent_id=None, sort_order=0):
    db = SessionLocal()
    try:
        c = Category(name=name, slug=name.lower().replace(" ", "-"),
                     parent_id=parent_id, level=1, sort_order=sort_order,
                     created_by=owner_id)
        db.add(c)
        db.commit()
        db.refresh(c)
        return c.id
    finally:
        db.close()


def _tree_names(nodes):
    """收集树里所有节点名（含子层级）。"""
    out = []
    for n in nodes:
        out.append(n["name"])
        out.extend(_tree_names(n.get("children") or []))
    return out


def _root_names(nodes):
    return [n["name"] for n in nodes]


class TestCategoryTreeVisibility:
    def setup_method(self):
        self.ids = _seed_users()

    def teardown_method(self):
        drop_test_schema()

    def test_normal_user_does_not_see_others_categories(self):
        _seed_category("admin建的", owner_id=self.ids["admin"])
        _seed_category("u1建的", owner_id=self.ids["u1"])
        _seed_category("u2建的", owner_id=self.ids["u2"])

        resp = client.get(f"{API}/categories/tree", headers=_headers("u1"))
        assert resp.status_code == 200
        names = _tree_names(resp.json()["tree"])
        assert "u1建的" in names
        assert "admin建的" in names, "admin 创建的品类对普通用户可见（与 filter_by_ownership 一致）"
        assert "u2建的" not in names, "不得看到其他普通用户创建的品类"

    def test_normal_user_list_and_tree_have_same_scope(self):
        """同一个页面里两套口径是最初的问题：列表与树的可见集合必须一致。"""
        _seed_category("admin建的", owner_id=self.ids["admin"])
        _seed_category("u1建的", owner_id=self.ids["u1"])
        _seed_category("u2建的", owner_id=self.ids["u2"])

        headers = _headers("u1")
        listed = {c["name"] for c in
                  client.get(f"{API}/categories", headers=headers).json()["categories"]}
        in_tree = set(_tree_names(client.get(f"{API}/categories/tree", headers=headers).json()["tree"]))
        assert in_tree == listed, f"树 {in_tree} 与列表 {listed} 可见域不一致"

    def test_admin_sees_everything(self):
        _seed_category("admin建的", owner_id=self.ids["admin"])
        _seed_category("u1建的", owner_id=self.ids["u1"])
        _seed_category("u2建的", owner_id=self.ids["u2"])

        resp = client.get(f"{API}/categories/tree", headers=_headers("admin"))
        names = _tree_names(resp.json()["tree"])
        assert {"admin建的", "u1建的", "u2建的"} <= set(names)

    def test_orphan_child_is_promoted_when_parent_hidden(self):
        """父不可见时子节点要提升为根级 —— 否则它接不上任何根，会连着子树一起消失。"""
        parent = _seed_category("u2的父品类", owner_id=self.ids["u2"])
        _seed_category("u1的子品类", owner_id=self.ids["u1"], parent_id=parent)

        resp = client.get(f"{API}/categories/tree", headers=_headers("u1"))
        tree = resp.json()["tree"]
        assert "u2的父品类" not in _tree_names(tree)
        assert "u1的子品类" in _root_names(tree), "父不可见时子节点应提升为根级"

    def test_visible_hierarchy_is_preserved(self):
        """父子都可见时层级不能被提升逻辑打乱。"""
        parent = _seed_category("u1的父", owner_id=self.ids["u1"])
        _seed_category("u1的子", owner_id=self.ids["u1"], parent_id=parent)

        tree = client.get(f"{API}/categories/tree", headers=_headers("u1")).json()["tree"]
        roots = {n["name"]: n for n in tree}
        assert "u1的父" in roots
        assert "u1的子" not in roots, "父可见时子节点不该出现在根级"
        assert [c["name"] for c in roots["u1的父"]["children"]] == ["u1的子"]

    def test_deep_orphan_subtree_keeps_its_children(self):
        """孤儿提升要把整棵子树一起带出来，不能只剩节点本身。"""
        grand = _seed_category("u2的祖父", owner_id=self.ids["u2"])
        parent = _seed_category("u2的父", owner_id=self.ids["u2"], parent_id=grand)
        mid = _seed_category("u1的中", owner_id=self.ids["u1"], parent_id=parent)
        _seed_category("u1的叶", owner_id=self.ids["u1"], parent_id=mid)

        tree = client.get(f"{API}/categories/tree", headers=_headers("u1")).json()["tree"]
        roots = {n["name"]: n for n in tree}
        assert "u1的中" in roots
        assert [c["name"] for c in roots["u1的中"]["children"]] == ["u1的叶"]
