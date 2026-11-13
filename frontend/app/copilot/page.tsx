"use client";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";

type Evidence = { tool: string; input: unknown; output: unknown };
type Msg = { role: "user" | "assistant"; content: string; evidence?: Evidence[] };

const PROMPTS = [
  "Why did revenue change recently?",
  "Which menu items should I stop promoting?",
  "What happens if I raise burger prices 8%?",
  "Where can I raise prices to make more profit?",
  "What should I prep for next week?",
];
const LABEL: Record<string, string> = {
  get_business_summary: "Checked sales summary", get_product_performance: "Checked product performance",
  get_sales_trends: "Checked sales trends", get_demand_forecast: "Ran demand forecast",
  simulate_decision: "Simulated the change", find_opportunities: "Searched for price opportunities",
};

export default function Copilot() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    const next: Msg[] = [...msgs, { role: "user", content: text }];
    setMsgs(next); setInput(""); setBusy(true);
    try {
      const r = await api<{ answer: string; evidence: Evidence[] }>("/api/copilot/chat", {
        method: "POST", body: JSON.stringify({ messages: next.map(({ role, content }) => ({ role, content })) }),
      });
      setMsgs([...next, { role: "assistant", content: r.answer, evidence: r.evidence }]);
    } catch (e) {
      setMsgs([...next, { role: "assistant", content: `Something went wrong: ${(e as Error).message}` }]);
    } finally { setBusy(false); }
  };

  return (
    <>
      <div className="head"><div>
        <h1>Ask about your diner in plain English</h1>
        <p>Every answer is built from your sales data. Open &ldquo;The check&rdquo; under a reply to see exactly which lookups and numbers it used.</p>
      </div></div>
      <div className="chat">
        {!msgs.length && <div className="prompts">{PROMPTS.map((p) => <button key={p} onClick={() => send(p)}>{p}</button>)}</div>}
        {msgs.map((m, i) => m.role === "user" ? <div key={i} className="msg user">{m.content}</div> : (
          <div key={i} className="msg bot">
            <ReactMarkdown>{m.content}</ReactMarkdown>
            {!!m.evidence?.length && (
              <details className="check">
                <summary>The check: {m.evidence.length} lookup{m.evidence.length > 1 ? "s" : ""}</summary>
                {m.evidence.map((e, j) => (
                  <div key={j} className="line"><div style={{ width: "100%" }}>
                    <strong>{LABEL[e.tool] ?? e.tool}</strong>
                    <pre>{JSON.stringify({ input: e.input, result: e.output }, null, 1).slice(0, 2500)}</pre>
                  </div></div>
                ))}
              </details>
            )}
          </div>
        ))}
        {busy && <div className="msg bot muted" aria-live="polite">Pulling the numbers…</div>}
        <div ref={end} />
        <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
          <textarea rows={2} value={input} placeholder="e.g. Should I run a pancake promo on weekdays?" aria-label="Your question"
            onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }} />
          <button className="btn" disabled={busy || !input.trim()}>Ask</button>
        </form>
      </div>
    </>
  );
}
