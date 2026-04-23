"""
Human loop. The operator types frustrations, desires, opinions, observations.
Echo extracts an idea and classifies it. When two sparks in the same category
contradict each other, mark a 'divergence' — opportunity for parallel products
aimed at different preference tribes.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List

from util.logging_setup import get_logger

log = get_logger("echo.human")


class InputType(Enum):
    FRUSTRATION = "frustration"
    DESIRE = "desire"
    OPINION = "opinion"
    OBSERVATION = "observation"


@dataclass
class HumanSpark:
    spark_id: str
    human_id: str
    input_type: InputType
    raw_text: str
    timestamp: str
    emotional_intensity: float
    category: str
    extracted_idea: str
    market_validated: bool = False
    spawned_products: List[str] = field(default_factory=list)


_CATEGORY_KEYWORDS = {
    "productivity": ["task", "todo", "schedule", "calendar", "focus", "distract"],
    "finance": ["money", "budget", "invoice", "expense", "tax"],
    "fitness": ["workout", "exercise", "gym", "run", "weight"],
    "writing": ["write", "blog", "article", "book", "story"],
    "dev": ["code", "bug", "deploy", "git", "api"],
    "creative": ["draw", "paint", "music", "design", "art"],
}


class HumanLoop:
    def __init__(self, db_path: str = "human_sparks.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sparks (
                    spark_id TEXT PRIMARY KEY,
                    human_id TEXT,
                    input_type TEXT,
                    raw_text TEXT,
                    timestamp TEXT,
                    emotional_intensity REAL,
                    category TEXT,
                    extracted_idea TEXT,
                    market_validated BOOLEAN,
                    spawned_products TEXT,
                    divergence_group TEXT
                )
            """)
            conn.commit()

    def capture_spark(self, human_input: str, human_id: str = "anonymous") -> HumanSpark:
        analysis = self._analyze_input(human_input)
        spark = HumanSpark(
            spark_id=f"spark_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}",
            human_id=human_id,
            input_type=analysis["type"],
            raw_text=human_input,
            timestamp=datetime.utcnow().isoformat(),
            emotional_intensity=analysis["intensity"],
            category=analysis["category"],
            extracted_idea=analysis["idea"],
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sparks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (spark.spark_id, spark.human_id, spark.input_type.value,
                 spark.raw_text, spark.timestamp, spark.emotional_intensity,
                 spark.category, spark.extracted_idea, spark.market_validated,
                 json.dumps(spark.spawned_products), None),
            )
            conn.commit()
        self._check_divergence(spark)
        log.info("Spark captured: [%s/%s] %s",
                 spark.category, spark.input_type.value, spark.extracted_idea[:80])
        return spark

    def _analyze_input(self, text: str) -> Dict:
        tl = text.lower()
        if "tired of" in tl or "frustrated" in tl or "hate" in tl or "annoy" in tl:
            input_type, intensity = InputType.FRUSTRATION, 0.8
        elif "wish" in tl or "want" in tl or "need" in tl:
            input_type, intensity = InputType.DESIRE, 0.7
        elif "should" in tl or "think" in tl or "believe" in tl:
            input_type, intensity = InputType.OPINION, 0.6
        else:
            input_type, intensity = InputType.OBSERVATION, 0.4

        category = "general"
        for cat, kws in _CATEGORY_KEYWORDS.items():
            if any(k in tl for k in kws):
                category = cat
                break

        idea = text
        for prefix in ("I'm tired of ", "I hate ", "I wish ", "I want ",
                       "I think ", "I need "):
            if idea.startswith(prefix):
                idea = idea[len(prefix):]
                break
        return {"type": input_type, "intensity": intensity,
                "category": category, "idea": idea}

    def _check_divergence(self, new_spark: HumanSpark) -> None:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT spark_id, extracted_idea FROM sparks "
                "WHERE category = ? AND spark_id != ?",
                (new_spark.category, new_spark.spark_id),
            )
            for existing_id, existing_idea in c.fetchall():
                if self._is_contradictory(new_spark.extracted_idea, existing_idea):
                    group_id = f"diverge_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
                    c.execute("UPDATE sparks SET divergence_group = ? WHERE spark_id = ?",
                              (group_id, new_spark.spark_id))
                    c.execute("UPDATE sparks SET divergence_group = ? WHERE spark_id = ?",
                              (group_id, existing_id))
                    conn.commit()
                    log.info("Divergence: %s ↔ %s", existing_idea[:60],
                             new_spark.extracted_idea[:60])
                    return

    @staticmethod
    def _is_contradictory(idea_a: str, idea_b: str) -> bool:
        # Placeholder — a real version would call an LLM for semantic contradiction.
        opposites = [
            ("async", "sync"), ("video", "text"), ("manual", "automated"),
            ("simple", "complex"), ("cheap", "premium"), ("fast", "thorough"),
            ("minimal", "feature-rich"), ("private", "public"),
        ]
        al, bl = idea_a.lower(), idea_b.lower()
        for x, y in opposites:
            if (x in al and y in bl) or (y in al and x in bl):
                return True
        return False

    def get_tribal_opportunities(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT divergence_group,
                       GROUP_CONCAT(spark_id) AS sparks,
                       GROUP_CONCAT(extracted_idea, '|||') AS ideas
                FROM sparks
                WHERE divergence_group IS NOT NULL
                GROUP BY divergence_group
                HAVING COUNT(*) >= 2
            """)
            return [{
                "group_id": row[0],
                "sparks": row[1].split(","),
                "ideas": row[2].split("|||"),
                "strategy": "parallel_products",
            } for row in c.fetchall()]

    def get_high_intensity_sparks(self, min_intensity: float = 0.7) -> List[HumanSpark]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM sparks WHERE emotional_intensity >= ? "
                "ORDER BY emotional_intensity DESC",
                (min_intensity,),
            )
            return [HumanSpark(
                spark_id=row[0], human_id=row[1],
                input_type=InputType(row[2]), raw_text=row[3],
                timestamp=row[4], emotional_intensity=row[5],
                category=row[6], extracted_idea=row[7],
                market_validated=bool(row[8]),
                spawned_products=json.loads(row[9]) if row[9] else [],
            ) for row in c.fetchall()]
