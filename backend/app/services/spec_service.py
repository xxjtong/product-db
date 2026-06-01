"""Core spec validation and query building service."""

from app.models.category import CategorySpecDefinition, Category


def validate_specs(specs: dict, spec_defs: list[CategorySpecDefinition]) -> list[str]:
    """Validate submitted specs against spec definitions. Returns list of error messages."""
    errors = []
    spec_def_map = {sd.spec_key: sd for sd in spec_defs}

    for key, value in specs.items():
        if key not in spec_def_map:
            continue  # unknown keys are allowed (custom_fields handles ad-hoc)

        sd = spec_def_map[key]
        if sd.spec_type == "enum" and sd.options:
            if isinstance(value, list):
                for v in value:
                    if v not in sd.options:
                        errors.append(f"{sd.display_name}: '{v}' is not a valid option")
            elif value is not None and value not in sd.options:
                errors.append(f"{sd.display_name}: '{value}' is not a valid option")

        elif sd.spec_type == "number" and sd.validation:
            try:
                num_val = float(value) if value is not None else None
                if num_val is not None:
                    if "min" in sd.validation and num_val < sd.validation["min"]:
                        errors.append(f"{sd.display_name}: minimum is {sd.validation['min']}")
                    if "max" in sd.validation and num_val > sd.validation["max"]:
                        errors.append(f"{sd.display_name}: maximum is {sd.validation['max']}")
            except (ValueError, TypeError):
                errors.append(f"{sd.display_name}: must be a number")

        elif sd.spec_type == "boolean":
            if value is not None and not isinstance(value, bool):
                errors.append(f"{sd.display_name}: must be true or false")

    return errors


def _get_comm_method_names(p) -> list:
    return [cm.method.name for cm in p.comm_methods if cm.method]

def _get_comm_protocol_names(p) -> list:
    return [cp.protocol.name for cp in p.comm_protocols if cp.protocol]

def _get_power_supply_names(p) -> list:
    return [ps.power.name for ps in p.power_supplies if ps.power]

def _get_hardware_interfaces(p) -> list:
    return [f"{hi.interface_name} ×{hi.quantity}" for hi in p.hardware_interfaces]

def _get_sensor_capabilities(p) -> list:
    return [f"{sc.metric.name if sc.metric else ''} {sc.measure_range or ''}" for sc in p.sensor_capabilities]


def compare_products(products: list) -> dict:
    """Generate comparison matrix: {spec_key: {product_id: value, ...}, ...}
    Only includes specs where values differ across products."""
    if len(products) < 2:
        return _extract_all_specs(products)

    all_spec_keys = set()
    product_specs = {}
    for p in products:
        p_specs = {**p.specs}
        p_specs["通讯方式"] = ", ".join(_get_comm_method_names(p))
        p_specs["通讯协议"] = ", ".join(_get_comm_protocol_names(p))
        p_specs["供电方式"] = ", ".join(_get_power_supply_names(p))
        p_specs["硬件接口"] = ", ".join(_get_hardware_interfaces(p))
        p_specs["传感能力"] = ", ".join(_get_sensor_capabilities(p))
        p_specs["价格"] = float(p.base_price) if p.base_price else 0
        p_specs["厂商"] = p.manufacturer.name if p.manufacturer else ""
        p_specs["品类"] = p.category.name if p.category else ""
        product_specs[p.id] = p_specs
        all_spec_keys.update(p_specs.keys())

    result = {}
    for key in sorted(all_spec_keys):
        values = {}
        for p in products:
            values[p.id] = product_specs[p.id].get(key)
        # Only include if values differ
        unique_vals = set(str(v) for v in values.values())
        if len(unique_vals) > 1:
            result[key] = values

    return result


def _extract_all_specs(products: list) -> dict:
    result = {}
    for p in products:
        p_specs = {**p.specs}
        p_specs["通讯方式"] = ", ".join(_get_comm_method_names(p))
        p_specs["通讯协议"] = ", ".join(_get_comm_protocol_names(p))
        p_specs["供电方式"] = ", ".join(_get_power_supply_names(p))
        p_specs["硬件接口"] = ", ".join(_get_hardware_interfaces(p))
        p_specs["传感能力"] = ", ".join(_get_sensor_capabilities(p))
        p_specs["价格"] = float(p.base_price) if p.base_price else 0
        p_specs["厂商"] = p.manufacturer.name if p.manufacturer else ""
        p_specs["品类"] = p.category.name if p.category else ""
        for key, val in p_specs.items():
            if key not in result:
                result[key] = {}
            result[key][p.id] = val
    return result
