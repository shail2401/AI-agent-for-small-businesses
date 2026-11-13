import logging
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Order, OrderItem, Product, WebhookEvent
from ..paypal import PayPalError, paypal
from ..services.data import load_products
from ..utils import to_py

log = logging.getLogger("payments")
router = APIRouter(prefix="/api", tags=["payments"])


@router.get("/menu")
def menu(db: Session = Depends(get_db)):
    return to_py(load_products(db))


class Line(BaseModel):
    product_id: int
    qty: int = Field(ge=1, le=20)


class CreateOrder(BaseModel):
    items: list[Line] = Field(min_length=1)


def mark_paid(db: Session, order: Order, capture: dict, payer_email: str | None = None) -> bool:
    """Idempotent: both the capture endpoint and the webhook call this; only the first one changes state."""
    if order.status == "PAID":
        return False
    order.status, order.paid_at = "PAID", datetime.utcnow()
    order.capture_id = capture.get("id") or order.capture_id
    order.payer_email = payer_email or order.payer_email
    return True


@router.post("/checkout/orders")
def create_order(req: CreateOrder, db: Session = Depends(get_db)):
    # Prices come from the database, never from the browser.
    prods = {p.id: p for p in db.execute(select(Product).where(Product.id.in_([l.product_id for l in req.items]))).scalars()}
    if len(prods) != len({l.product_id for l in req.items}):
        raise HTTPException(400, "Unknown product in cart")
    total = sum(prods[l.product_id].price * l.qty for l in req.items)
    order = Order(status="CREATED", total=total, source="paypal", items=[
        OrderItem(product_id=l.product_id, quantity=l.qty, unit_price=prods[l.product_id].price, unit_cost=prods[l.product_id].cost)
        for l in req.items])
    db.add(order)
    db.flush()
    try:
        pp = paypal.create_order(order.id, f"{total:.2f}", [dict(name=prods[l.product_id].name, qty=l.qty, price=f"{prods[l.product_id].price:.2f}") for l in req.items])
    except PayPalError as e:
        db.rollback()
        raise HTTPException(502, str(e))
    order.paypal_order_id = pp["id"]
    db.commit()
    return dict(id=pp["id"], order_id=order.id)


@router.post("/checkout/orders/{paypal_order_id}/capture")
def capture_order(paypal_order_id: str, db: Session = Depends(get_db)):
    order = db.execute(select(Order).where(Order.paypal_order_id == paypal_order_id)).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    try:
        res = paypal.capture(paypal_order_id)
    except PayPalError as e:
        raise HTTPException(502, str(e))
    cap = res["purchase_units"][0]["payments"]["captures"][0]
    if cap.get("status") == "COMPLETED":
        mark_paid(db, order, cap, res.get("payer", {}).get("email_address"))
        db.commit()
    return dict(order_id=order.id, status=order.status, total=float(order.total))


def _handle_event(db: Session, ev: dict) -> str:
    t, res = ev.get("event_type", ""), ev.get("resource", {})
    if t == "PAYMENT.CAPTURE.COMPLETED":
        order = db.get(Order, int(res["custom_id"])) if str(res.get("custom_id", "")).isdigit() else None
        if not order:
            return "no matching order (custom_id missing)"
        return "marked paid" if mark_paid(db, order, res) else "already paid"
    if t == "CHECKOUT.ORDER.APPROVED":
        order = db.execute(select(Order).where(Order.paypal_order_id == res.get("id"))).scalar_one_or_none()
        if order and order.status == "CREATED":
            order.status = "APPROVED"
        return "approved"
    if t in ("PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"):
        cap_id = next((l["href"].rstrip("/").split("/")[-1] for l in res.get("links", []) if l.get("rel") == "up"), None)
        order = db.execute(select(Order).where(Order.capture_id == cap_id)).scalar_one_or_none() if cap_id else None
        if order:
            order.status = "REFUNDED"
            return "refunded"
        return "no matching capture"
    if t in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
        order = db.get(Order, int(res["custom_id"])) if str(res.get("custom_id", "")).isdigit() else None
        if order and order.status != "PAID":
            order.status = "FAILED"
        return "failed"
    return "ignored"


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    ev = await request.json()
    if settings.paypal_webhook_id:
        headers = {k.lower(): v for k, v in request.headers.items()}
        if not paypal.verify_webhook(headers, ev):
            raise HTTPException(400, "Invalid webhook signature")
    else:
        log.warning("PAYPAL_WEBHOOK_ID not set: webhook signature NOT verified (dev only)")
    record = WebhookEvent(event_id=ev.get("id", ""), event_type=ev.get("event_type", ""), payload=ev)
    db.add(record)
    try:
        db.flush()
    except IntegrityError:  # PayPal retries deliveries: ignore duplicates
        db.rollback()
        return {"status": "duplicate"}
    record.outcome = _handle_event(db, ev)
    db.commit()
    return {"status": "ok", "outcome": record.outcome}
