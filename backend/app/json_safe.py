"""A json.dumps `default` that converts numpy scalars/arrays (which leak out
of the forensic math all over this app) into plain JSON-serializable types."""
from __future__ import annotations

import json

import numpy as np


def default(obj):
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def sanitize(obj):
    """Round-trip an object through our numpy-safe encoder so every numpy
    scalar/array inside it becomes a plain Python type, suitable for
    FastAPI's own JSON encoding on the way out of an endpoint."""
    return json.loads(json.dumps(obj, default=default))
