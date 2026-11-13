"""Decision simulator: turns price changes / promo discounts into revenue & profit impact.

scenario_units = baseline_units * (new_price / list_price) ** elasticity
Baseline units come from the demand forecast; elasticity is learned (or a labelled prior).
"""
import pandas as pd

from .forecast import forecast_all


def _eval(units, price, cost):
    return units * price, units * (price - cost)


def simulate(df: pd.DataFrame, prods: list[dict], changes: list[dict], horizon_days: int = 30) -> dict:
    horizon_days = max(7, min(int(horizon_days), 90))
    fc = forecast_all(df, prods, horizon=horizon_days)
    fp = {p["product_id"]: p for p in fc["products"]}
    rows, tot = [], dict(b_rev=0.0, b_prof=0.0, s_rev=0.0, s_prof=0.0, lo=0.0, hi=0.0)
    chg = {c["product_id"]: c for c in changes}
    for pid, p in fp.items():
        c = chg.get(pid, {})
        pc = max(-50.0, min(100.0, float(c.get("price_change_pct", 0))))
        disc = max(0.0, min(90.0, float(c.get("discount_pct", 0))))
        ratio = (1 + pc / 100) * (1 - disc / 100)
        e, price, cost, base_u = p["elasticity"], p["price"], p["cost"], p["units_total"]
        new_price = price * ratio
        s_u = base_u * ratio ** e
        b_rev, b_prof = _eval(base_u, price, cost)
        s_rev, s_prof = _eval(s_u, new_price, cost)
        lo_p = min(_eval(base_u * ratio ** (e + d), new_price, cost)[1] for d in (-0.5, 0.5))
        hi_p = max(_eval(base_u * ratio ** (e + d), new_price, cost)[1] for d in (-0.5, 0.5))
        new_margin = new_price - cost
        breakeven = (price - cost) / new_margin - 1 if new_margin > 0 and ratio != 1 else None
        rows.append(dict(product_id=pid, name=p["name"], changed=ratio != 1, price=price, new_price=round(new_price, 2),
                         elasticity=round(e, 2), elasticity_source=p["elasticity_source"],
                         baseline_units=round(base_u), scenario_units=round(s_u),
                         units_change_pct=round((s_u / base_u - 1) * 100, 1) if base_u else 0,
                         baseline_revenue=round(b_rev, 2), scenario_revenue=round(s_rev, 2),
                         baseline_profit=round(b_prof, 2), scenario_profit=round(s_prof, 2),
                         profit_delta=round(s_prof - b_prof, 2),
                         profit_range=[round(lo_p - b_prof, 2), round(hi_p - b_prof, 2)],
                         breakeven_volume_change_pct=None if breakeven is None else round(breakeven * 100, 1)))
        for k, v in (("b_rev", b_rev), ("b_prof", b_prof), ("s_rev", s_rev), ("s_prof", s_prof)):
            tot[k] += v
        tot["lo"] += lo_p - b_prof
        tot["hi"] += hi_p - b_prof
    dr, dp = tot["s_rev"] - tot["b_rev"], tot["s_prof"] - tot["b_prof"]
    changed = [r for r in rows if r["changed"]]
    verdict = ("No changes applied." if not changed else
               "Revenue and profit both rise." if dr > 0 and dp > 0 else
               "Revenue falls but profit rises." if dr <= 0 and dp > 0 else
               "Revenue rises but profit falls." if dr > 0 else "Revenue and profit both fall.")
    return dict(
        horizon_days=horizon_days,
        baseline=dict(revenue=round(tot["b_rev"], 2), profit=round(tot["b_prof"], 2)),
        scenario=dict(revenue=round(tot["s_rev"], 2), profit=round(tot["s_prof"], 2)),
        delta=dict(revenue=round(dr, 2), profit=round(dp, 2),
                   revenue_pct=round(dr / tot["b_rev"] * 100, 1) if tot["b_rev"] else None,
                   profit_pct=round(dp / tot["b_prof"] * 100, 1) if tot["b_prof"] else None,
                   profit_range=[round(tot["lo"], 2), round(tot["hi"], 2)]),
        verdict=verdict, products=rows,
        assumptions=["Baseline = ML demand forecast at current list prices.",
                     "Elasticity is learned from past price/promo variation where available; otherwise a category prior (flagged).",
                     "profit_range reflects elasticity uncertainty of ±0.5. No competitor or cannibalisation effects are modelled."])


def find_opportunities(df: pd.DataFrame, prods: list[dict], horizon_days: int = 30) -> list[dict]:
    """Test +5% / +10% price moves per product and rank by simulated profit gain."""
    fc = forecast_all(df, prods, horizon=horizon_days)
    out = []
    for p in fc["products"]:
        best = None
        for pc in (5, 10):
            r = simulate(df, prods, [dict(product_id=p["product_id"], price_change_pct=pc)], horizon_days)["products"]
            row = next(x for x in r if x["product_id"] == p["product_id"])
            if best is None or row["profit_delta"] > best["profit_delta"]:
                best = dict(product=p["name"], price_change_pct=pc, elasticity=row["elasticity"],
                            elasticity_source=row["elasticity_source"], profit_delta=row["profit_delta"],
                            revenue_delta=round(row["scenario_revenue"] - row["baseline_revenue"], 2),
                            units_change_pct=row["units_change_pct"])
        if best and best["profit_delta"] > 0:
            out.append(best)
    return sorted(out, key=lambda x: -x["profit_delta"])[:5]
