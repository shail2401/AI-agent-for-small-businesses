"""Demand forecasting + price elasticity.

Per product we fit a Poisson GLM (log link) on daily units with: linear trend, day-of-week
dummies and log(price / list price). The price coefficient is the product's own price
elasticity learned from historical price/promo variation. Where history lacks price
variation (or yields an implausible sign), we fall back to a category prior and say so.
"""
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

from .data import today

warnings.filterwarnings("ignore", message="Unknown solver options")
PRIOR = {"Mains": -0.9, "Breakfast": -1.1, "Sides": -1.4, "Drinks": -1.7, "Dessert": -1.5}
_cache: dict = {}


def _daily(df_p, list_price, idx):
    g = df_p.groupby("date").agg(units=("qty", "sum"), rev=("revenue", "sum")).reindex(idx)
    units = g["units"].fillna(0.0)
    price = (g["rev"] / g["units"]).fillna(list_price)
    return pd.DataFrame({"units": units, "price": price}, index=idx)


def _X(idx, price, list_price, t0):
    t = ((idx - t0).days.values) / 100.0
    cols = [t] + [(idx.dayofweek.values == d).astype(float) for d in range(1, 7)]
    cols.append(np.log(np.clip(np.asarray(price, float), 1e-6, None) / list_price))
    return np.column_stack(cols)


def _fit(daily, list_price, category):
    prior = PRIOR.get(category, -1.3)
    if len(daily) < 21 or daily["units"].sum() < 15:
        return dict(model=None, mean=float(daily["units"].mean() if len(daily) else 0), elasticity=prior,
                    source="prior", resid=0.0, t0=daily.index[0] if len(daily) else None)
    X, y = _X(daily.index, daily["price"].values, list_price, daily.index[0]), daily["units"].values
    m = PoissonRegressor(alpha=1e-4, max_iter=3000).fit(X, y)
    coef, spread = float(m.coef_[-1]), float(X[:, -1].std())
    ok = spread >= 0.03 and -4.0 <= coef <= -0.2
    resid = float(np.std(y - m.predict(X)))
    return dict(model=m, mean=float(y.mean()), elasticity=coef if ok else prior,
                source="estimated" if ok else "prior", resid=resid, t0=daily.index[0])


def _predict(fit, dates, list_price):
    if fit["model"] is None:
        return np.full(len(dates), fit["mean"])
    X = _X(dates, np.full(len(dates), list_price), list_price, fit["t0"])
    return fit["model"].predict(X)


def forecast_all(df: pd.DataFrame, prods: list[dict], horizon: int = 14, lookback: int = 120) -> dict:
    key = (len(df), str(df["ts"].max()) if len(df) else "", horizon, tuple(p["price"] for p in prods))
    if key in _cache:
        return _cache[key]
    end = today()
    if df.empty:
        return dict(horizon=horizon, daily=[], products=[], backtest=None)
    start = max(df["date"].min(), end - pd.Timedelta(days=lookback))
    idx = pd.date_range(start, end)
    future = pd.date_range(end + pd.Timedelta(days=1), periods=horizon)
    out_p, tot_rev, tot_var = [], np.zeros(horizon), np.zeros(horizon)
    fits, dailies = {}, {}
    for p in prods:
        dp = _daily(df[df["product_id"] == p["id"]], p["price"], idx)
        f = _fit(dp, p["price"], p["category"])
        fits[p["id"]], dailies[p["id"]] = f, dp
        mu = np.clip(_predict(f, future, p["price"]), 0, None)
        sd = max(f["resid"], 0.3 * np.sqrt(mu.mean() + 1e-9))
        tot_rev += mu * p["price"]
        tot_var += (sd * p["price"]) ** 2
        out_p.append(dict(product_id=p["id"], name=p["name"], category=p["category"], price=p["price"], cost=p["cost"],
                          units_total=float(mu.sum()), revenue_total=float(mu.sum() * p["price"]),
                          daily_units=[float(x) for x in mu], elasticity=f["elasticity"], elasticity_source=f["source"]))
    sd = np.sqrt(tot_var)
    daily = [dict(date=d, revenue=float(r), lo=float(max(r - 1.28 * s, 0)), hi=float(r + 1.28 * s))
             for d, r, s in zip(future, tot_rev, sd)]
    result = dict(horizon=horizon, daily=daily, products=out_p, total_revenue=float(tot_rev.sum()),
                  backtest=_backtest(df, prods, idx))
    _cache.clear()
    _cache[key] = result
    return result


def _backtest(df, prods, idx, hold=14):
    """Hold out the last 14 days; compare model vs a seasonal-naive baseline on revenue (WAPE)."""
    if len(idx) < 56:
        return None
    train_idx, test_idx = idx[:-hold], idx[-hold:]
    pred = np.zeros(hold)
    actual = np.zeros(hold)
    naive = np.zeros(hold)
    for p in prods:
        dp = _daily(df[df["product_id"] == p["id"]], p["price"], idx)
        f = _fit(dp.loc[train_idx], p["price"], p["category"])
        # predict with the prices that actually applied, so promos in the window are not penalised
        if f["model"] is None:
            mu = np.full(hold, f["mean"])
        else:
            mu = f["model"].predict(_X(test_idx, dp.loc[test_idx, "price"].values, p["price"], f["t0"]))
        pred += mu * dp.loc[test_idx, "price"].values
        actual += dp.loc[test_idx, "units"].values * dp.loc[test_idx, "price"].values
        tr = dp.loc[train_idx[-28:]]
        dow_mean = (tr["units"] * tr["price"]).groupby(tr.index.dayofweek).mean()
        naive += np.array([dow_mean.get(d, 0.0) for d in test_idx.dayofweek])
    wape = lambda a, b: float(np.abs(a - b).sum() / max(a.sum(), 1e-9) * 100)
    return dict(holdout_days=hold, model_wape_pct=round(wape(actual, pred), 1), naive_wape_pct=round(wape(actual, naive), 1))
