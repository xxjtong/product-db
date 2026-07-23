import re

LIKE_ESCAPE = '\\'


def escape_like(text: str) -> str:
    """Escape % and _ wildcards for SQLAlchemy ilike.

    IMPORTANT: callers MUST pass escape=LIKE_ESCAPE to ilike(),
    e.g. column.ilike(pattern, escape=LIKE_ESCAPE).
    """
    return re.sub(r'([%_])', r'\\\1', text)
