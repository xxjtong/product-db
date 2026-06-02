import re


def escape_like(text: str) -> str:
    """Escape % and _ wildcards for SQLAlchemy ilike."""
    return re.sub(r'([%_])', r'\\\1', text)
