"""
Financial ledger. Every task writes a row. Every sale writes a row.
The daily_summary table is derived.

Cost table is for April 2026 published prices. The self-upgrade engine
updates it automatically via the same workflow that updates the router.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from util.logging_setup import get_logger

log = get_logger("echo.ledger")


class ModelTier(Enum):
    CHEAP = "cheap"
    STANDARD = "standard"
    PREMIUM = "premium"


# Published per-million-token pricing, April 2026. Update via self_upgrade engine.
COST_TABLE = {
    # Premium
    "claude-opus-4-7": {"input": 5.00, "output": 25.00, "tier": ModelTier.PREMIUM},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00, "tier": ModelTier.PREMIUM},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "tier": ModelTier.PREMIUM},
    "gpt-5.4": {"input": 3.00, "output": 12.00, "tier": ModelTier.PREMIUM},
    "gemini-3.1-pro": {"input": 2.00, "output": 12.00, "tier": ModelTier.PREMIUM},

    # Standard
    "grok-4.20": {"input": 2.00, "output": 8.00, "tier": ModelTier.STANDARD},
    "kimi-k2.6": {"input": 0.50, "output": 1.50, "tier": ModelTier.STANDARD},

    # Cheap
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "tier": ModelTier.CHEAP},
    "deepseek-v3.2": {"input": 0.28, "output": 0.42, "tier": ModelTier.CHEAP},
    "llama-4-scout-local": {"input": 0.00, "output": 0.00, "tier": ModelTier.CHEAP},

    # Research
    "sonar-pro": {"input": 3.00, "output": 15.00, "tier": ModelTier.STANDARD},
    "sonar": {"input": 1.00, "output": 1.00, "tier": ModelTier.CHEAP},
}


@dataclass
class TaskRecord:
    task_id: str
    loop_type: str
    model_used: str
    tokens_in: int
    tokens_out: int
    cost_usd: float = 0.0
    revenue_usd: float = 0.0
    status: str = "pending"
    timestamp: str = ""
    product_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    agent_name: str = "system"
    action_type: str = "task"


class FinancialLedger:
    def __init__(self, db_path: str = "echo_ledger.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    parent_task_id TEXT,
                    loop_type TEXT,
                    agent_name TEXT,
                    action_type TEXT,
                    model_used TEXT,
                    tokens_in INTEGER,
                    tokens_out INTEGER,
                    cost_usd REAL,
                    revenue_usd REAL,
                    status TEXT,
                    timestamp TEXT,
                    product_id TEXT,
                    jurisdiction TEXT,
                    compliance_disclosures TEXT
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS ix_tasks_ts ON tasks(timestamp)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_tasks_loop ON tasks(loop_type)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS daily_summary (
                    date TEXT PRIMARY KEY,
                    total_cost REAL,
                    total_revenue REAL,
                    net_profit REAL,
                    active_loops INTEGER,
                    model_breakdown TEXT
                )
            """)
            conn.commit()

    def _calculate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        pricing = COST_TABLE.get(model)
        if not pricing:
            log.warning("Unknown model %s — cost recorded as 0", model)
            return 0.0
        return round(
            (tokens_in / 1_000_000) * pricing["input"]
            + (tokens_out / 1_000_000) * pricing["output"],
            6,
        )

    def log_task(
        self,
        task: TaskRecord,
        jurisdiction: str = "us",
        disclosures: Optional[List[str]] = None,
    ) -> float:
        # Only overwrite cost if it wasn't pre-set (eg a revenue row)
        if task.cost_usd == 0.0 and (task.tokens_in or task.tokens_out):
            task.cost_usd = self._calculate_cost(
                task.model_used, task.tokens_in, task.tokens_out
            )
        if not task.timestamp:
            task.timestamp = datetime.utcnow().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                task.task_id, task.parent_task_id, task.loop_type,
                task.agent_name, task.action_type, task.model_used,
                task.tokens_in, task.tokens_out, task.cost_usd,
                task.revenue_usd, task.status, task.timestamp,
                task.product_id, jurisdiction, json.dumps(disclosures or []),
            ))
            conn.commit()

        self._update_daily_summary()
        return task.cost_usd

    def _update_daily_summary(self) -> None:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COALESCE(SUM(cost_usd),0), COALESCE(SUM(revenue_usd),0), "
                "COUNT(DISTINCT loop_type) FROM tasks WHERE DATE(timestamp) = ?",
                (today,),
            )
            total_cost, total_revenue, active = c.fetchone()

            c.execute(
                "SELECT model_used, COALESCE(SUM(cost_usd),0) FROM tasks "
                "WHERE DATE(timestamp) = ? GROUP BY model_used",
                (today,),
            )
            breakdown = {row[0]: row[1] for row in c.fetchall()}

            c.execute(
                "INSERT OR REPLACE INTO daily_summary VALUES (?,?,?,?,?,?)",
                (today, total_cost, total_revenue,
                 total_revenue - total_cost, active, json.dumps(breakdown)),
            )
            conn.commit()

    def get_profit_loss(self, days: int = 7) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT date, total_cost, total_revenue, net_profit "
                "FROM daily_summary ORDER BY date DESC LIMIT ?",
                (days,),
            )
            rows = c.fetchall()

        if not rows:
            return {
                "period_days": days,
                "total_cost": 0.0,
                "total_revenue": 0.0,
                "net_profit": 0.0,
                "daily_breakdown": [],
            }

        return {
            "period_days": days,
            "total_cost": sum(r[1] or 0 for r in rows),
            "total_revenue": sum(r[2] or 0 for r in rows),
            "net_profit": sum(r[3] or 0 for r in rows),
            "daily_breakdown": rows,
        }

    def should_halt(self) -> bool:
        """Survival rule #1: halt if 7-day moving average profit is negative."""
        pnl = self.get_profit_loss(7)
        if pnl["period_days"] == 0:
            return False
        return pnl["net_profit"] < 0 and len(pnl["daily_breakdown"]) >= 7

    def daily_budget_breached(self, tier: ModelTier, caps: dict) -> bool:
        """Survival rule #2: per-tier daily budget caps."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tier_models = [m for m, p in COST_TABLE.items() if p["tier"] == tier]
        if not tier_models:
            return False
        placeholders = ",".join("?" * len(tier_models))
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                f"SELECT COALESCE(SUM(cost_usd),0) FROM tasks "
                f"WHERE DATE(timestamp) = ? AND model_used IN ({placeholders})",
                (today, *tier_models),
            )
            spend = c.fetchone()[0] or 0.0
        cap = caps.get(tier.value, float("inf"))
        return spend >= cap

    def get_budget_recommendation(self, task_complexity: str) -> str:
        if task_complexity == "simple":
            return "deepseek-v3.2"
        elif task_complexity == "standard":
            return "kimi-k2.6"
        else:
            return "claude-opus-4-7"
