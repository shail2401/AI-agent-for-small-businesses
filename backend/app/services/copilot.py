"""AI business copilot: an LLM with tool calling over real business data.
The model never sees raw tables; it calls analytics / forecast / simulator tools and must cite their numbers."""
import json

import anthropic
from sqlalchemy.orm import Session

from ..config import settings
from ..utils import to_py
from . import analytics
from .data import load_items, load_products
from .forecast import forecast_all
from .simulator import find_opportunities, simulate

SYSTEM = """You are Luke's Diner Copilot, a business analyst for a small diner owner.
Rules:
- Answer ONLY from tool results. Always call tools before stating any number; never guess or use memory.
- Lead with the answer in plain language, then 2-4 pieces of evidence (exact figures from tools), then a concrete recommendation.
- For any "what if" about prices or promos, call simulate_decision. Report profit as well as revenue, the uncertainty range, and whether elasticity was estimated or a prior.
- Be honest about uncertainty: a promo that lifts revenue can still lose profit. If data is thin, say so.
- Keep answers short, in dollars, no jargon. Use short markdown lists when helpful."""

_days = {"type": "integer", "description": "Look-back window in days (7-90)", "default": 30}
TOOLS = [
    {"name": "get_business_summary", "description": "Revenue, transactions, average order value, profit, margin for the last N days vs the previous N days.",
     "input_schema": {"type": "object", "properties": {"days": _days}}},
    {"name": "get_product_performance", "description": "Per-product revenue, units, profit, margin, revenue change vs prior period and menu class (star/workhorse/puzzle/dog).",
     "input_schema": {"type": "object", "properties": {"days": _days}}},
    {"name": "get_sales_trends", "description": "Weekday pattern, peak hours, weekly growth rate and category mix.",
     "input_schema": {"type": "object", "properties": {"days": {"type": "integer", "default": 56}}}},
    {"name": "get_demand_forecast", "description": "ML forecast of daily revenue and per-product units for the next N days, with backtest accuracy and learned price elasticities.",
     "input_schema": {"type": "object", "properties": {"horizon_days": {"type": "integer", "default": 14}}}},
    {"name": "simulate_decision",
     "description": "Estimate revenue and profit impact of price changes or promo discounts over a horizon. Provide one entry per product changed (use product names).",
     "input_schema": {"type": "object", "properties": {
         "changes": {"type": "array", "items": {"type": "object", "properties": {
             "product": {"type": "string"}, "price_change_pct": {"type": "number"}, "discount_pct": {"type": "number"}},
             "required": ["product"]}},
         "horizon_days": {"type": "integer", "default": 30}}, "required": ["changes"]}},
    {"name": "find_opportunities", "description": "Rank products where a small price increase is simulated to raise profit.",
     "input_schema": {"type": "object", "properties": {}}},
]


def _run_tool(db: Session, name: str, args: dict):
    df, prods = load_items(db), load_products(db)
    if df.empty:
        return {"error": "No paid orders yet."}
    if name == "get_business_summary":
        return analytics.summary(df, int(args.get("days", 30)))
    if name == "get_product_performance":
        return analytics.products(df, int(args.get("days", 30)))
    if name == "get_sales_trends":
        t = analytics.trends(df, int(args.get("days", 56)))
        return {k: v for k, v in t.items() if k != "revenue_by_hour"} | {"peak_hour": t.get("peak_hour")}
    if name == "get_demand_forecast":
        f = forecast_all(df, prods, int(args.get("horizon_days", 14)))
        return dict(horizon=f["horizon"], total_revenue=f["total_revenue"], backtest=f["backtest"],
                    daily=[{k: round(v, 0) if k != "date" else v for k, v in d.items()} for d in f["daily"]],
                    products=[{k: p[k] for k in ("name", "units_total", "revenue_total", "elasticity", "elasticity_source")} for p in f["products"]])
    if name == "simulate_decision":
        by_name = {p["name"].lower(): p["id"] for p in prods}
        changes, unknown = [], []
        for c in args.get("changes", []):
            pid = by_name.get(str(c.get("product", "")).lower())
            if pid is None:
                unknown.append(c.get("product"))
                continue
            changes.append(dict(product_id=pid, price_change_pct=c.get("price_change_pct", 0), discount_pct=c.get("discount_pct", 0)))
        res = simulate(df, prods, changes, int(args.get("horizon_days", 30)))
        res["products"] = [r for r in res["products"] if r["changed"]]
        if unknown:
            res["unknown_products"] = unknown + ["(valid names: " + ", ".join(p["name"] for p in prods) + ")"]
        return res
    if name == "find_opportunities":
        return find_opportunities(df, prods)
    return {"error": f"unknown tool {name}"}


def chat(db: Session, messages: list[dict]) -> dict:
    if not settings.anthropic_api_key:
        return dict(answer="The copilot needs an `ANTHROPIC_API_KEY` in backend/.env. Dashboard, forecast and simulator work without it.", evidence=[])
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msgs, evidence = [dict(role=m["role"], content=m["content"]) for m in messages], []
    for _ in range(8):  # tool-use loop
        resp = client.messages.create(model=settings.llm_model, max_tokens=1500, system=SYSTEM, tools=TOOLS, messages=msgs)
        if resp.stop_reason != "tool_use":
            return dict(answer="".join(b.text for b in resp.content if b.type == "text"), evidence=evidence)
        msgs.append(dict(role="assistant", content=resp.content))
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                try:
                    out = to_py(_run_tool(db, b.name, b.input or {}))
                except Exception as e:  # surface tool errors to the model instead of crashing
                    out = {"error": str(e)}
                evidence.append(dict(tool=b.name, input=b.input, output=out))
                results.append(dict(type="tool_result", tool_use_id=b.id, content=json.dumps(out)[:12000]))
        msgs.append(dict(role="user", content=results))
    return dict(answer="I couldn't finish the analysis. Try a narrower question.", evidence=evidence)
