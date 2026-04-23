"""
LOOP-02 — Content Loop.

Produces a real article markdown file under `workspace/content/`.
Intended for blog posts, newsletters, or Medium / Substack pastes.

LITE tier: runs anywhere Python runs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from compliance.legal_gate import LegalGate, Jurisdiction
from intel.perplexity_client import PerplexityIntelClient
from loops._base import LoopBase
from util.logging_setup import get_logger

log = get_logger("echo.loop.content")


class ContentLoop(LoopBase):
    loop_name = "content"
    minimum_tier = "lite"

    def __init__(self, output_root: str = "workspace/content"):
        super().__init__()
        self.gate = LegalGate()
        self.intel = PerplexityIntelClient()
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def run(self, topic: str, angle: str = "", word_target: int = 1200) -> dict:
        log.info("ContentLoop start: topic=%s angle=%s", topic, angle)

        # Research
        self._record("sonar-pro", "research", 300, 800, agent="echo_intel")
        try:
            report = self.intel.grounded_summary(
                f"Current state of: {topic}. Recent developments, contrarian angles, "
                f"sourced facts. Angle preference: {angle or 'none, give best'}."
            )
        except Exception as exc:
            log.error("Research failed: %s", exc)
            return {"status": "blocked", "reason": f"research_failed: {exc}"}

        # Compliance
        compliance = self.gate.check(
            product_type="article",
            target_markets=[Jurisdiction.US, Jurisdiction.EU],
            description=f"article on {topic}",
        )
        if not compliance.approved:
            return {"status": "blocked", "reason": compliance.block_reason}

        # Draft
        self._record("deepseek-v3.2", "draft", 800, word_target * 2, agent="writer")
        citations_block = "\n".join(f"- {c}" for c in report.citations[:8])
        findings_block = "\n".join(
            f"- {f.title}: {f.snippet[:160]}" for f in report.findings[:6]
        )
        draft = self._call_model(
            "cheap-coder",
            prompt=(
                f"Write a {word_target}-word article about: {topic}.\n"
                f"Angle: {angle or 'whatever is most interesting'}.\n\n"
                f"Use these findings as source material:\n{findings_block}\n\n"
                f"Cite sources inline as [1], [2], etc. matching this list:\n{citations_block}\n\n"
                f"Write in clean Markdown. Start with an H1 title. Do not pad. "
                f"End with a short 'Sources' section listing the citations."
            ),
            system="You are a clear, direct writer. No hype, no filler.",
            max_tokens=3000,
        )
        if not draft:
            return {"status": "failed", "reason": "empty_model_response"}

        # Polish
        self._record("claude-opus-4-7", "polish", 1500, 2000, agent="editor")
        final = self._call_model(
            "premium-code",
            prompt=(
                f"Edit this article for clarity, flow, and tight sentences. "
                f"Keep all facts and citations. Keep the structure. "
                f"Return only the edited article.\n\n---\n{draft}\n---"
            ),
            max_tokens=3000,
        ) or draft

        # Write
        slug = self.slug(topic)
        date = datetime.utcnow().strftime("%Y-%m-%d")
        article_dir = self.output_root / f"{date}-{slug}"
        article_dir.mkdir(parents=True, exist_ok=True)

        article_file = article_dir / "article.md"
        disclosures_block = "\n\n---\n\n" + "\n".join(
            f"_{d}_" for d in compliance.required_disclosures
        )
        article_file.write_text(final + disclosures_block, encoding="utf-8")

        (article_dir / "meta.json").write_text(json.dumps({
            "topic": topic,
            "angle": angle,
            "word_target": word_target,
            "created_at": datetime.utcnow().isoformat(),
            "sources": report.citations,
            "compliance": compliance.required_disclosures,
        }, indent=2), encoding="utf-8")

        log.info("ContentLoop wrote %s", article_dir)
        return {
            "status": "created",
            "output_path": str(article_dir),
            "article_file": str(article_file),
        }
