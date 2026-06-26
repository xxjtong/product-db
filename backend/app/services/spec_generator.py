"""Spec sheet HTML generator for product spec sheets."""
from __future__ import annotations
import html
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.category import Category, CategorySpecDefinition
from app.models.dictionary import Manufacturer


def build_spec_html(p: Product, db: Session) -> str:
    """Build complete HTML for product spec sheet.

    Includes product image, comm methods, protocols, power supplies,
    hardware interfaces, sensor capabilities, spec groups, and unmatched specs.
    """
    spec_defs = db.query(CategorySpecDefinition).filter_by(category_id=p.category_id)\
        .order_by(CategorySpecDefinition.sort_order).all()

    groups: dict = {}
    for sd in spec_defs:
        g = sd.display_group or "基本参数"
        if g not in groups:
            groups[g] = []
        groups[g].append(sd)

    defined_keys = {sd.spec_key for sd in spec_defs}
    unmatched = {k: v for k, v in (p.specs or {}).items() if k not in defined_keys}

    # Product image HTML
    img_html = ""
    primary_img = next((img for img in p.images if img.is_primary), None)
    if primary_img:
        img_url = primary_img.url
        if img_url.startswith("http://") or img_url.startswith("https://"):
            pass  # use as-is
        else:
            img_url = ""  # skip local/non-http images for security
        img_html = f'<img src="{html.escape(str(img_url), quote=True)}" class="product-img" />' if img_url else ''

    # Comm methods
    comm_rows = ""
    for cm in p.comm_methods:
        if cm.method:
            mtype = "有线" if cm.method.method_type == "wired" else "无线"
            comm_rows += f"<tr><td>{html.escape(mtype)}</td><td>{html.escape(str(cm.method.name))}</td><td>{html.escape(str(cm.details or '—'))}</td></tr>"

    # Protocols
    proto_rows = ""
    for cp in p.comm_protocols:
        if cp.protocol:
            proto_rows += f"<tr><td>{html.escape(str(cp.protocol.name))}</td><td>{'双向' if cp.direction == 'both' else '采集' if cp.direction == 'acquisition' else '转发'}</td></tr>"

    # Power
    power_rows = ""
    for ps in p.power_supplies:
        if ps.power:
            power_rows += f"<tr><td>{html.escape(str(ps.power.name))}</td><td>{html.escape(str(ps.voltage_range or '—'))}</td><td>{html.escape(str(ps.battery_life or '—'))}</td></tr>"

    # Hardware interfaces
    iface_rows = ""
    for hi in p.hardware_interfaces:
        iface_rows += f"<tr><td>{html.escape(str(hi.interface_name))}</td><td>×{hi.quantity}</td><td>{html.escape(str(hi.description or '—'))}</td></tr>"

    # Sensor capabilities
    sensor_rows = ""
    for sc in p.sensor_capabilities:
        if sc.metric:
            sensor_rows += f"<tr><td>{html.escape(str(sc.metric.name))} ({html.escape(str(sc.metric.unit or ''))})</td><td>{html.escape(str(sc.measure_range or '—'))}</td><td>{html.escape(str(sc.accuracy or '—'))}</td><td>{html.escape(str(sc.resolution or '—'))}</td></tr>"

    # Spec groups
    spec_group_html = ""
    for group_name, items in groups.items():
        rows = ""
        for sd in items:
            val = (p.specs or {}).get(sd.spec_key)
            if val is None:
                val_str = "—"
            elif sd.spec_type == "boolean":
                val_str = "✓" if val else "—"
            else:
                val_str = str(val)
                if sd.unit:
                    val_str += f" {sd.unit}"
            rows += f"<tr><td>{html.escape(sd.display_name)}</td><td>{html.escape(val_str)}</td></tr>"
        spec_group_html += f"""<h2>{html.escape(group_name)}</h2>
<table>{rows}</table>"""

    unmatched_rows = ""
    if unmatched:
        for k, v in unmatched.items():
            unmatched_rows += f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"

    desc_html = f"<h2>描述</h2><p>{html.escape(str(p.description))}</p>" if p.description else ""
    base_info = f"<p>{html.escape(str(p.manufacturer.name if p.manufacturer else ''))}  |  {html.escape(str(p.category.name if p.category else ''))}  |  型号: {html.escape(str(p.model or '—'))}</p>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>{html.escape(str(p.name))} - 规格书</title>
<style>
@page {{ size: A4; margin: 20mm 18mm; @bottom-center {{ content: "第 " counter(page) " 页"; font-size: 9px; color: #94a3b8; }} }}
body {{ font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei", sans-serif; font-size: 12px; color: #1e293b; line-height: 1.6; }}
.header {{ border-bottom: 3px solid #0f3460; padding-bottom: 12px; margin-bottom: 20px; }}
.header h1 {{ font-size: 22px; margin: 0 0 4px; color: #0f3460; }}
.header p {{ font-size: 12px; color: #64748b; margin: 2px 0; }}
h2 {{ font-size: 14px; color: #0f3460; margin: 20px 0 8px; padding: 4px 0 4px 10px; border-left: 4px solid #0f3460; background: #f8fafc; page-break-after: avoid; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 11px; page-break-inside: avoid; }}
th {{ background: #f1f5f9; padding: 6px 10px; text-align: left; font-weight: 600; border-bottom: 2px solid #cbd5e1; }}
td {{ padding: 5px 10px; border-bottom: 1px solid #e2e8f0; }}
td:first-child {{ color: #475569; width: 160px; }}
.badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; margin: 1px 2px; background: #f1f5f9; border: 1px solid #e2e8f0; }}
.product-img {{ max-width: 120px; max-height: 120px; float: right; border-radius: 6px; border: 1px solid #e2e8f0; margin-left: 16px; }}
.footer {{ margin-top: 24px; padding-top: 12px; border-top: 1px solid #e2e8f0; font-size: 10px; color: #94a3b8; text-align: center; }}
</style></head>
<body>
<div class="header">
  {img_html}
  <h1>{html.escape(str(p.name))}</h1>
  {base_info}
</div>
<h2>通讯方式</h2>
<table><tr><th>类型</th><th>方式</th><th>详情</th></tr>{comm_rows or '<tr><td colspan="3">—</td></tr>'}</table>

<h2>通讯协议</h2>
<table><tr><th>协议</th><th>方向</th></tr>{proto_rows or '<tr><td colspan="2">—</td></tr>'}</table>

<h2>供电方式</h2>
<table><tr><th>方式</th><th>电压/规格</th><th>续航</th></tr>{power_rows or '<tr><td colspan="3">—</td></tr>'}</table>

{"<h2>硬件接口</h2><table><tr><th>接口</th><th>数量</th><th>描述</th></tr>" + iface_rows + "</table>" if iface_rows else ""}

{"<h2>传感能力</h2><table><tr><th>指标</th><th>量程</th><th>精度</th><th>分辨率</th></tr>" + sensor_rows + "</table>" if sensor_rows else ""}

{spec_group_html}

{"<h2>其他参数</h2><table>" + unmatched_rows + "</table>" if unmatched_rows else ""}

{desc_html}

<div class="footer">© 产品数据库 — 生成于 {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")}</div>
</body></html>"""
