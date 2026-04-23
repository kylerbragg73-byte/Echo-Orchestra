"""
LOOP-01 — Digital Product Loop.

Primary entry point for anyone starting with Echo. Runs on LITE tier and up
(no Docker required, 4+ GB RAM). Produces a real file on disk at
`workspace/products/<slug>/` — not a link to a nonexistent URL.

Pipeline:
  1. Research (Perplexity)
  2. Compliance gate
  3. Ideation (cheap model)
  4. Build (premium model)
  5. QA pass (cheap model)
  6. Write to disk with disclosures appended

Revenue step (upload to Gumroad/Payhip) stays manual — Echo doesn't hold
any marketplace credentials on your behalf.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from compliance.legal_gate import LegalGate, Jurisdiction
from intel.perplexity_client import PerplexityIntelClient
from loops._base import LoopBase
from util.logging_setup import get_logger

log = get_logger("echo.loop.digital")


class DigitalProductLoop(LoopBase):
    loop_name = "digital_product"
    minimum_tier = "lite"

    def __init__(self, output_root: str = "workspace/products"):
        super().__init__()
        self.gate = LegalGate()
        self.intel = PerplexityIntelClient()
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.jurisdictions = [Jurisdiction.US, Jurisdiction.EU]

    def run(self, niche: str, product_type: str = "notion_template") -> dict:
        log.info("DigitalProductLoop start: niche=%s type=%s", niche, product_type)

        # 1. Research
        self._record("sonar-pro", "research", 400, 1000, agent="echo_intel")
        try:
            research = self.intel.research_product_idea(niche, product_type)
        except Exception as exc:
            log.error("Research failed: %s", exc)
            return {"status": "blocked", "reason": f"research_failed: {exc}"}
        analysis = research["analysis"]
        if not analysis.get("build_advised", False):
            log.info("Research says no build: %s", analysis.get("recommendation", ""))
            return {
                "status": "blocked",
                "reason": "no_market",
                "recommendation": analysis.get("recommendation", ""),
            }

        # 2. Compliance
        description = f"{product_type} for {niche} market"
        compliance = self.gate.check(
            product_type=product_type,
            target_markets=self.jurisdictions,
            description=description,
        )
        if not compliance.approved:
            return {"status": "blocked", "reason": compliance.block_reason}

        # 3. Ideation
        self._record("deepseek-v3.2", "ideation", 500, 1000, agent="builder")
        ideas = self._call_model(
            "cheap-coder",
            prompt=f"Give me 3 specific {product_type} ideas for the {niche} niche. "
                   f"Each: title, 1-line value proposition, who exactly buys it.",
            system="You are a concise product ideator. Return a numbered list.",
        ) or f"1. {niche} starter pack\n2. {niche} tracker\n3. {niche} checklist"

        # 4. Build
        self._record("claude-opus-4-7", "build", 2000, 3000, agent="builder")
        product_body = self._call_model(
            "premium-code",
            prompt=(
                f"Build a complete {product_type} for the {niche} niche. "
                f"Base it on the first of these ideas:\n\n{ideas}\n\n"
                f"Write the entire product as clean Markdown with clear "
                f"H1/H2/H3 headings, sections, tables where useful, and "
                f"actionable content. No meta-commentary, no 'here is your product' "
                f"preamble — just the product itself, ready to paste into Notion."
            ),
            system="You produce finished, sellable digital products. No fluff.",
            max_tokens=4000,
        )
        if not product_body:
            return {"status": "failed", "reason": "empty_model_response"}

        # 5. QA pass
        self._record("deepseek-v3.2", "qa", 1000, 500, agent="qa")
        qa_notes = self._call_model(
            "cheap-coder",
            prompt=(
                f"Review this {product_type} for clarity, typos, and missing "
                f"sections. Return a short bullet list of issues only.\n\n"
                f"---\n{product_body}\n---"
            ),
        )

        # 6. Write to disk
        slug = self.slug(f"{niche}-{product_type}")
        product_dir = self.output_root / slug
        product_dir.mkdir(parents=True, exist_ok=True)

        product_file = product_dir / "product.md"
        disclosures_block = "\n\n---\n\n## Disclosures\n\n" + "\n".join(
            f"- {d}" for d in compliance.required_disclosures
        )
        product_file.write_text(product_body + disclosures_block, encoding="utf-8")

        meta_file = product_dir / "meta.json"
        meta = {
            "slug": slug,
            "niche": niche,
            "product_type": product_type,
            "created_at": datetime.utcnow().isoformat(),
            "research_recommendation": analysis.get("recommendation", ""),
            "compliance": {
                "risk_level": compliance.risk_level.value,
                "required_disclosures": compliance.required_disclosures,
                "required_actions": compliance.required_actions,
            },
        }
        import json
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        qa_file = product_dir / "qa_notes.md"
        qa_file.write_text(qa_notes or "_(qa pass returned empty)_", encoding="utf-8")

        log.info("DigitalProductLoop wrote %s", product_dir)
        return {
            "status": "created",
            "output_path": str(product_dir),
            "product_file": str(product_file),
            "meta_file": str(meta_file),
            "compliance_risk": compliance.risk_level.value,
        }
