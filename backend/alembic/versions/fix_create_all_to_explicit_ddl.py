"""Replace create_all/drop_all with explicit DDL.

Revision ID: fix_explicit_ddl
Revises: 7db0c6d785b3
Create Date: 2026-06-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fix_explicit_ddl'
down_revision: Union[str, None] = '7db0c6d785b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop all tables (respecting FK deps), then recreate with explicit DDL."""

    # ── DROP in reverse-dependency order ──────────────────────────────────
    op.drop_table("download_logs")
    op.drop_table("download_tickets")
    op.drop_table("login_logs")
    op.drop_table("ai_usage_logs")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
    op.drop_table("quotation_items")
    op.drop_table("quotations")
    op.drop_table("solution_bom_snapshots")
    op.drop_table("solution_items")
    op.drop_table("solutions")
    op.drop_table("product_dependencies")
    op.drop_table("category_spec_definitions")
    op.drop_table("product_sensor_capabilities")
    op.drop_table("product_hardware_interfaces")
    op.drop_table("product_power_supplies")
    op.drop_table("product_comm_protocols")
    op.drop_table("product_comm_methods")
    op.drop_table("product_images")
    op.drop_table("bom_templates")
    op.drop_table("products")
    op.drop_table("dict_sensor_metrics")
    op.drop_table("dict_power_supplies")
    op.drop_table("dict_comm_protocols")
    op.drop_table("dict_comm_methods")
    op.drop_table("suppliers")
    op.drop_table("manufacturers")
    op.drop_table("device_categories")
    op.drop_table("field_settings")
    op.drop_table("system_settings")
    op.drop_table("users")

    # ── CREATE in dependency order ────────────────────────────────────────

    # 1. users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role", sa.String(10), server_default="user"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_login", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # 2. device_categories (self-referencing)
    op.create_table(
        "device_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=True),
        sa.Column("level", sa.Integer(), server_default="1"),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["parent_id"], ["device_categories.id"], name="fk_device_categories_parent"),
    )
    op.create_index("ix_device_categories_slug", "device_categories", ["slug"], unique=True)

    # 3. manufacturers
    op.create_table(
        "manufacturers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_manufacturers_name", "manufacturers", ["name"], unique=True)

    # 4. suppliers
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact_person", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])

    # 5. system_settings
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(100), unique=True, nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("description", sa.String(200), nullable=True),
    )
    op.create_index("ix_system_settings_key", "system_settings", ["key"], unique=True)

    # 6. field_settings
    op.create_table(
        "field_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("field_name", sa.String(50), unique=True, nullable=False),
        sa.Column("user_visible", sa.Boolean(), server_default=sa.text("1")),
    )
    op.create_index("ix_field_settings_field_name", "field_settings", ["field_name"], unique=True)

    # 7. dict_comm_methods
    op.create_table(
        "dict_comm_methods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("method_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
    )

    # 8. dict_comm_protocols
    op.create_table(
        "dict_comm_protocols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
    )

    # 9. dict_power_supplies
    op.create_table(
        "dict_power_supplies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supply_category", sa.String(50), nullable=False),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
    )

    # 10. dict_sensor_metrics
    op.create_table(
        "dict_sensor_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
    )

    # 11. products
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("manufacturer_id", sa.Integer(), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("unit", sa.String(20), server_default="台"),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("cost_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("product_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("specs", sa.Text(), nullable=True),
        sa.Column("urls", sa.Text(), nullable=True),
        sa.Column("custom_fields", sa.Text(), nullable=True),
        sa.Column("pinyin_search", sa.Text(), nullable=True),
        sa.Column("view_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["device_categories.id"], name="fk_products_category", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manufacturer_id"], ["manufacturers.id"], name="fk_products_manufacturer", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_products_supplier", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_id"], ["products.id"], name="fk_products_parent", ondelete="SET NULL"),
    )
    op.create_index("ix_products_model", "products", ["model"])
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_sku", "products", ["sku"])
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_status", "products", ["status"])
    op.create_index("ix_products_parent_id", "products", ["parent_id"])

    # 12. product_comm_methods
    op.create_table(
        "product_comm_methods",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("method_id", sa.Integer(), nullable=False),
        sa.Column("details", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_pcm_product", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["method_id"], ["dict_comm_methods.id"], name="fk_pcm_method", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "method_id"),
    )

    # 13. product_comm_protocols
    op.create_table(
        "product_comm_protocols",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(20), server_default="both"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_pcpr_product", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["protocol_id"], ["dict_comm_protocols.id"], name="fk_pcpr_protocol", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "protocol_id"),
    )

    # 14. product_power_supplies
    op.create_table(
        "product_power_supplies",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("power_id", sa.Integer(), nullable=False),
        sa.Column("voltage_range", sa.String(100), nullable=True),
        sa.Column("battery_life", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_pps_product", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["power_id"], ["dict_power_supplies.id"], name="fk_pps_power", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "power_id"),
    )

    # 15. product_hardware_interfaces
    op.create_table(
        "product_hardware_interfaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("interface_name", sa.String(50), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1"),
        sa.Column("description", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_phi_product", ondelete="CASCADE"),
    )
    op.create_index("ix_product_hardware_interfaces_product_id", "product_hardware_interfaces", ["product_id"])

    # 16. product_sensor_capabilities
    op.create_table(
        "product_sensor_capabilities",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("metric_id", sa.Integer(), nullable=False),
        sa.Column("measure_range", sa.String(100), nullable=True),
        sa.Column("accuracy", sa.String(100), nullable=True),
        sa.Column("resolution", sa.String(50), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_psc_product", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["metric_id"], ["dict_sensor_metrics.id"], name="fk_psc_metric", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "metric_id"),
    )

    # 17. product_images
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("alt_text", sa.String(200), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_pi_product", ondelete="CASCADE"),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])

    # 18. product_dependencies
    op.create_table(
        "product_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_product_id", sa.Integer(), nullable=True),
        sa.Column("depends_on_category_id", sa.Integer(), nullable=True),
        sa.Column("dependency_type", sa.String(20), server_default="required"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_pd_product", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["depends_on_product_id"], ["products.id"], name="fk_pd_depends_on_product", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["depends_on_category_id"], ["device_categories.id"], name="fk_pd_depends_on_category", ondelete="CASCADE"),
        sa.CheckConstraint(
            "depends_on_product_id IS NOT NULL OR depends_on_category_id IS NOT NULL",
            name="ck_dependency_target",
        ),
    )
    op.create_index("ix_product_dependencies_product_id", "product_dependencies", ["product_id"])

    # 19. category_spec_definitions
    op.create_table(
        "category_spec_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("spec_key", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("spec_type", sa.String(50), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("is_filterable", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("is_comparable", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("display_group", sa.String(100), nullable=True),
        sa.Column("options", sa.Text(), nullable=True),
        sa.Column("validation", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["device_categories.id"], name="fk_csd_category", ondelete="CASCADE"),
    )

    # 20. bom_templates
    op.create_table(
        "bom_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sheet_name", sa.String(100), server_default="Sheet1"),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("0")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_bt_created_by", ondelete="SET NULL"),
    )

    # 21. solutions
    op.create_table(
        "solutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("client_name", sa.String(200), nullable=True),
        sa.Column("project_name", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("total_cost", sa.Numeric(14, 2), server_default="0"),
        sa.Column("total_price", sa.Numeric(14, 2), server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_solutions_created_by"),
    )

    # 22. solution_items
    op.create_table(
        "solution_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("solution_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount_rate", sa.Numeric(5, 2), server_default="100"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.ForeignKeyConstraint(["solution_id"], ["solutions.id"], name="fk_si_solution", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_si_product", ondelete="RESTRICT"),
    )
    op.create_index("ix_solution_items_solution_id", "solution_items", ["solution_id"])

    # 23. solution_bom_snapshots
    op.create_table(
        "solution_bom_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("solution_id", sa.Integer(), unique=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("exported_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["solution_id"], ["solutions.id"], name="fk_sbom_solution", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["bom_templates.id"], name="fk_sbom_template", ondelete="CASCADE"),
    )

    # 24. quotations
    op.create_table(
        "quotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("solution_id", sa.Integer(), nullable=True),
        sa.Column("quote_number", sa.String(50), unique=True, nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("client_name", sa.String(200), nullable=True),
        sa.Column("client_contact", sa.String(100), nullable=True),
        sa.Column("valid_days", sa.Integer(), server_default="15"),
        sa.Column("tax_rate", sa.Numeric(5, 2), server_default="0"),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("total_amount", sa.Numeric(14, 2), server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["solution_id"], ["solutions.id"], name="fk_quotations_solution", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_quotations_created_by"),
    )

    # 25. quotation_items
    op.create_table(
        "quotation_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quotation_id", sa.Integer(), nullable=False),
        sa.Column("solution_item_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_snapshot", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("discount_rate", sa.Numeric(5, 2), server_default="100"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.ForeignKeyConstraint(["quotation_id"], ["quotations.id"], name="fk_qi_quotation", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["solution_item_id"], ["solution_items.id"], name="fk_qi_solution_item", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_qi_product", ondelete="RESTRICT"),
    )
    op.create_index("ix_quotation_items_quotation_id", "quotation_items", ["quotation_id"])

    # 26. ai_conversations
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ai_conv_user"),
    )
    op.create_index("ix_ai_conversations_user_id", "ai_conversations", ["user_id"])

    # 27. ai_messages
    op.create_table(
        "ai_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_calls", sa.Text(), nullable=True),
        sa.Column("tool_call_id", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], name="fk_aim_conversation", ondelete="CASCADE"),
    )
    op.create_index("ix_ai_messages_conversation_id", "ai_messages", ["conversation_id"])

    # 28. ai_usage_logs
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("model", sa.String(50), nullable=True),
        sa.Column("tokens_in", sa.Integer(), server_default="0"),
        sa.Column("tokens_out", sa.Integer(), server_default="0"),
        sa.Column("duration_ms", sa.Float(), server_default="0"),
        sa.Column("success", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ail_user"),
    )
    op.create_index("ix_ai_usage_logs_user_id", "ai_usage_logs", ["user_id"])

    # 29. login_logs
    op.create_table(
        "login_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("success", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_login_logs_user"),
    )
    op.create_index("ix_login_logs_user_id", "login_logs", ["user_id"])

    # 30. download_tickets
    op.create_table(
        "download_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket", sa.String(64), unique=True, nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_dt_created_by"),
    )
    op.create_index("ix_download_tickets_ticket", "download_tickets", ["ticket"], unique=True)

    # 31. download_logs
    op.create_table(
        "download_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_dl_user"),
    )
    op.create_index("ix_download_logs_user_id", "download_logs", ["user_id"])


def downgrade() -> None:
    """Drop all tables in reverse-dependency order."""
    op.drop_table("download_logs")
    op.drop_table("download_tickets")
    op.drop_table("login_logs")
    op.drop_table("ai_usage_logs")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
    op.drop_table("quotation_items")
    op.drop_table("quotations")
    op.drop_table("solution_bom_snapshots")
    op.drop_table("solution_items")
    op.drop_table("solutions")
    op.drop_table("product_dependencies")
    op.drop_table("category_spec_definitions")
    op.drop_table("product_sensor_capabilities")
    op.drop_table("product_hardware_interfaces")
    op.drop_table("product_power_supplies")
    op.drop_table("product_comm_protocols")
    op.drop_table("product_comm_methods")
    op.drop_table("product_images")
    op.drop_table("bom_templates")
    op.drop_table("products")
    op.drop_table("dict_sensor_metrics")
    op.drop_table("dict_power_supplies")
    op.drop_table("dict_comm_protocols")
    op.drop_table("dict_comm_methods")
    op.drop_table("suppliers")
    op.drop_table("manufacturers")
    op.drop_table("device_categories")
    op.drop_table("field_settings")
    op.drop_table("system_settings")
    op.drop_table("users")
