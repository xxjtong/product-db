"""给 E2E（Playwright）造一份**最小且确定**的本地数据集。

为什么需要它：E2E 原先只能对着「从生产同步下来的库」跑，CI 里没有那个库 —— 于是
整套 E2E 一直进不了 CI（R78）。这个脚本把「跑 E2E 至少需要哪些行」固定下来。

配套：
    cd backend && venv/bin/alembic upgrade head && venv/bin/python seed_e2e.py
    cd frontend && npx playwright test api-health.spec.ts fixes.spec.ts

幂等：全部按业务标识查重，重复执行不会翻倍。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.dictionary import Manufacturer  # noqa: E402
from app.models.supplier import Supplier  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.solution import Solution, SolutionItem  # noqa: E402
from app.models.quotation import Quotation  # noqa: E402
from app.auth import hash_password  # noqa: E402

# E2E 的默认凭据（frontend/e2e/auth.ts 的 CRED 默认值）与 DEV_MODE 免登录用的都是这套
ADMIN = {"username": "admin", "password": "admin"}


def _category(db, name, slug, level=1, sort_order=0):
    cat = db.query(Category).filter_by(slug=slug).first()
    if cat:
        return cat
    cat = Category(name=name, slug=slug, level=level, sort_order=sort_order)
    db.add(cat)
    db.flush()
    return cat


def _manufacturer(db, name):
    m = db.query(Manufacturer).filter(Manufacturer.name == name).first()
    if m:
        return m
    m = Manufacturer(name=name)
    db.add(m)
    db.flush()
    return m


def _supplier(db, name):
    s = db.query(Supplier).filter(Supplier.name == name).first()
    if s:
        return s
    s = Supplier(name=name)
    db.add(s)
    db.flush()
    return s


def _product(db, **kw):
    p = db.query(Product).filter(Product.model == kw["model"]).first()
    if p:
        return p
    p = Product(**kw)
    db.add(p)
    db.flush()
    return p


def main() -> int:
    # 表由 Alembic 建；这里只在库是空的（还没跑迁移）时明确报错，避免造出半截 schema
    from sqlalchemy import inspect
    if not inspect(engine).has_table("users"):
        print("库还没有表：先跑 `venv/bin/alembic upgrade head`", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username=ADMIN["username"]).first()
        if not admin:
            admin = User(username=ADMIN["username"],
                         password_hash=hash_password(ADMIN["password"]),
                         role="admin")
            db.add(admin)
            db.flush()

        gateway = _category(db, "网关", "e2e-gateway")
        sensor = _category(db, "传感器", "e2e-sensor")
        _category(db, "室内传感器", "e2e-sensor-indoor", level=2, sort_order=0).parent_id = sensor.id
        mfg = _manufacturer(db, "E2E 示例厂商")
        sup = _supplier(db, "E2E 示例供应商")
        db.flush()

        # 描述里故意带 URL：技术方案/报价单的「功能描述」必须剥掉链接（core-flows 会断言）
        _product(
            db, name="E2E 示例网关", model="E2E-GW-001", sku="SKU-GW-001",
            category_id=gateway.id, manufacturer_id=mfg.id, supplier_id=sup.id,
            base_price=1200, cost_price=800, status="active",
            description="工业级 LoRaWAN 网关 https://example.com/gw?src=e2e",
            specs={"max_endpoints": 500, "防护等级": "IP67", "尺寸": "100×80×30mm"},
        )
        sen = _product(
            db, name="E2E 示例传感器", model="E2E-SEN-001", sku="SKU-SEN-001",
            category_id=sensor.id, manufacturer_id=mfg.id, supplier_id=sup.id,
            base_price=300, cost_price=180, status="active",
            description="温湿度传感器",
            specs={"防护等级": "IP65", "工作温度": "-20~60℃"},
        )
        db.flush()

        sol = db.query(Solution).filter(Solution.name == "E2E 示例方案").first()
        if not sol:
            sol = Solution(name="E2E 示例方案", client_name="E2E 客户",
                           project_name="E2E 项目", created_by=admin.id)
            db.add(sol)
            db.flush()
            db.add(SolutionItem(solution_id=sol.id, product_id=sen.id, quantity=4))
            db.add(SolutionItem(solution_id=sol.id, product_id=gateway.id, quantity=1))
            db.flush()

        # core-flows 会打开报价单页并核对「功能描述」列 —— 没有报价单就断言不到表格。
        # 走应用自己的服务建单（不手写行），报价单号/条目快照与线上口径一致
        qt = db.query(Quotation).filter(Quotation.title == "E2E 示例报价单").first()
        if not qt:
            from app.services.quotation_service import create_quotation_from_solution
            create_quotation_from_solution(db, sol, admin, title="E2E 示例报价单",
                                           client_name="E2E 客户")
            db.flush()

        db.commit()
    finally:
        db.close()

    print("E2E 种子数据就绪（admin/admin、3 个品类、1 厂商、1 供应商、2 产品、1 方案、1 报价单）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
