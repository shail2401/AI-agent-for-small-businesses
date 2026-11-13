import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Order, OrderItem, Product

COLS = ["order_id", "ts", "product_id", "product", "category", "qty", "unit_price", "unit_cost"]


def today() -> pd.Timestamp:
    return pd.Timestamp.utcnow().tz_localize(None).normalize()


def load_items(db: Session) -> pd.DataFrame:
    """One row per order line for PAID orders. Single source of truth for all analytics."""
    q = (
        select(
            Order.id.label("order_id"), Order.paid_at.label("ts"), OrderItem.product_id,
            Product.name.label("product"), Product.category, OrderItem.quantity.label("qty"),
            OrderItem.unit_price, OrderItem.unit_cost,
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(Order.status == "PAID", Order.paid_at.is_not(None))
    )
    df = pd.read_sql(q, db.get_bind())
    if df.empty:
        df = pd.DataFrame(columns=COLS)
        df["ts"] = pd.to_datetime(df["ts"])
    for c in ("unit_price", "unit_cost", "qty"):
        df[c] = df[c].astype(float)
    df["ts"] = pd.to_datetime(df["ts"])
    df["date"] = df["ts"].dt.normalize()
    df["revenue"] = df["qty"] * df["unit_price"]
    df["cost"] = df["qty"] * df["unit_cost"]
    df["profit"] = df["revenue"] - df["cost"]
    return df


def load_products(db: Session) -> list[dict]:
    rows = db.execute(select(Product).order_by(Product.id)).scalars().all()
    return [dict(id=p.id, name=p.name, category=p.category, price=float(p.price), cost=float(p.cost)) for p in rows]
