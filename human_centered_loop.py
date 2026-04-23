"""
LOOP-04 — Human-Centered Loop.

Reads high-intensity sparks from the human_loop database and routes each
one to the loop most likely to turn it into a product. The goal is that
the operator's frustrations and desires become shippable things without
the operator having to manually kick off each build.
"""

from __future__ import annotations

from typing import List

from agents.human_loop import HumanLoop, HumanSpark
from loops._base import LoopBase
from loops.digital_product_loop import DigitalProductLoop
from loops.content_loop import ContentLoop
from util.logging_setup import get_logger

log = get_logger("echo.loop.human")


class HumanCenteredLoop(LoopBase):
    loop_name = "human_centered"
    minimum_tier = "lite"

    def __init__(self):
        super().__init__()
        self.human_loop = HumanLoop()
        self.dp_loop = DigitalProductLoop()
        self.content_loop = ContentLoop()

    def run(self, min_intensity: float = 0.7, max_per_run: int = 3) -> dict:
        sparks: List[HumanSpark] = self.human_loop.get_high_intensity_sparks(min_intensity)
        if not sparks:
            return {"status": "nothing_to_do", "processed": 0}

        results = []
        for spark in sparks[:max_per_run]:
            route = self._route(spark)
            log.info("Spark '%s' -> %s", spark.extracted_idea[:60], route)
            try:
                if route == "digital_product":
                    res = self.dp_loop.run(niche=spark.extracted_idea,
                                           product_type=self._infer_product_type(spark))
                elif route == "content":
                    res = self.content_loop.run(topic=spark.extracted_idea,
                                                angle=spark.input_type.value)
                else:
                    res = {"status": "unhandled", "route": route}
                results.append({"spark_id": spark.spark_id, "route": route, "result": res})
            except Exception as exc:
                log.error("Spark run failed: %s", exc)
                results.append({"spark_id": spark.spark_id, "route": route,
                                "result": {"status": "error", "error": str(exc)}})

        return {"status": "ran", "processed": len(results), "results": results}

    @staticmethod
    def _route(spark: HumanSpark) -> str:
        # Frustrations and desires about concrete tools -> product
        # Observations and opinions -> content
        if spark.input_type.value in ("frustration", "desire"):
            return "digital_product"
        return "content"

    @staticmethod
    def _infer_product_type(spark: HumanSpark) -> str:
        t = spark.extracted_idea.lower()
        if "template" in t or "checklist" in t or "tracker" in t:
            return "notion_template"
        if "guide" in t or "how to" in t or "tutorial" in t:
            return "pdf_guide"
        return "notion_template"
