"""
One-shot migration: quote-system -> product-db
Usage: python migrate_quote_to_productdb.py [--dry-run]
"""
import sqlite3, json, sys

SRC = "/Users/tong/quote-system/quote.db"
DST = "/Users/tong/product-db/backend/product_db.db"
DRY_RUN = "--dry-run" in sys.argv


def main():
    src = sqlite3.connect(SRC)
    dst = sqlite3.connect(DST)
    src.row_factory = sqlite3.Row
    dst.row_factory = sqlite3.Row

    stats = {}

    # 1. Merge manufacturers (by name, add missing)
    src_mfgs_all = [dict(r) for r in src.execute("SELECT * FROM manufacturers")]
    src_mfgs = {r["name"]: r for r in src_mfgs_all}
    src_mfgs_by_id = {r["id"]: r for r in src_mfgs_all}
    dst_mfgs = {r["name"]: dict(r) for r in dst.execute("SELECT * FROM manufacturers")}
    mfg_new = 0
    for name, m in src_mfgs.items():
        if name not in dst_mfgs:
            if not DRY_RUN:
                dst.execute(
                    "INSERT INTO manufacturers (name, website, description) VALUES (?,?,?)",
                    (m["name"], m["website"] or "", m["description"] if "description" in m.keys() and m["description"] else ""),
                )
            mfg_new += 1
    stats["manufacturers"] = f"src={len(src_mfgs)} dst_before={len(dst_mfgs)} new={mfg_new}"

    # Refresh manufacturer map after insert
    dst_mfgs_by_id = {r["id"]: r for r in dst.execute("SELECT * FROM manufacturers")}
    dst_mfgs_by_name = {r["name"]: dict(r) for r in dst.execute("SELECT * FROM manufacturers")}
    if not DRY_RUN:
        dst.commit()

    # 2. Merge suppliers (by name)
    src_sups_all = [dict(r) for r in src.execute("SELECT * FROM suppliers")]
    src_sups = {r["name"]: r for r in src_sups_all}
    src_sups_by_id = {r["id"]: r for r in src_sups_all}
    dst_sups = {r["name"]: dict(r) for r in dst.execute("SELECT * FROM suppliers")}
    sup_new = 0
    for name, s in src_sups.items():
        if name not in dst_sups:
            if not DRY_RUN:
                dst.execute(
                    "INSERT INTO suppliers (name, contact_person, phone, email, website, notes) VALUES (?,?,?,?,?,?)",
                    (s["name"],
                     s["contact_person"] if "contact_person" in s.keys() and s["contact_person"] else "",
                     s["phone"] if "phone" in s.keys() and s["phone"] else "",
                     s["email"] if "email" in s.keys() and s["email"] else "",
                     s["website"] if "website" in s.keys() and s["website"] else "",
                     s["notes"] if "notes" in s.keys() and s["notes"] else ""),
                )
            sup_new += 1
    stats["suppliers"] = f"src={len(src_sups)} dst_before={len(dst_sups)} new={sup_new}"
    if not DRY_RUN:
        dst.commit()

    dst_sups_by_name = {r["name"]: dict(r) for r in dst.execute("SELECT * FROM suppliers")}

    # 3. Categories: quote-system categories -> product-db
    #    Use parent_id to keep hierarchy, add as top-level under a "Q导入" parent
    src_cats = {r["id"]: dict(r) for r in src.execute("SELECT * FROM device_categories")}
    dst_cats = {r["slug"]: dict(r) for r in dst.execute("SELECT * FROM device_categories")}
    dst_cats_by_name = {r["name"]: dict(r) for r in dst.execute("SELECT * FROM device_categories")}

    # Create a parent category for imported products
    import_parent_id = None
    for slug_prefix in ["imported", "q-import"]:
        existing = dst.execute("SELECT id FROM device_categories WHERE slug=?", (slug_prefix,)).fetchone()
        if existing:
            import_parent_id = existing["id"]
            break
    if not import_parent_id and not DRY_RUN:
        dst.execute(
            "INSERT INTO device_categories (name, slug, level, sort_order, is_active) VALUES (?,?,?,?,?)",
            ("Q导入", "q-import", 1, 99, 1),
        )
        dst.commit()
        import_parent_id = dst.execute("SELECT id FROM device_categories WHERE slug='q-import'").fetchone()["id"]
    elif DRY_RUN:
        import_parent_id = 999  # fake ID for dry run

    # Map old cat IDs -> new cat IDs
    cat_id_map = {}
    cat_new = 0
    for cid, cat in src_cats.items():
        # Try to find matching slug or name in product-db
        slug = (cat["slug"] if "slug" in cat.keys() and cat["slug"] else "").strip()
        if slug and slug in dst_cats:
            cat_id_map[cid] = dst_cats[slug]["id"]
        elif cat["name"] in dst_cats_by_name:
            cat_id_map[cid] = dst_cats_by_name[cat["name"]]["id"]
        else:
            if not DRY_RUN:
                new_slug = slug if slug else f"qcat-{cid}"
                # Ensure unique slug
                existing = dst.execute("SELECT id FROM device_categories WHERE slug=?", (new_slug,)).fetchone()
                if existing:
                    new_slug = f"{new_slug}-{cid}"
                dst.execute(
                    "INSERT INTO device_categories (parent_id, name, slug, level, sort_order, is_active) VALUES (?,?,?,?,?,?)",
                    (import_parent_id, cat["name"], new_slug, 1, cat["sort_order"] if "sort_order" in cat.keys() and cat["sort_order"] is not None else 0, 1),
                )
            cat_new += 1
            if not DRY_RUN:
                dst.commit()
                new_id = dst.execute("SELECT id FROM device_categories WHERE slug=?", (new_slug,)).fetchone()["id"]
                cat_id_map[cid] = new_id
            else:
                cat_id_map[cid] = 900 + cid
    stats["categories"] = f"src={len(src_cats)} mapped={len(src_cats)-cat_new} new={cat_new}"

    if not DRY_RUN:
        dst.commit()

    # 4. Import products
    # product-db needs: name, model, sku, category_id, manufacturer_id, supplier_id,
    #   unit, base_price, cost_price, description, image_url, product_url, status, parent_id,
    #   specs, urls, custom_fields, pinyin_search
    src_products = list(src.execute("SELECT * FROM products WHERE is_active=1"))
    dst_existing_names = {r["name"] for r in dst.execute("SELECT name FROM products")}
    products_imported = 0
    products_skipped = 0
    pid_map = {}  # old product_id -> new product_id

    for p in src_products:
        if p["name"] in dst_existing_names:
            products_skipped += 1
            continue

        # Resolve category: use product_categories M2M if available, else direct category_id
        cat_id = None
        m2m = src.execute("SELECT category_id FROM product_categories WHERE product_id=?", (p["id"],)).fetchall()
        if m2m:
            for mc in m2m:
                if mc["category_id"] in cat_id_map:
                    cat_id = cat_id_map[mc["category_id"]]
                    break
        if cat_id is None and p["category_id"] in cat_id_map:
            cat_id = cat_id_map[p["category_id"]]
        if cat_id is None:
            cat_id = import_parent_id  # fallback to "Q导入" parent

        # Resolve manufacturer (src_mfgs_by_id keyed by ID, look up by ID)
        mfg_id = p["manufacturer_id"]
        if mfg_id and mfg_id in src_mfgs_by_id:
            mfg_name = src_mfgs_by_id[mfg_id]["name"]
            mfg_id = dst_mfgs_by_name[mfg_name]["id"] if mfg_name in dst_mfgs_by_name else None

        # Resolve supplier (src_sups_by_id keyed by ID, look up by ID)
        sup_id = p["supplier_id"]
        if sup_id and sup_id in src_sups_by_id:
            sup_name = src_sups_by_id[sup_id]["name"]
            sup_id = dst_sups_by_name[sup_name]["id"] if sup_name in dst_sups_by_name else None

        # Parse specs/specs JSON
        specs = "{}"
        if p["specs"] and p["specs"].strip():
            try:
                json.loads(p["specs"])
                specs = p["specs"]
            except (json.JSONDecodeError, TypeError):
                specs = json.dumps({"value": p["specs"]}, ensure_ascii=False)

        urls = p["urls"] if p["urls"] and p["urls"].strip() else "{}"
        custom_fields = p["custom_fields"] if p["custom_fields"] and p["custom_fields"].strip() else "{}"
        desc_parts = []
        for f in ["function_desc", "remark"]:
            if f in p.keys() and p[f]:
                desc_parts.append(str(p[f]))
        description = "\n".join(desc_parts)

        if not DRY_RUN:
            cur = dst.execute(
                """INSERT INTO products (name, model, sku, category_id, manufacturer_id, supplier_id,
                   unit, base_price, cost_price, description, image_url, product_url, status, parent_id,
                   specs, urls, custom_fields, pinyin_search, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    p["name"], p["model"] or "", p["sku"] or "", cat_id, mfg_id, sup_id,
                    p["unit"] or "台", p["price"] or 0, p["cost_price"] or 0, description,
                    p["image_url"] or "", p["product_url"] or "", p["status"] or "active",
                    p["parent_id"], specs, urls, custom_fields, p["pinyin_search"] or "",
                    p["created_at"], p["updated_at"],
                ),
            )
            new_pid = cur.lastrowid
            pid_map[p["id"]] = new_pid
        products_imported += 1

    stats["products"] = f"src={len(src_products)} imported={products_imported} skipped={products_skipped}"

    if not DRY_RUN:
        dst.commit()

    # 5. Import mapping tables (dict IDs are identical between databases)
    mapping_tables = [
        ("product_comm_methods", ["product_id", "method_id", "details"], ["product_id"]),
        ("product_comm_protocols", ["product_id", "protocol_id", "direction"], ["product_id"]),
        ("product_power_supplies", ["product_id", "power_id", "voltage_range", "battery_life"], ["product_id"]),
        ("product_hardware_interfaces", ["product_id", "interface_name", "quantity", "description"], ["product_id"]),
        ("product_sensor_capabilities", ["product_id", "metric_id", "measure_range", "accuracy", "resolution"], ["product_id"]),
        ("product_images", ["product_id", "url", "is_primary", "sort_order", "alt_text"], ["product_id"]),
    ]

    map_stats = {}
    for table, columns, _id_cols in mapping_tables:
        rows = list(src.execute(f"SELECT * FROM {table}"))
        imported = 0
        for row in rows:
            old_pid = row["product_id"]
            if old_pid not in pid_map:
                continue
            new_pid = pid_map[old_pid]
            values = {}
            for col in columns:
                if col == "product_id":
                    values[col] = new_pid
                else:
                    values[col] = row[col] if col in row.keys() else None
            if not DRY_RUN:
                placeholders = ", ".join(values.keys())
                qs = ", ".join("?" * len(values))
                dst.execute(f"INSERT OR IGNORE INTO {table} ({placeholders}) VALUES ({qs})", list(values.values()))
            imported += 1
        map_stats[table] = f"src={len(rows)} imported={imported}"

    stats["mappings"] = map_stats

    if not DRY_RUN:
        dst.commit()

    # 6. Print results
    print("=" * 60)
    print("MIGRATION " + ("DRY RUN" if DRY_RUN else "EXECUTED"))
    print("=" * 60)
    for key, val in stats.items():
        if isinstance(val, dict):
            print(f"\n{key}:")
            for k, v in val.items():
                print(f"  {k}: {v}")
        else:
            print(f"{key}: {val}")

    src.close()
    dst.close()


if __name__ == "__main__":
    main()
