from typing import List, Optional, Any
from html import escape
from Models.ExtractedInfo import ExtractedInfo

def get_html_attributes(obj: Any, attr: str, default: str = "N/A") -> str:
    """
    Helper to retrieve attribute from objects or keys from dicts.
    Returns default if not present or value is falsy (but not zero).
    """
    if obj is None:
        return default
    # If dict-like
    try:
        if isinstance(obj, dict):
            val = obj.get(attr, default)
            return val if val is not None else default
    except Exception:
        pass
    # If object with attribute
    try:
        val = getattr(obj, attr)
        return val if val is not None else default
    except Exception:
        return default
