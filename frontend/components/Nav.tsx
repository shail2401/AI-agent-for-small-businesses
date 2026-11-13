"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/simulator", label: "What-if simulator" },
  { href: "/copilot", label: "Ask the copilot" },
  { href: "/order", label: "Take an order" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <aside className="rail">
      <div className="sign">Luke&apos;s Diner<small>Business copilot</small></div>
      <nav aria-label="Main">
        {links.map((l) => (
          <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined}>{l.label}</Link>
        ))}
      </nav>
      <div className="foot">PayPal sandbox payments sync here automatically.</div>
    </aside>
  );
}
