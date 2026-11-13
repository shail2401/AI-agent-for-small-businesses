"use client";
import { useEffect, useState } from "react";
import { api, MenuItem, money, pct, signed, SimResult } from "@/lib/api";

type Edit = { price: number; disc: number };

export default function Simulator() {
  const [menu, setMenu] = useState<MenuItem[]>([]);
  const [edits, setEdits] = useState<Record<number, Edit>>({});
  const [horizon, setHorizon] = useState(30);
  const [res, setRes] = useState<SimResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { api<MenuItem[]>("/api/menu").then(setMenu).catch((e) => setError(e.message)); }, []);

  const set = (id: number, k: keyof Edit, v: number) => setEdits((e) => ({ ...e, [id]: { ...(e[id] ?? { price: 0, disc: 0 }), [k]: v } }));
  const preset = (fn: (m: MenuItem) => Edit | null) => {
    const next: Record<number, Edit> = {};
    menu.forEach((m) => { const e = fn(m); if (e) next[m.id] = e; });
    setEdits(next); setRes(null);
  };

  const run = async () => {
    setBusy(true); setError("");
    try {
      const changes = Object.entries(edits).filter(([, e]) => e.price || e.disc)
        .map(([id, e]) => ({ product_id: Number(id), price_change_pct: e.price, discount_pct: e.disc }));
      setRes(await api<SimResult>("/api/simulate", { method: "POST", body: JSON.stringify({ changes, horizon_days: horizon }) }));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const cls = (v: number) => (v > 0 ? "up" : v < 0 ? "down" : "flat");
  return (
    <>
      <div className="head">
        <div>
          <h1>Test a price or promo before you run it</h1>
          <p>Set a price change or a discount on any item. The simulator forecasts normal demand, then adjusts it using how customers have reacted to your past price changes.</p>
        </div>
        <label>Look ahead <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
          {[14, 30, 60].map((d) => <option key={d} value={d}>{d} days</option>)}</select></label>
      </div>
      {error && <div className="notice error" role="alert">{error}</div>}
      <div className="grid g2">
        <div className="card">
          <div className="prompts" style={{ marginBottom: 12 }}>
            <button onClick={() => preset((m) => (m.category === "Mains" ? { price: 5, disc: 0 } : null))}>Raise mains 5%</button>
            <button onClick={() => preset((m) => (m.category === "Breakfast" ? { price: 0, disc: 15 } : null))}>15% off breakfast</button>
            <button onClick={() => preset((m) => (m.category === "Drinks" ? { price: 0, disc: 20 } : null))}>20% off drinks</button>
            <button onClick={() => preset(() => null)}>Clear</button>
          </div>
          <div className="table-wrap"><table>
            <thead><tr><th>Item</th><th className="n">Price</th><th className="n">Price change %</th><th className="n">Discount %</th></tr></thead>
            <tbody>{menu.map((m) => (
              <tr key={m.id}><td>{m.name}</td><td className="n">{money(m.price, 2)}</td>
                <td className="n"><input type="number" aria-label={`${m.name} price change percent`} value={edits[m.id]?.price ?? 0} min={-50} max={100} onChange={(e) => set(m.id, "price", Number(e.target.value))} /></td>
                <td className="n"><input type="number" aria-label={`${m.name} discount percent`} value={edits[m.id]?.disc ?? 0} min={0} max={90} onChange={(e) => set(m.id, "disc", Number(e.target.value))} /></td></tr>
            ))}</tbody>
          </table></div>
          <p><button className="btn" onClick={run} disabled={busy || !menu.length}>{busy ? "Running…" : "Run simulation"}</button></p>
        </div>

        <div className="stack">
          {!res && <div className="card"><h2>Results appear here</h2><p className="muted">Pick a preset or enter your own changes, then run the simulation.</p></div>}
          {res && (<>
            <div className="card">
              <h2>{res.verdict}</h2>
              <p className="sub">Next {res.horizon_days} days compared with changing nothing.</p>
              <div className="grid g2e">
                <div><div className="muted">Revenue</div><div className={`value ${cls(res.delta.revenue)}`} style={{ fontSize: 24, fontFamily: "var(--display)", fontWeight: 700 }}>{signed(res.delta.revenue)}</div><div className="muted">{pct(res.delta.revenue_pct)} · {money(res.scenario.revenue)}</div></div>
                <div><div className="muted">Gross profit</div><div className={`value ${cls(res.delta.profit)}`} style={{ fontSize: 24, fontFamily: "var(--display)", fontWeight: 700 }}>{signed(res.delta.profit)}</div><div className="muted">{pct(res.delta.profit_pct)} · likely {signed(res.delta.profit_range[0])} to {signed(res.delta.profit_range[1])}</div></div>
              </div>
            </div>
            <div className="card">
              <h2>By item</h2>
              {res.products.filter((p) => p.changed).map((p) => (
                <div key={p.product_id} style={{ padding: "10px 0", borderBottom: "1px solid #eef1ee" }}>
                  <strong>{p.name}</strong> {money(p.price, 2)} → {money(p.new_price, 2)}
                  <div className="muted">Units {pct(p.units_change_pct)} · profit <span className={cls(p.profit_delta)}>{signed(p.profit_delta)}</span></div>
                  <div className="muted">
                    {p.breakeven_volume_change_pct != null && <>Needs {pct(p.breakeven_volume_change_pct)} volume to break even on profit. </>}
                    <span className={`tag ${p.elasticity_source === "estimated" ? "est" : ""}`}>elasticity {p.elasticity} {p.elasticity_source === "estimated" ? "learned from your sales" : "category default"}</span>
                  </div>
                </div>
              ))}
              <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>{res.assumptions.join(" ")}</p>
            </div>
          </>)}
        </div>
      </div>
    </>
  );
}
