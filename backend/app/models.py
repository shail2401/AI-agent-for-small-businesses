from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    category: Mapped[str] = mapped_column(String(40))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # current list price
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 2))   # unit cost (food + labour share)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    capture_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="CREATED", index=True)  # CREATED/APPROVED/PAID/REFUNDED/FAILED
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    payer_email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="paypal")  # paypal / seed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # price actually charged (captures promos)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    order: Mapped[Order] = relationship(back_populates="items")

    __table_args__ = (Index("ix_items_product", "product_id"),)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)  # idempotency key
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(120), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
