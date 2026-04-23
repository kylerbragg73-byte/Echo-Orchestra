"""
Echo-Orchestra core — wires device profile, ledger, tax, compliance, router,
strategy, human loop, loops, and self-upgrade into a single object.

Honors:
  - human_config.json `loops_enabled` toggles
  - device_tier minimum requirements per loop
  - survival rules (budget, profit, kill thresholds)
  - upgrade budget cap (rule #7)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from util.logging_setup import setup_logging, get_logger
from ledger.ledger import FinancialLedger, TaskRecord, ModelTier
from ledger.tax_module import HumanTaxModule
from compliance.legal_gate import LegalGate, Jurisdiction
from intel.perplexity_client import PerplexityIntelClient
from orchestration.strategy import StrategyEngine
from router.simple_router import SimpleRouter
from agents.human_loop import HumanLoop
from platform_tier.device_tier import DeviceProfile, DeviceTier, TIER_ORDER
from platform_tier.self_upgrade import SelfUpgradeEngine

setup_logging()
log = get_logger("echo.core")


# Registry of all known loops. key is human_config.loops_enabled key,
# value is (module_path, class_name, minimum_tier_string)
LOOP_REGISTRY = {
    "digital_product_loop": ("loops.digital_product_loop", "DigitalProductLoop", "lite"),
    "content_loop":         ("loops.content_loop",         "ContentLoop",        "lite"),
    "saas_loop":            ("loops.saas_loop",            "SaasLoop",           "standard"),
    "human_centered_loop":  ("loops.human_centered_loop",  "HumanCenteredLoop",  "lite"),
    "game_loop":            ("loops.game_loop",            "GameLoop",           "workstation"),
    "movie_loop":           ("loops.movie_loop",           "MovieLoop",          "workstation"),
}


DEFAULT_DAILY_CAPS = {
    "cheap":    5.00,
    "standard": 10.00,
    "premium":  50.00,
}


class EchoSystem:
    def __init__(self, config_path: str = "human_config.json"):
        self.config_path = config_path
        self.config = self._load_config()

        # Device profile — classifies host and determines capabilities
        self.device = DeviceProfile()
        log.info("Echo online. Tier: %s", self.device.tier.value)

        # Financial + tax
        self.ledger = FinancialLedger()
        self.tax_module = HumanTaxModule(config_path=config_path)

        # Research + compliance + routing
        self.intel = PerplexityIntelClient()
        self.gate = LegalGate()
        self.router = SimpleRouter()
        self.strategy = StrategyEngine()

        # Human loop
        self.human_loop = HumanLoop()

        # Self-upgrade — pass device so it knows what it can scan
        self.upgrader = SelfUpgradeEngine(
            config_path=config_path, device_profile=self.device,
        )

        # Scheduler is NOT started automatically — operator opts in.

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            log.warning("%s missing — using defaults", self.config_path)
            return {}

    # -- tier and capability gating --

    def loop_available(self, loop_key: str) -> bool:
        """A loop is available iff: registered, human-enabled, AND host tier is sufficient."""
        if loop_key not in LOOP_REGISTRY:
            return False
        enabled = self.config.get("loops_enabled", {}).get(loop_key, False)
        if not enabled:
            return False
        _, _, min_tier_str = LOOP_REGISTRY[loop_key]
        required_tier = DeviceTier(min_tier_str)
        host_rank = TIER_ORDER.index(self.device.tier)
        needed_rank = TIER_ORDER.index(required_tier)
        return host_rank >= needed_rank

    def available_loops(self) -> List[str]:
        return [k for k in LOOP_REGISTRY if self.loop_available(k)]

    def get_loop(self, loop_key: str):
        """Import + instantiate a loop. Raises if not available."""
        if not self.loop_available(loop_key):
            raise RuntimeError(f"Loop '{loop_key}' not available on this host / config")
        module_path, class_name, _ = LOOP_REGISTRY[loop_key]
        module = __import__(module_path, fromlist=[class_name])
        cls = getattr(module, class_name)
        return cls()

    # -- public API --

    def research(self, topic: str, objective: str = "") -> dict:
        return self.intel.research_product_idea(topic, objective)

    def process_revenue(self, amount: float, description: str = "") -> dict:
        task = TaskRecord(
            task_id=f"rev_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}",
            loop_type="revenue",
            model_used="manual",
            tokens_in=0, tokens_out=0,
            revenue_usd=amount,
            agent_name="operator",
            action_type="revenue",
            status="paid",
        )
        self.ledger.log_task(task)

        pnl = self.ledger.get_profit_loss(days=30)
        # Simple approach: any positive incremental revenue goes through profit split
        # based on its proportional contribution to the 30-day net profit.
        split = self.tax_module.process_profit(amount)
        log.info("Revenue recorded: $%.2f — %s", amount, description)
        return {"amount": amount, "description": description,
                "split": split, "thirty_day_net": pnl["net_profit"]}

    def survival_check(self) -> dict:
        """Run the survival rules. Returns current health and any blocks."""
        pnl = self.ledger.get_profit_loss(days=7)
        halted_7d = self.ledger.should_halt()
        caps = self.config.get("daily_caps", DEFAULT_DAILY_CAPS)
        tier_status = {
            tier.value: self.ledger.daily_budget_breached(tier, caps)
            for tier in ModelTier
        }
        return {
            "seven_day_net": pnl["net_profit"],
            "maintenance_mode": halted_7d,
            "tier_caps_breached": tier_status,
            "active_loops_count": len([
                k for k, v in self.config.get("loops_enabled", {}).items() if v
            ]),
            "max_parallel_loops": 5,
        }

    def weekly_upgrade_check(self) -> dict:
        """Scan for upgrade candidates, auto-apply the low-risk ones within budget,
        queue the rest for human approval."""
        candidates = self.upgrader.scan_candidates()
        applied, pending = [], []
        for c in candidates:
            result = self.upgrader.apply(c)
            status = result.get("status")
            if status == "applied":
                applied.append(result)
            elif status in ("pending_human_approval", "blocked_budget"):
                pending.append({**result, "component": c.component,
                                "from": c.current_version, "to": c.latest_version,
                                "risk": c.risk})
        log.info("Upgrade scan: %d candidates, %d applied, %d pending",
                 len(candidates), len(applied), len(pending))
        return {
            "scanned": len(candidates),
            "applied": applied,
            "pending_human": pending,
            "budget": {
                "business_reserve_balance": self.upgrader.get_business_reserve_balance(),
                "month_spent": self.upgrader.monthly_spend(),
                "month_inflow": self.upgrader.monthly_inflow(),
            },
        }

    def status(self) -> dict:
        """One-call health dump — useful for a dashboard or CLI."""
        return {
            "device": self.device.summary(),
            "survival": self.survival_check(),
            "ledger_7d": self.ledger.get_profit_loss(days=7),
            "ledger_30d": self.ledger.get_profit_loss(days=30),
            "tax": self.tax_module.get_human_dashboard(),
            "available_loops": self.available_loops(),
            "pending_upgrades": self.upgrader.list_pending_approvals(),
        }


# -- CLI --

def _cli() -> int:
    p = argparse.ArgumentParser(description="Echo-Orchestra")
    p.add_argument("--init", action="store_true",
                   help="Initialize DBs, print device tier, exit.")
    p.add_argument("--status", action="store_true",
                   help="Print current system status as JSON.")
    p.add_argument("--upgrade-check", action="store_true",
                   help="Run a self-upgrade scan and apply low-risk items.")
    p.add_argument("--start-scheduler", action="store_true",
                   help="Start the payout scheduler (foreground).")
    args = p.parse_args()

    echo = EchoSystem()

    if args.init:
        print(json.dumps(echo.device.summary(), indent=2))
        print(f"\nAvailable loops: {echo.available_loops()}")
        return 0
    if args.status:
        print(json.dumps(echo.status(), indent=2, default=str))
        return 0
    if args.upgrade_check:
        print(json.dumps(echo.weekly_upgrade_check(), indent=2))
        return 0
    if args.start_scheduler:
        echo.tax_module.start_scheduler()
        log.info("Scheduler running. Ctrl-C to stop.")
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            echo.tax_module.stop_scheduler()
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
