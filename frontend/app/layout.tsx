import type { Metadata } from "next";
import { Bricolage_Grotesque, Public_Sans } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

const display = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-display", weight: ["500", "600", "700", "800"] });
const body = Public_Sans({ subsets: ["latin"], variable: "--font-body" });

export const metadata: Metadata = { title: "Luke's Diner Copilot", description: "Sales, profit and what-if decisions for Luke's Diner." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <div className="shell">
          <Nav />
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
