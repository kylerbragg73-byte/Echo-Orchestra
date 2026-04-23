"""
Echo Intel — research layer powered by Perplexity Sonar.

Endpoint: https://api.perplexity.ai/chat/completions (OpenAI-compatible).
Models: sonar, sonar-pro, sonar-reasoning-pro, sonar-deep-research.

Every loop calls this first. If research says no market, the loop bails.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

from pydantic import BaseModel, Field

from util.http import post_json
from util.logging_setup import get_logger

log = get_logger("echo.intel")


class ResearchFinding(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class ResearchReport(BaseModel):
    topic: str
    summary: str = ""
    findings: List[ResearchFinding] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    recommendation: str = ""
    build_advised: bool = False


class PerplexityIntelClient:
    """Thin wrapper around Perplexity chat completions with JSON-mode output."""

    BASE_URL = "https://api.perplexity.ai"

    def __init__(self, api_key: Optional[str] = None, model: str = "sonar-pro"):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.model = model
        if not self.api_key:
            log.warning("PERPLEXITY_API_KEY is not set — research calls will fail")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def grounded_summary(
        self,
        prompt: str,
        search_context_size: str = "medium",
    ) -> ResearchReport:
        """Ask Perplexity to return a JSON-shaped report for the given prompt."""
        system_msg = (
            "You are Echo Intel, a research agent. Return ONLY a JSON object "
            "matching this schema, with no prose before or after: "
            '{"topic": str, "summary": str, '
            '"findings": [{"title": str, "url": str, "snippet": str}], '
            '"risks": [str], "opportunities": [str], "citations": [str], '
            '"recommendation": str, "build_advised": bool}. '
            "Set build_advised to true only when evidence supports real demand "
            "and legal clearance in US/EU."
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "search_context_size": search_context_size,
            "response_format": {"type": "json_object"},
        }
        data = post_json(
            f"{self.BASE_URL}/chat/completions",
            headers=self._headers(),
            json_body=payload,
            timeout=120,
        )
        content = data["choices"][0]["message"]["content"]

        # SAFETY: parse as JSON, never exec/eval.
        if isinstance(content, str):
            try:
                report_dict = json.loads(content)
            except json.JSONDecodeError as exc:
                log.error("Perplexity returned non-JSON content: %s", exc)
                # Salvage what we can
                return ResearchReport(
                    topic=prompt[:80],
                    summary=content[:500],
                    recommendation="Parse failed — review manually",
                    build_advised=False,
                )
        else:
            report_dict = content

        # Normalize: ensure topic is set
        report_dict.setdefault("topic", prompt[:80])
        return ResearchReport(**report_dict)

    def research_product_idea(self, topic: str, objective: str) -> dict:
        prompt = (
            f"Research this product opportunity: {topic}. "
            f"Objective: {objective}. "
            f"Provide competitors, pricing signals, demand signals, risks, "
            f"opportunities, and a clear build / no-build recommendation."
        )
        analysis = self.grounded_summary(prompt)
        return {
            "topic": topic,
            "objective": objective,
            "analysis": analysis.model_dump(),
        }

    def validate_market(
        self, product_description: str, target_geography: str = "US"
    ) -> ResearchReport:
        return self.grounded_summary(
            f"Validate real market demand for: {product_description} "
            f"in {target_geography}. Include active competitors, pricing, and "
            f"signals of paying customers (not just interest)."
        )

    def compliance_scan(
        self, product_type: str, jurisdiction: str
    ) -> ResearchReport:
        return self.grounded_summary(
            f"Current {jurisdiction} legal and compliance requirements as of 2026 "
            f"for selling {product_type}. Include disclosures, licensing, and "
            f"any prohibited categories.",
            search_context_size="high",
        )
