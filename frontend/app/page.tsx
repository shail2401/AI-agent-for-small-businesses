"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, Forecast, money, pct, Point, ProductRow, RecentOrder, Summary, Trends } from "@/lib/api";

const CLASS_HELP: Record<string, string> = {
  star: "Popular and high margin. Protect it.",
  workhorse: "Popular, thin margin. Test a small price rise.",
  puzzle: "High margin, low sales. Feature it more.",
  dog: "Low sales, low margin. Rework or drop.",
};

function Delta({ v }: { v: number | null | undefined }) {
  const cls = v == null ? "flat" : v > 0.05 ? "up" : v < -0.05 ? "down" : "flat";
  return <span className={`delta ${cls}`}>{v == null ? "no prior data" : `${pct(v)} vs previous period`}</span>;
}

export default function Dashboard() {
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [series, setSeries] = useState<Point[]>([]);
  const [prods, setProds] = useState<ProductRow[]>([]);
  const [trends, setTrends] = useState<Trends | null>(null);
  const [fc, setFc] = useState<Forecast | null>(null);
  const [recent, setRecent] = useState<RecentOrder[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () =>
      Promise.all([
        api<Summary>(`/api/analytics/summary?days=${days}`), api<Point[]>("/api/analytics/timeseries?days=60"),
        api<ProductRow[]>(`/api/analytics/products?days=${days}`), api<Trends>("/api/analytics/trends"),
        api<Forecast>("/api/forecast?horizon=14"), api<RecentOrder[]>("/api/analytics/recent-orders"),
      ]).then(([s, t, p, tr, f, r]) => { setSummary(s); setSeries(t); setProds(p); setTrends(tr); setFc(f); setRecent(r); setError(""); })
        .catch((e) => setError(e.message));
    load();
    const id = setInterval(load, 30000); // picks up PayPal-synced orders
    return () => clearInterval(id);
  }, [days]);

  const chart = useMemo(() => {
    const actual = series.map((p) => ({ date: p.date.slice(5), revenue: p.revenue, avg7: p.avg7 } as Record<string, unknown>));
    const future = (fc?.daily ?? []).map((d) => ({ date: d.date.slice(5), forecast: d.revenue, band: [d.lo, d.hi] }));
    return [...actual, ...future];
  }, [series, fc]);

  if (error) return <div className="notice error" role="alert">{error}</div>;
  if (!summary) return <p className="muted">Loading your numbers…</p>;

  const c = summary.current, ch = summary.change_pct;
  const headline = ch.revenue == null ? "Here is how the diner is doing"
    : `Sales are ${ch.revenue >= 0 ? "up" : "down"} ${Math.abs(ch.revenue).toFixed(1)}% over the last ${days} days`;
  const hours = (h: number) => `${h % 12 || 12}${h < 12 ? "am" : "pm"}`;

  return (
    <>
      <div className="head">
        <div>
          <h1>{headline}</h1>
          <p>
            Gross margin is {c.margin_pct.toFixed(1)}%.
            {trends && <> {trends.best_day} is your strongest day and {hours(trends.peak_hour)} your busiest hour. Weekly sales are trending {pct(trends.weekly_growth_pct)} per week.</>}
          </p>
        </div>
        <div className="seg" role="group" aria-label="Period">
          {[7, 30, 90].map((d) => <button key={d} aria-pressed={days === d} onClick={() => setDays(d)}>{d} days</button>)}
        </div>
      </div>

      <div className="stack">
        <div className="grid g4">
          {[
            ["Revenue", money(c.revenue), ch.revenue], ["Transactions", c.transactions.toLocaleString(), ch.transactions],
            ["Average order value", money(c.aov, 2), ch.aov], ["Gross profit", money(c.profit), ch.profit],
          ].map(([label, value, d]) => (
            <div className="card kpi" key={label as string}>
              <div className="label">{label}</div><div className="value">{value}</div><Delta v={d as number | null} />
            </div>
          ))}
        </div>

        <div className="grid g2">
          <div className="card">
            <h2>Daily sales and 14-day forecast</h2>
            <p className="sub">
              Solid line is actual revenue; dashed line and shaded band are the forecast and its likely range.
              {fc?.backtest && <> On the last {fc.backtest.holdout_days} days the model missed by {fc.backtest.model_wape_pct}% (a simple weekday average missed by {fc.backtest.naive_wape_pct}%).</>}
            </p>
            <div style={{ height: 300 }}>
              <ResponsiveContainer>
                <ComposedChart data={chart} margin={{ left: 0, right: 8, top: 8 }}>
                  <CartesianGrid stroke="#e7ebe7" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} interval={6} />
                  <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `$${Math.round(v / 100) / 10}k`} width={48} />
                  <Tooltip formatter={(v: unknown) => (Array.isArray(v) ? `${money(v[0])} – ${money(v[1])}` : money(Number(v)))} />
                  <Area dataKey="band" name="Forecast range" stroke="none" fill="#e8b13a" fillOpacity={0.25} />
                  <Line dataKey="revenue" name="Revenue" stroke="#0e4d4f" strokeWidth={2} dot={false} />
                  <Line dataKey="avg7" name="7-day average" stroke="#7aa6a2" strokeWidth={1.5} dot={false} />
                  <Line dataKey="forecast" name="Forecast" stroke="#b9801a" strokeWidth={2} strokeDasharray="6 4" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="stack">
            <div className="card">
              <h2>Average sales by weekday</h2>
              <div style={{ height: 150 }}>
                <ResponsiveContainer>
                  <BarChart data={trends?.weekday_avg_revenue ?? []}>
                    <XAxis dataKey="day" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(v: unknown) => money(Number(v))} cursor={{ fill: "#eef3f1" }} />
                    <Bar dataKey="revenue" fill="#0e4d4f" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="card">
              <h2>Latest paid orders</h2>
              <p className="sub">Sandbox PayPal orders appear here as soon as the webhook lands.</p>
              {recent.map((o) => (
                <div key={o.id} className="menu-row" style={{ padding: "6px 0" }}>
                  <span>#{o.id} <span className="tag">{o.source === "paypal" ? "PayPal" : "history"}</span></span>
                  <strong>{money(o.total, 2)}</strong>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <h2>Product performance</h2>
          <p className="sub">Classes compare each item&apos;s sales volume and profit per unit with your menu average.</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Product</th><th>Class</th><th className="n">Units</th><th className="n">Revenue</th><th className="n">Share</th><th className="n">Gross margin</th><th className="n">Revenue change</th></tr></thead>
              <tbody>
                {prods.map((p) => (
                  <tr key={p.product_id}>
                    <td><strong>{p.product}</strong> <span className="muted">{p.category}</span></td>
                    <td><span className={`chip ${p.class}`} title={CLASS_HELP[p.class]}>{p.class}</span></td>
                    <td className="n">{p.units.toLocaleString()}</td><td className="n">{money(p.revenue)}</td>
                    <td className="n">{p.revenue_share_pct.toFixed(1)}%</td><td className="n">{p.margin_pct.toFixed(0)}%</td>
                    <td className={`n ${(p.revenue_change_pct ?? 0) < 0 ? "down" : "up"}`}>{pct(p.revenue_change_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ marginBottom: 0 }}>
            Want to test a change? <Link href="/simulator">Open the simulator</Link> or <Link href="/copilot">ask the copilot</Link>.
          </p>
        </div>
      </div>
    </>
  );
}
