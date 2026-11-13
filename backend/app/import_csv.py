"""Import a sales CSV (e.g. from Kaggle) into Luke's Diner Copilot.

  python -m app.import_csv /data/sales.csv --replace --shift-to-today
  python -m app.import_csv sales.csv --map product="Item Name" --map qty=Quantity

Columns are auto-detected by common names; override any with --map field=Column.
Fields: order_id, date, time, product, category, qty, price, total, cost
Only date, product and (qty + price, or total) are required.
"""
import argparse
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import Order, OrderItem, Product

ALIASES = {
    "order_id": ["transaction_id", "order_id", "orderid", "invoice", "invoiceno", "invoice_no", "receipt_id", "receipt", "check_id", "ticket_id"],
    "date": ["transaction_date", "order_date", "date", "datetime", "timestamp", "invoicedate", "sale_date", "created_at"],
    "time": ["transaction_time", "order_time", "time"],
    "product": ["product_detail", "item", "item_name", "product", "product_name", "menu_item", "description", "name"],
    "category": ["product_category", "item_category", "category", "product_type", "type"],
    "qty": ["transaction_qty", "quantity", "qty", "units", "units_sold", "quantity_sold"],
    "price": ["unit_price", "price_per_unit", "price", "item_price", "unitprice", "selling_price"],
    "total": ["total_spent", "total_price", "total_amount", "line_total", "total", "revenue", "sales", "amount"],
    "cost": ["unit_cost", "cost_per_unit", "cost", "cogs"],
}
BAD = {"", "error", "unknown", "nan", "none", "null", "n/a", "na"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def detect(columns, overrides: dict) -> dict:
    by_norm = {norm(c): c for c in columns}
    found = {}
    for field, names in ALIASES.items():
        if field in overrides:
            if overrides[field] not in columns:
                sys.exit(f"--map {field}={overrides[field]}: no such column. Columns are: {list(columns)}")
            found[field] = overrides[field]
        else:
            hit = next((by_norm[n] for n in names if n in by_norm), None)
            if hit:
                found[field] = hit
    return found


def num(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.where(~s.str.lower().isin(BAD))
    return pd.to_numeric(s.str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--replace", action="store_true", help="delete existing products/orders first (includes seed data)")
    ap.add_argument("--shift-to-today", action="store_true", help="shift all dates so the newest sale is yesterday")
    ap.add_argument("--cost-pct", type=float, default=0.35, help="unit cost as a share of price when the file has no cost (default 0.35)")
    ap.add_argument("--top", type=int, default=40, help="keep the top N products by revenue (default 40)")
    ap.add_argument("--dayfirst", action="store_true", help="dates are DD/MM/YYYY")
    ap.add_argument("--map", action="append", default=[], metavar="field=Column")
    a = ap.parse_args()

    raw = pd.read_csv(a.csv, dtype=str, keep_default_na=False)
    cols = detect(raw.columns, dict(m.split("=", 1) for m in a.map))
    print("Column mapping:", {k: v for k, v in cols.items()})
    need = [f for f in ("date", "product") if f not in cols]
    if "qty" not in cols and "total" not in cols:
        need.append("qty or total")
    if "price" not in cols and "total" not in cols:
        need.append("price or total")
    if need:
        sys.exit(f"Missing: {need}. Columns found: {list(raw.columns)}\nUse --map field=Column, e.g. --map product=\"Item Name\"")

    df = pd.DataFrame({"product": raw[cols["product"]].str.strip()})
    df["product"] = df["product"].where(~df["product"].str.lower().isin(BAD))
    d = raw[cols["date"]].str.strip()
    if "time" in cols:
        d = d + " " + raw[cols["time"]].str.strip()
    df["ts"] = pd.to_datetime(d.where(~d.str.lower().isin(BAD)), errors="coerce", dayfirst=a.dayfirst)
    df["qty"] = num(raw[cols["qty"]]) if "qty" in cols else float("nan")
    df["price"] = num(raw[cols["price"]]) if "price" in cols else float("nan")
    total = num(raw[cols["total"]]) if "total" in cols else pd.Series(float("nan"), index=raw.index)
    df["price"] = df["price"].fillna(total / df["qty"])
    df["qty"] = df["qty"].fillna(total / df["price"]).fillna(1 if "qty" not in cols and "total" in cols else float("nan"))
    if "qty" not in cols and "total" in cols:
        df["qty"], df["price"] = 1.0, total
    df["category"] = raw[cols["category"]].str.strip().where(lambda s: ~s.str.lower().isin(BAD), "Other") if "category" in cols else "Other"
    df["cost"] = num(raw[cols["cost"]]) if "cost" in cols else float("nan")
    df["order_key"] = raw[cols["order_id"]].str.strip() if "order_id" in cols else pd.Series(raw.index.astype(str), index=raw.index)

    before = len(df)
    df = df.dropna(subset=["product", "ts", "qty", "price"])
    df = df[(df["qty"] > 0) & (df["price"] > 0)]
    df["qty"] = df["qty"].round().clip(lower=1).astype(int)
    print(f"Usable rows: {len(df):,} of {before:,} (dropped {before - len(df):,} with missing/invalid values)")
    if df.empty:
        sys.exit("No usable rows. Check --dayfirst and the column mapping.")
    if "time" not in cols and (df["ts"].dt.hour == 0).all():
        df["ts"] = df["ts"] + timedelta(hours=12)
        print("Note: file has no time of day, so orders are stamped 12:00 (hourly charts will not be meaningful).")
    if "order_id" not in cols:
        print("Note: no order id column, so each row becomes its own order (average order value = one line).")

    keep = df.assign(rev=df["qty"] * df["price"]).groupby("product")["rev"].sum().nlargest(a.top).index
    df = df[df["product"].isin(keep)]
    if a.shift_to_today:
        delta = (pd.Timestamp.utcnow().tz_localize(None).normalize() - timedelta(days=1)) - df["ts"].max().normalize()
        df["ts"] = df["ts"] + delta
        print(f"Shifted all dates by {delta.days} days (newest sale is now yesterday).")
    print(f"Date range: {df['ts'].min().date()} to {df['ts'].max().date()}  |  {df['product'].nunique()} products  |  {df['order_key'].nunique():,} orders")

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if a.replace:
            for t in (OrderItem, Order, Product):
                db.query(t).delete()
            db.commit()
        latest = df.sort_values("ts").groupby("product").tail(30).groupby("product")
        info = pd.DataFrame({"price": latest["price"].median(), "category": latest["category"].last(), "cost": latest["cost"].median()})
        info["cost"] = info["cost"].fillna(info["price"] * a.cost_pct)
        existing = {p.name: p for p in db.execute(select(Product)).scalars()}
        for name, r in info.iterrows():
            if name not in existing:
                existing[name] = Product(name=name, category=r["category"], price=Decimal(f"{r.price:.2f}"), cost=Decimal(f"{r.cost:.2f}"))
                db.add(existing[name])
        db.commit()

        n = 0
        for _, g in df.groupby("order_key", sort=False):
            ts = g["ts"].min().to_pydatetime()
            lines = g.groupby(["product", "price"], as_index=False).agg(qty=("qty", "sum"))
            items = [OrderItem(product_id=existing[l["product"]].id, quantity=int(l["qty"]), unit_price=Decimal(f"{l['price']:.2f}"),
                               unit_cost=existing[l["product"]].cost) for _, l in lines.iterrows()]
            total = sum(i.unit_price * i.quantity for i in items)
            db.add(Order(status="PAID", total=total, source="import", created_at=ts, paid_at=ts, items=items))
            n += 1
            if n % 5000 == 0:
                db.commit()
                print(f"  {n:,} orders…")
        db.commit()
    print(f"Done. Imported {n:,} orders. Cost per unit set to {a.cost_pct:.0%} of price where the file had none; edit products.cost to match reality.")


if __name__ == "__main__":
    main()
