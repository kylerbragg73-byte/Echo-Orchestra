"""Simple model router — first-level decision logic.

For heavier routing (fallbacks, budget caps, retries) the LiteLLM proxy does
the work. This module is just the decision of which logical model to ask for.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RouteDecision:
    provider: str
    model: str
    reason: str


class SimpleRouter:
    def route(self, task_type: str, complexity: str = "medium") -> RouteDecision:
        # Research always goes to Perplexity
        if task_type in ("research", "fact_check", "market_scan", "compliance_update"):
            return RouteDecision("perplexity", "sonar-pro", "live research")

        # Low-stakes bulk
        if task_type in ("data_processing", "qa_testing", "simple_code", "content_draft"):
            return RouteDecision("deepseek", "deepseek-v3.2", "cheap bulk task")

        if complexity == "low":
            return RouteDecision("deepseek", "deepseek-v3.2", "low complexity")

        if complexity == "medium":
            return RouteDecision("xai", "grok-4.20", "balanced")

        if complexity == "high":
            return RouteDecision("anthropic", "claude-opus-4-7", "high complexity synthesis")

        if complexity == "multimodal":
            return RouteDecision("google", "gemini-3.1-pro", "multimodal")

        # Default
        return RouteDecision("deepseek", "deepseek-v3.2", "default")
