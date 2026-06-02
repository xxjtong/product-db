"""Shared utility helpers for route handlers."""


def apply_partial_update(obj, data, fields: list[str]):
    """Apply non-None values from data (dict or Pydantic model) to obj for given fields."""
    for f in fields:
        val = data.get(f) if isinstance(data, dict) else getattr(data, f, None)
        if val is not None:
            setattr(obj, f, val)
