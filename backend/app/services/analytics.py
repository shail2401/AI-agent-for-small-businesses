import numpy as np
import pandas as pd

from .data import today


def _pct(cur, prev):
    return None if not prev else round((cur - prev) / prev * 100, 1)


def _window(df, start, end):
    return df[(df["date"] > start) & (df["date"] <= end)]


def _kpis(w: pd.DataFrame) -> dict:
    rev, tx, profit = float(w["revenue"].sum()), int(w["order_id"].nunique()), float(w["profit"].sum())
    return dict(revenue=round(rev, 2), transactions=tx, aov=round(rev / tx, 2) if tx else 0.0,
                profit=round(profit, 2), margin_pct=round(profit / rev * 100, 1) if rev else 0.0,
                units=int(w["qty"].sum()))


def summary(df: pd.DataFrame, days: int = 30) -> dict:
    end = today() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    d = pd.Timedelta(days=days)
    cur, prev = _kpis(_window(df, end.normalize() - d, end)), _kpis(_window(df, end.normalize() - 2 * d, end.normalize() - d))
    return dict(days=days, current=cur, previous=prev,
                change_pct={k: _pct(cur[k], prev[k]) for k in ("revenue", "transactions", "aov", "profit", "units")})


def timeseries(df: pd.DataFrame, days: int = 60) -> list[dict]:
    end = today()
    idx = pd.date_range(end - pd.Timedelta(days=days - 1), end)
    g = df.groupby("date").agg(revenue=("revenue", "sum"), profit=("profit", "sum"), transactions=("order_id", "nunique"))
    g = g.reindex(idx).fillna(0.0)
    g["avg7"] = g["revenue"].rolling(7, min_periods=1).mean()
    g.index.name = "date"
    return g.round(2).reset_index().to_dict("records")


def products(df: pd.DataFrame, days: int = 30) -> list[dict]:
    """Per-product performance plus menu-engineering class (star / workhorse / puzzle / dog)."""
    end = today() + pd.Timedelta(days=1)
    d = pd.Timedelta(days=days)
    cur, prev = _window(df, end - d - pd.Timedelta(days=1), end), _window(df, end - 2 * d - pd.Timedelta(days=1), end - d - pd.Timedelta(days=1))
    if cur.empty:
        return []
    g = cur.groupby(["product_id", "product", "category"]).agg(
        units=("qty", "sum"), revenue=("revenue", "sum"), profit=("profit", "sum")).reset_index()
    pg = prev.groupby("product_id")["revenue"].sum()
    g["prev_revenue"] = g["product_id"].map(pg).fillna(0.0)
    g["revenue_change_pct"] = [_pct(a, b) for a, b in zip(g["revenue"], g["prev_revenue"])]
    g["avg_price"] = g["revenue"] / g["units"]
    g["unit_margin"] = g["profit"] / g["units"]
    g["margin_pct"] = g["profit"] / g["revenue"] * 100
    g["revenue_share_pct"] = g["revenue"] / g["revenue"].sum() * 100
    pop_cut = 0.7 / len(g) * g["units"].sum()                      # menu-engineering popularity rule
    margin_cut = g["profit"].sum() / g["units"].sum()               # weighted average unit margin
    def klass(r):
        hi_pop, hi_mar = r.units >= pop_cut, r.unit_margin >= margin_cut
        return "star" if hi_pop and hi_mar else "workhorse" if hi_pop else "puzzle" if hi_mar else "dog"
    g["class"] = g.apply(klass, axis=1)
    g = g.sort_values("revenue", ascending=False).drop(columns=["prev_revenue"])
    return g.round(2).to_dict("records")


def trends(df: pd.DataFrame, days: int = 56) -> dict:
    end = today()
    w = df[df["date"] > end - pd.Timedelta(days=days)]
    if w.empty:
        return {}
    daily = w.groupby("date")["revenue"].sum().reindex(pd.date_range(end - pd.Timedelta(days=days - 1), end)).fillna(0)
    by_dow = daily.groupby(daily.index.dayofweek).mean()
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly = daily.resample("W").sum().iloc[:-1] if len(daily) > 14 else daily.resample("W").sum()
    slope = 0.0
    if len(weekly) >= 3 and weekly.mean() > 0:
        slope = float(np.polyfit(np.arange(len(weekly)), weekly.values, 1)[0] / weekly.mean() * 100)
    hours = w.groupby(w["ts"].dt.hour)["revenue"].sum()
    cat = w.groupby("category")["revenue"].sum()
    return dict(
        weekday_avg_revenue=[dict(day=names[i], revenue=round(float(by_dow.get(i, 0)), 2)) for i in range(7)],
        best_day=names[int(by_dow.idxmax())], slowest_day=names[int(by_dow.idxmin())],
        weekly_growth_pct=round(slope, 2),
        revenue_by_hour=[dict(hour=int(h), revenue=round(float(v), 2)) for h, v in hours.items()],
        peak_hour=int(hours.idxmax()),
        category_mix=[dict(category=k, share_pct=round(float(v / cat.sum() * 100), 1)) for k, v in cat.sort_values(ascending=False).items()],
    )
