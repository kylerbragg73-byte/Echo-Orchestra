"""
Strategy engine — portfolio decisions based on 30-day performance.

Previous version's comments said "lifetime" but the query pulled last 30 days.
This version is labeled correctly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List

from util.logging_setup import get_logger

log = get_logger("echo.strategy")


class Decision(Enum):
    SCALE = "scale"
    MAINTAIN = "maintain"
    IMPROVE = "improve"
    KILL = "kill"
    CREATE = "create"


@dataclass
class LoopPerformance:
    loop_type: str
    window_days: int
    total_revenue: float
    total_cost: float
    net_profit: float
    product_count: int
    avg_product_profit: float
    success_rate: float


class StrategyEngine:
    def __init__(self, ledger_db: str = "echo_ledger.db"):
        self.ledger_db = ledger_db
        self.rules = {
            "window_days": 30,
            "min_profit_margin": 0.20,
            "kill_threshold_30d": -10.00,
            "scale_threshold_30d": 100.00,
            "max_parallel_loops": 5,
            "exploration_budget": 0.10,
            "safe_budget": 0.70,
            "adjacent_budget": 0.20,
        }

    def analyze_portfolio(self) -> Dict[str, LoopPerformance]:
        cutoff = (datetime.utcnow() - timedelta(days=self.rules["window_days"])).isoformat()
        with sqlite3.connect(self.ledger_db) as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT loop_type,
                       COALESCE(SUM(revenue_usd),0) AS revenue,
                       COALESCE(SUM(cost_usd),0)    AS cost,
                       COUNT(DISTINCT product_id)   AS products,
                       COUNT(CASE WHEN revenue_usd > cost_usd THEN 1 END) AS profitable
                FROM tasks
                WHERE timestamp > ?
                GROUP BY loop_type
                """,
                (cutoff,),
            )
            rows = c.fetchall()

        results: Dict[str, LoopPerformance] = {}
        for loop_type, revenue, cost, products, profitable in rows:
            if not loop_type:
                continue
            net = (revenue or 0) - (cost or 0)
            products = products or 0
            results[loop_type] = LoopPerformance(
                loop_type=loop_type,
                window_days=self.rules["window_days"],
                total_revenue=revenue or 0,
                total_cost=cost or 0,
                net_profit=net,
                product_count=products,
                avg_product_profit=net / products if products else 0.0,
                success_rate=((profitable or 0) / products) if products else 0.0,
            )
        return results

    def make_decisions(self) -> List[Dict]:
        portfolio = self.analyze_portfolio()
        decisions = []
        for loop_type, perf in portfolio.items():
            decision = Decision.MAINTAIN
            reasoning: List[str] = []

            if perf.net_profit < self.rules["kill_threshold_30d"]:
                decision = Decision.KILL
                reasoning.append(
                    f"30-day net ${perf.net_profit:.2f} below kill threshold "
                    f"${self.rules['kill_threshold_30d']:.2f}"
                )
            elif perf.net_profit > self.rules["scale_threshold_30d"]:
                decision = Decision.SCALE
                reasoning.append(
                    f"30-day net ${perf.net_profit:.2f} above scale threshold "
                    f"${self.rules['scale_threshold_30d']:.2f}"
                )
            elif perf.success_rate < 0.5 and perf.product_count > 3:
                decision = Decision.IMPROVE
                reasoning.append(
                    f"Success rate {perf.success_rate:.0%} below 50% across "
                    f"{perf.product_count} products"
                )
            elif perf.success_rate > 0.7 and perf.net_profit > 50:
                decision = Decision.CREATE
                reasoning.append(
                    "High success rate and positive profit — explore adjacent verticals"
                )

            decisions.append({
                "loop_type": loop_type,
                "decision": decision.value,
                "reasoning": reasoning,
                "metrics": {
                    "window_days": perf.window_days,
                    "revenue": perf.total_revenue,
                    "cost": perf.total_cost,
                    "net": perf.net_profit,
                    "success_rate": perf.success_rate,
                },
            })
        return decisions

    def allocate_budget(self, total_budget: float) -> Dict[str, float]:
        portfolio = self.analyze_portfolio()
        allocations: Dict[str, float] = {}
        proven = {k: v for k, v in portfolio.items() if v.net_profit > 0}
        proven_total = sum(v.net_profit for v in proven.values()) or 1
        safe = total_budget * self.rules["safe_budget"]
        for loop_type, perf in proven.items():
            allocations[loop_type] = (perf.net_profit / proven_total) * safe
        allocations["exploration"] = total_budget * self.rules["exploration_budget"]
        allocations["adjacent"] = total_budget * self.rules["adjacent_budget"]
        return allocations
