"use client";
import { useEffect, useMemo, useState } from "react";
import { PayPalButtons, PayPalScriptProvider } from "@paypal/react-paypal-js";
import { api, MenuItem, money } from "@/lib/api";

const CLIENT_ID = process.env.NEXT_PUBLIC_PAYPAL_CLIENT_ID ?? "";

export default function OrderPage() {
  const [menu, setMenu] = useState<MenuItem[]>([]);
  const [cart, setCart] = useState<Record<number, number>>({});
  const [done, setDone] = useState<{ order_id: number; total: number } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { api<MenuItem[]>("/api/menu").then(setMenu).catch((e) => setError(e.message)); }, []);
  const lines = useMemo(() => Object.entries(cart).filter(([, q]) => q > 0).map(([id, qty]) => ({ product_id: Number(id), qty })), [cart]);
  const total = lines.reduce((s, l) => s + (menu.find((m) => m.id === l.product_id)?.price ?? 0) * l.qty, 0);
  const bump = (id: number, d: number) => setCart((c) => ({ ...c, [id]: Math.max(0, (c[id] ?? 0) + d) }));

  if (done) return (
    <div className="card" style={{ maxWidth: 520 }}>
      <h2>Order #{done.order_id} paid</h2>
      <p className="muted">{money(done.total, 2)} captured in the PayPal sandbox. It is now in your sales data; the webhook keeps it in sync even if you close this page.</p>
      <button className="btn" onClick={() => { setDone(null); setCart({}); }}>Take another order</button>
    </div>
  );

  return (
    <>
      <div className="head"><div><h1>Take a sandbox order</h1>
        <p>Pay with a PayPal sandbox buyer account. Paid orders flow into the dashboard, forecasts and copilot.</p></div></div>
      {error && <div className="notice error" role="alert">{error}</div>}
      {!CLIENT_ID && <div className="notice" style={{ marginBottom: 16 }}>Add <code>NEXT_PUBLIC_PAYPAL_CLIENT_ID</code> to <code>frontend/.env.local</code> to enable PayPal buttons.</div>}
      <div className="grid g2">
        <div className="card">
          {menu.map((m) => (
            <div className="menu-row" key={m.id}>
              <div><strong>{m.name}</strong><div className="muted">{m.category}</div></div>
              <div className="stepper">
                <span>{money(m.price, 2)}</span>
                <button aria-label={`Remove ${m.name}`} onClick={() => bump(m.id, -1)}>−</button>
                <span aria-live="polite" style={{ minWidth: 16, textAlign: "center" }}>{cart[m.id] ?? 0}</span>
                <button aria-label={`Add ${m.name}`} onClick={() => bump(m.id, 1)}>+</button>
              </div>
            </div>
          ))}
        </div>
        <div className="card" style={{ alignSelf: "start" }}>
          <h2>Total {money(total, 2)}</h2>
          <p className="sub">{lines.length ? `${lines.reduce((s, l) => s + l.qty, 0)} items` : "Add items to pay"}</p>
          {CLIENT_ID && lines.length > 0 && (
            <PayPalScriptProvider options={{ clientId: CLIENT_ID, currency: "USD", intent: "capture" }}>
              <PayPalButtons key={JSON.stringify(lines)} style={{ layout: "vertical" }}
                createOrder={async () => (await api<{ id: string }>("/api/checkout/orders", { method: "POST", body: JSON.stringify({ items: lines }) })).id}
                onApprove={async (data) => setDone(await api(`/api/checkout/orders/${data.orderID}/capture`, { method: "POST" }))}
                onError={(e) => setError(String((e as { message?: string }).message ?? "PayPal checkout failed"))} />
            </PayPalScriptProvider>
          )}
        </div>
      </div>
    </>
  );
}
