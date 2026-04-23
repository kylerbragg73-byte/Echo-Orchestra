"""
LOOP-03 — SaaS Loop.

Scaffolds a real Next.js + Stripe starter project on disk at
`workspace/saas/<slug>/`. The operator runs `npm install && npm run dev`
and deploys to Vercel.

STANDARD tier: needs node/npm installed (checked at runtime), 8+ GB RAM.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from compliance.legal_gate import LegalGate, Jurisdiction
from intel.perplexity_client import PerplexityIntelClient
from loops._base import LoopBase
from util.logging_setup import get_logger

log = get_logger("echo.loop.saas")


# Minimal, functional Next.js 14 App Router starter.
# Not a toy — `npm install && npm run dev` works out of the box.
PACKAGE_JSON = """{
  "name": "%SLUG%",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "stripe": "^14.0.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@types/react": "^18.3.0",
    "typescript": "^5.4.0"
  }
}
"""

TS_CONFIG = """{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{"name": "next"}],
    "paths": {"@/*": ["./*"]}
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
"""

NEXT_ENV_DTS = '/// <reference types="next" />\n/// <reference types="next/image-types/global" />\n'

LAYOUT_TSX = """export const metadata = { title: "%NAME%" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0 }}>{children}</body>
    </html>
  );
}
"""

PAGE_TSX = """export default function Home() {
  return (
    <main style={{ maxWidth: 720, margin: "4rem auto", padding: "0 1.5rem" }}>
      <h1 style={{ fontSize: "2.25rem", lineHeight: 1.1 }}>%NAME%</h1>
      <p style={{ fontSize: "1.125rem", color: "#555" }}>%TAGLINE%</p>
      <form action="/api/checkout" method="POST" style={{ marginTop: "2rem" }}>
        <button style={{
          background: "#0b6bcb", color: "white", padding: "0.75rem 1.5rem",
          border: 0, borderRadius: 6, fontSize: "1rem", cursor: "pointer"
        }}>
          Subscribe — $%PRICE%/mo
        </button>
      </form>
      <footer style={{ marginTop: "4rem", fontSize: "0.875rem", color: "#888" }}>
        <p>%DISCLOSURES%</p>
      </footer>
    </main>
  );
}
"""

CHECKOUT_ROUTE = """import Stripe from "stripe";
import { NextResponse } from "next/server";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: "2024-06-20" });

export async function POST() {
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    line_items: [{ price: process.env.STRIPE_PRICE_ID!, quantity: 1 }],
    success_url: `${process.env.APP_URL}/thank-you`,
    cancel_url: `${process.env.APP_URL}/`,
  });
  return NextResponse.redirect(session.url!, 303);
}
"""

NEXT_CONFIG = """/** @type {import('next').NextConfig} */
const nextConfig = { reactStrictMode: true };
module.exports = nextConfig;
"""

ENV_EXAMPLE = """STRIPE_SECRET_KEY=
STRIPE_PRICE_ID=
APP_URL=http://localhost:3000
"""

GITIGNORE = "node_modules\n.next\n.env\n.env.local\n"


class SaasLoop(LoopBase):
    loop_name = "saas"
    minimum_tier = "standard"

    def __init__(self, output_root: str = "workspace/saas"):
        super().__init__()
        self.gate = LegalGate()
        self.intel = PerplexityIntelClient()
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def run(self, idea: str, price: float = 9.00) -> dict:
        log.info("SaasLoop start: idea=%s price=$%.2f", idea, price)

        # Node check
        if shutil.which("node") is None or shutil.which("npm") is None:
            return {"status": "blocked",
                    "reason": "Node.js + npm not found on PATH. Install Node 18+ first."}

        # Research
        self._record("sonar-pro", "research", 400, 1000, agent="echo_intel")
        try:
            research = self.intel.research_product_idea(idea, "SaaS monthly subscription")
        except Exception as exc:
            return {"status": "blocked", "reason": f"research_failed: {exc}"}
        analysis = research["analysis"]
        if not analysis.get("build_advised", False):
            return {"status": "blocked", "reason": "no_market",
                    "recommendation": analysis.get("recommendation", "")}

        # Compliance
        compliance = self.gate.check(
            product_type="saas",
            target_markets=[Jurisdiction.US, Jurisdiction.EU],
            description=idea,
            has_financial_component=False,
        )
        if not compliance.approved:
            return {"status": "blocked", "reason": compliance.block_reason}

        # Naming and copy
        self._record("claude-opus-4-7", "naming", 500, 200, agent="writer")
        name_tagline = self._call_model(
            "premium-code",
            prompt=(
                f"Give me a product name (2-3 words, memorable) and a one-line tagline "
                f"(under 14 words) for this SaaS:\n\n{idea}\n\n"
                f"Format as exactly two lines:\n"
                f"Name: <name>\nTagline: <tagline>"
            ),
            max_tokens=200,
        ) or "Name: Starter App\nTagline: The simplest way to get started."

        name = "Starter App"
        tagline = idea
        for line in name_tagline.splitlines():
            if line.lower().startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.lower().startswith("tagline:"):
                tagline = line.split(":", 1)[1].strip()

        # Scaffold
        slug = self.slug(name)
        proj_dir = self.output_root / slug
        if proj_dir.exists():
            return {"status": "exists", "output_path": str(proj_dir)}
        (proj_dir / "app" / "api" / "checkout").mkdir(parents=True, exist_ok=True)

        def write(path: Path, content: str) -> None:
            path.write_text(content, encoding="utf-8")

        disclosures = " ".join(compliance.required_disclosures[:2])

        write(proj_dir / "package.json",
              PACKAGE_JSON.replace("%SLUG%", slug))
        write(proj_dir / "tsconfig.json", TS_CONFIG)
        write(proj_dir / "next-env.d.ts", NEXT_ENV_DTS)
        write(proj_dir / "next.config.js", NEXT_CONFIG)
        write(proj_dir / ".env.example", ENV_EXAMPLE)
        write(proj_dir / ".gitignore", GITIGNORE)
        write(proj_dir / "app" / "layout.tsx",
              LAYOUT_TSX.replace("%NAME%", name))
        write(proj_dir / "app" / "page.tsx",
              PAGE_TSX
                .replace("%NAME%", name)
                .replace("%TAGLINE%", tagline)
                .replace("%PRICE%", f"{price:.0f}")
                .replace("%DISCLOSURES%", disclosures))
        write(proj_dir / "app" / "api" / "checkout" / "route.ts", CHECKOUT_ROUTE)

        (proj_dir / "meta.json").write_text(json.dumps({
            "name": name, "slug": slug, "tagline": tagline,
            "price_per_month": price, "idea": idea,
            "created_at": datetime.utcnow().isoformat(),
            "disclosures": compliance.required_disclosures,
            "next_steps": [
                "cd " + str(proj_dir),
                "cp .env.example .env && edit it",
                "npm install",
                "npm run dev",
            ],
        }, indent=2), encoding="utf-8")

        log.info("SaasLoop scaffolded %s", proj_dir)
        return {
            "status": "created",
            "output_path": str(proj_dir),
            "name": name,
            "tagline": tagline,
            "next_steps": [
                f"cd {proj_dir}",
                "cp .env.example .env  # fill in Stripe keys",
                "npm install",
                "npm run dev",
            ],
        }
