export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  } catch {
    throw new Error(`Can't reach the API at ${API}. Start the backend (see README) and reload.`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export const money = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
export const signed = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : `${n >= 0 ? "+" : "−"}${money(Math.abs(n), digits)}`;
export const pct = (n: number | null | undefined) => (n == null ? "–" : `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(1)}%`);

export type Kpis = { revenue: number; transactions: number; aov: number; profit: number; margin_pct: number; units: number };
export type Summary = { days: number; current: Kpis; previous: Kpis; change_pct: Record<string, number | null> };
export type Point = { date: string; revenue: number; profit: number; transactions: number; avg7: number };
export type ProductRow = {
  product_id: number; product: string; category: string; units: number; revenue: number; profit: number;
  revenue_change_pct: number | null; margin_pct: number; revenue_share_pct: number; class: "star" | "workhorse" | "puzzle" | "dog";
};
export type Trends = {
  weekday_avg_revenue: { day: string; revenue: number }[]; best_day: string; slowest_day: string; weekly_growth_pct: number;
  peak_hour: number; category_mix: { category: string; share_pct: number }[];
};
export type Forecast = {
  horizon: number; total_revenue: number; daily: { date: string; revenue: number; lo: number; hi: number }[];
  backtest: { holdout_days: number; model_wape_pct: number; naive_wape_pct: number } | null;
};
export type MenuItem = { id: number; name: string; category: string; price: number; cost: number };
export type SimRow = {
  product_id: number; name: string; changed: boolean; price: number; new_price: number; elasticity: number;
  elasticity_source: "estimated" | "prior"; units_change_pct: number; baseline_profit: number; scenario_profit: number;
  profit_delta: number; profit_range: [number, number]; breakeven_volume_change_pct: number | null;
  baseline_revenue: number; scenario_revenue: number;
};
export type SimResult = {
  horizon_days: number; verdict: string; baseline: { revenue: number; profit: number }; scenario: { revenue: number; profit: number };
  delta: { revenue: number; profit: number; revenue_pct: number | null; profit_pct: number | null; profit_range: [number, number] };
  products: SimRow[]; assumptions: string[];
};
export type RecentOrder = { id: number; total: number; source: string; paid_at: string; payer: string | null };
