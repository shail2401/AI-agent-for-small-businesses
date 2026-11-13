"""Synthetic but realistic history so the dashboard, forecasts and elasticities work on day one.
Includes price changes and promos so elasticity can actually be learned. Run: python -m app.seed"""
import random
from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import Order, OrderItem, Product

# name, category, price, cost, base units/day, true elasticity
MENU = [
    ("Classic Cheeseburger", "Mains", 11.50, 4.80, 38, -0.7), ("Chicken Fried Steak", "Mains", 14.00, 6.90, 16, -0.8),
    ("Meatloaf Plate", "Mains", 13.00, 6.40, 12, -0.9), ("Patty Melt", "Mains", 12.00, 5.10, 15, -1.0),
    ("Two-Egg Breakfast", "Breakfast", 9.50, 2.60, 34, -1.0), ("Buttermilk Pancakes", "Breakfast", 8.50, 1.90, 26, -1.3),
    ("Biscuits & Gravy", "Breakfast", 8.00, 2.10, 14, -1.1), ("Hand-Cut Fries", "Sides", 4.50, 0.90, 52, -1.4),
    ("Onion Rings", "Sides", 5.50, 1.30, 20, -1.6), ("Chocolate Shake", "Drinks", 6.00, 1.50, 30, -1.5),
    ("Bottomless Coffee", "Drinks", 2.75, 0.30, 70, -0.5), ("Apple Pie Slice", "Dessert", 5.00, 1.60, 18, -1.7),
]
DAYS = 150
DOW = [0.80, 0.85, 0.90, 0.95, 1.20, 1.45, 1.30]  # Mon..Sun
HOUR_W = {7: 5, 8: 9, 9: 7, 11: 8, 12: 14, 13: 11, 14: 5, 17: 6, 18: 9, 19: 7, 20: 3}


def seed(force: bool = False):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.execute(select(Product.id)).first() and not force:
            return
        for tbl in (OrderItem, Order, Product):
            db.query(tbl).delete()
        prods = [Product(name=n, category=c, price=Decimal(str(p)), cost=Decimal(str(k))) for n, c, p, k, _, _ in MENU]
        db.add_all(prods)
        db.flush()
        rng, np_rng = random.Random(7), np.random.default_rng(7)
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        # promo / price experiments: (product idx, start day offset, length, multiplier)
        events = [(5, 40, 14, 0.85), (8, 70, 10, 0.80), (9, 95, 14, 0.90), (1, 55, 14, 1.07), (7, 100, 14, 1.10),
                  (11, 20, 10, 0.80), (3, 120, 14, 0.90), (0, 80, 12, 1.06), (6, 110, 10, 0.85), (4, 30, 10, 1.08)]
        hours, w = list(HOUR_W), list(HOUR_W.values())
        for off in range(DAYS, -1, -1):
            day = today - timedelta(days=off)
            trend = 1 + 0.0012 * (DAYS - off)
            tokens = []
            for i, (n, c, price, cost, base, e) in enumerate(MENU):
                mult = 1.0
                for pi, s, ln, m in events:
                    if pi == i and s <= DAYS - off < s + ln:
                        mult = m
                lam = base * 0.55 * DOW[day.weekday()] * trend * mult ** e
                units = int(np_rng.poisson(lam))
                tokens += [(prods[i], round(price * mult, 2))] * units
            rng.shuffle(tokens)
            while tokens:
                size = min(len(tokens), rng.choice([1, 2, 2, 3, 3, 4]))
                basket, tokens = tokens[:size], tokens[size:]
                ts = day + timedelta(hours=rng.choices(hours, w)[0], minutes=rng.randint(0, 59))
                if ts > datetime.utcnow():
                    continue
                lines: dict = {}
                for p, pr in basket:
                    q = lines.setdefault((p.id, pr), [p, 0])
                    q[1] += 1
                total = sum(Decimal(str(pr)) * q[1] for (pid, pr), q in lines.items())
                db.add(Order(status="PAID", total=total, source="seed", created_at=ts, paid_at=ts,
                             items=[OrderItem(product_id=p.id, quantity=q, unit_price=Decimal(str(pr)), unit_cost=p.cost)
                                    for (pid, pr), (p, q) in lines.items()]))
        db.commit()


if __name__ == "__main__":
    seed(force=True)
    print("Seeded.")
