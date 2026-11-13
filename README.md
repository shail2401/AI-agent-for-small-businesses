# Luke's Diner Copilot

AI business intelligence for a small diner: live dashboard, demand forecasts, a what-if decision simulator,
an LLM copilot that answers from real data, and PayPal sandbox payments that sync automatically.

```
Next.js + TypeScript  ──►  FastAPI  ──►  PostgreSQL
 dashboard / simulator /     │  Pandas analytics · scikit-learn forecast + elasticity
 copilot chat / checkout     │  LLM tool-calling copilot (Anthropic)
                             └─ PayPal Orders API  ◄── PayPal Webhooks
```

## Run it

```bash
cp backend/.env.example backend/.env          # add keys (all optional except for the feature they enable)
cp frontend/.env.local.example frontend/.env.local
docker compose up --build                     # Postgres + API (:8000) + web (:3000)
```
Open http://localhost:3000. On first start the API seeds ~150 days of history (with past price changes and promos so
elasticity can be learned). Dashboard, forecast and simulator work with **no keys**.

Without Docker: run Postgres, then `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
and `cd frontend && npm install && npm run dev`.

## Keys
| Feature | Set |
|---|---|
| Copilot chat | `ANTHROPIC_API_KEY` (model via `LLM_MODEL`) |
| Checkout | `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` (backend) and `NEXT_PUBLIC_PAYPAL_CLIENT_ID` (frontend, same client id) from a PayPal Developer sandbox app |
| Webhooks | `PAYPAL_WEBHOOK_ID` |

### PayPal webhook setup
1. Expose the API: `ngrok http 8000`.
2. In the PayPal Developer dashboard (sandbox app) add a webhook to `https://<ngrok>/api/webhooks/paypal` for
   `CHECKOUT.ORDER.APPROVED`, `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.REFUNDED`, `PAYMENT.CAPTURE.REVERSED`, `PAYMENT.CAPTURE.DENIED`.
3. Copy the webhook ID into `PAYPAL_WEBHOOK_ID`. Signatures are verified through PayPal's verify API; if the ID is unset, verification is skipped (dev only, logged).
4. Pay on **Take an order** with a sandbox buyer account. Refund it in the sandbox and the order flips to REFUNDED.

How sync works: the server prices the cart from the database, creates a PayPal order with `custom_id = our order id`,
and both the capture endpoint and the webhook call one idempotent `mark_paid`. Events are stored by `event_id`, so retries are ignored.

## How the analytics work
- **Analytics** (`services/analytics.py`): Pandas over PAID order lines — KPIs vs previous period, daily series,
  product performance, menu-engineering classes (star / workhorse / puzzle / dog), weekday/hour trends.
- **Forecast** (`services/forecast.py`): per-product Poisson regression (scikit-learn) on trend, weekday and log price.
  A 14-day holdout backtest is compared with a weekday-average baseline and shown on the dashboard.
- **Elasticity**: the log-price coefficient. If history has too little price variation or an implausible sign, a labelled
  category prior is used instead and the UI says so.
- **Simulator** (`services/simulator.py`): `scenario_units = baseline_units × (new_price / price)^elasticity`; reports revenue,
  profit, an elasticity ±0.5 range, and break-even volume. It does not model competitors or cannibalisation.
- **Copilot** (`services/copilot.py`): the LLM calls six tools (summary, products, trends, forecast, simulate, opportunities),
  must answer from their output, and the UI shows each lookup under "The check".

## Limits to know about
- Seed data is synthetic. Replace it by taking sandbox orders or importing history into `orders` / `order_items`.
- "Profit" is gross profit from `products.cost`; edit costs in the table (or `seed.py`) to match your real food and labour costs.
- No auth: add it before exposing the API publicly.
