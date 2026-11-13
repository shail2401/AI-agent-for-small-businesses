import math
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd


def to_py(o):
    """Recursively convert numpy / pandas / Decimal values into JSON-safe Python."""
    if isinstance(o, dict):
        return {str(k): to_py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_py(v) for v in o]
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return o.isoformat()[:10]
    return o
