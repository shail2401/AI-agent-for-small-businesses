from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Order
from ..services import analytics as A
from ..services.data import load_items, load_products
from ..services.forecast import forecast_all
from ..services.simulator import simulate
from ..utils import to_py

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics/summary")
def summary(days: int = Query(30, ge=7, le=180), db: Session = Depends(get_db)):
    return to_py(A.summary(load_items(db), days))


@router.get("/analytics/timeseries")
def timeseries(days: int = Query(60, ge=14, le=180), db: Session = Depends(get_db)):
    return to_py(A.timeseries(load_items(db), days))


@router.get("/analytics/products")
def products(days: int = Query(30, ge=7, le=180), db: Session = Depends(get_db)):
    return to_py(A.products(load_items(db), days))


@router.get("/analytics/trends")
def trends(days: int = Query(56, ge=14, le=180), db: Session = Depends(get_db)):
    return to_py(A.trends(load_items(db), days))


@router.get("/analytics/recent-orders")
def recent(db: Session = Depends(get_db)):
    rows = db.execute(select(Order).where(Order.status == "PAID").order_by(Order.paid_at.desc()).limit(8)).scalars().all()
    return to_py([dict(id=o.id, total=o.total, source=o.source, paid_at=o.paid_at.isoformat(), payer=o.payer_email) for o in rows])


@router.get("/forecast")
def forecast(horizon: int = Query(14, ge=7, le=60), db: Session = Depends(get_db)):
    f = forecast_all(load_items(db), load_products(db), horizon)
    return to_py(dict(horizon=f["horizon"], daily=f["daily"], backtest=f["backtest"], total_revenue=f.get("total_revenue"),
                      products=[{k: v for k, v in p.items() if k != "daily_units"} for p in f["products"]]))


class Change(BaseModel):
    product_id: int
    price_change_pct: float = Field(0, ge=-50, le=100)
    discount_pct: float = Field(0, ge=0, le=90)


class SimRequest(BaseModel):
    changes: list[Change]
    horizon_days: int = Field(30, ge=7, le=90)


@router.post("/simulate")
def run_simulation(req: SimRequest, db: Session = Depends(get_db)):
    return to_py(simulate(load_items(db), load_products(db), [c.model_dump() for c in req.changes], req.horizon_days))
