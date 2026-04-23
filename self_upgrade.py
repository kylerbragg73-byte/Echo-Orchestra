"""
Self-upgrade engine.

Scans for:
  - outdated pip packages (always)
  - outdated docker images (when docker is available)
  - newer model IDs at registered providers (stub — requires Echo Intel call)

Applies low-risk patch-version library upgrades automatically within budget.
Anything larger — major version bumps, Docker images, model ID swaps —
goes to the human approval queue.

Budget is drawn from the business_reserve table in human_tax.db. The caps
come from human_config.json's self_upgrade section.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from util.logging_setup import get_logger

log = get_logger("echo.upgrade")


@dataclass
class UpgradeCandidate:
    component: str           # e.g. "lib:requests", "image:litellm", "model:anthropic"
    current_version: str
    latest_version: str
    cost_usd: float
    risk: str                # "low" | "medium" | "high"
    requires_human: bool
    notes: str = ""


class SelfUpgradeEngine:
    def __init__(
        self,
        tax_db: str = "human_tax.db",
        upgrade_db: str = "echo_upgrades.db",
        config_path: str = "human_config.json",
        device_profile=None,
    ):
        self.tax_db = tax_db
        self.upgrade_db = upgrade_db
        self.config_path = config_path
        self.device_profile = device_profile
        self._init_db()
        self.config = self._load_config()

    def _load_config(self) -> dict:
        defaults = {
            "enabled": True,
            "auto_apply_risk": "low",
            "max_single_upgrade_pct_of_reserve": 0.10,
            "max_monthly_upgrade_pct_of_reserve": 0.30,
            "human_approval_required_above_usd": 25.00,
            "scan_frequency": "weekly",
        }
        try:
            with open(self.config_path, "r") as f:
                cfg = json.load(f).get("self_upgrade", {})
            return {**defaults, **cfg}
        except FileNotFoundError:
            return defaults

    def _init_db(self) -> None:
        with sqlite3.connect(self.upgrade_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS upgrades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT, component TEXT,
                    from_version TEXT, to_version TEXT,
                    cost_usd REAL, risk TEXT, status TEXT,
                    human_approved BOOLEAN,
                    rollback_version TEXT, notes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT, component TEXT,
                    from_version TEXT, to_version TEXT,
                    cost_usd REAL, risk TEXT, notes TEXT,
                    resolved BOOLEAN DEFAULT 0
                )
            """)
            conn.commit()

    # -- budget --

    def get_business_reserve_balance(self) -> float:
        if not os.path.exists(self.tax_db):
            return 0.0
        with sqlite3.connect(self.tax_db) as conn:
            c = conn.cursor()
            c.execute("SELECT COALESCE(balance,0) FROM business_reserve ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
        return row[0] if row else 0.0

    def monthly_spend(self) -> float:
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with sqlite3.connect(self.upgrade_db) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COALESCE(SUM(cost_usd),0) FROM upgrades "
                "WHERE ts >= ? AND status = 'applied'",
                (month_start.isoformat(),),
            )
            return c.fetchone()[0] or 0.0

    def monthly_inflow(self) -> float:
        """Approximate via business_reserve additions in the current month."""
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if not os.path.exists(self.tax_db):
            return 0.0
        with sqlite3.connect(self.tax_db) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COALESCE(SUM(amount_added),0) FROM business_reserve "
                "WHERE date >= ?",
                (month_start.isoformat(),),
            )
            return c.fetchone()[0] or 0.0

    def can_afford(self, cost: float) -> tuple[bool, str]:
        if cost <= 0:
            return True, "zero cost"
        balance = self.get_business_reserve_balance()
        if balance <= 0:
            return False, "no business reserve balance"
        single_cap = balance * self.config["max_single_upgrade_pct_of_reserve"]
        if cost > single_cap:
            return False, f"cost ${cost:.2f} exceeds single-upgrade cap ${single_cap:.2f}"
        inflow = self.monthly_inflow()
        # If there's no inflow this month, fall back to current balance as the basis
        # for the monthly cap. Otherwise a zero-inflow month blocks all upgrades.
        basis = inflow if inflow > 0 else balance
        monthly_cap = basis * self.config["max_monthly_upgrade_pct_of_reserve"]
        spent = self.monthly_spend()
        if spent + cost > monthly_cap:
            return False, (f"monthly spend ${spent:.2f}+${cost:.2f} "
                           f"would exceed cap ${monthly_cap:.2f}")
        return True, "within budget"

    # -- scanning --

    def scan_candidates(self) -> List[UpgradeCandidate]:
        candidates: List[UpgradeCandidate] = []
        candidates.extend(self._scan_pip())
        if self.device_profile and self.device_profile.has_docker:
            candidates.extend(self._scan_docker_images())
        # Model scanning is stubbed — a real version would call Echo Intel weekly
        # candidates.extend(self._scan_models())
        return candidates

    def _scan_pip(self) -> List[UpgradeCandidate]:
        try:
            r = subprocess.run(
                ["pip", "list", "--outdated", "--format=json"],
                capture_output=True, text=True, timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.warning("pip scan failed: %s", exc)
            return []
        if r.returncode != 0:
            log.warning("pip list failed: %s", r.stderr[:200])
            return []
        try:
            outdated = json.loads(r.stdout or "[]")
        except json.JSONDecodeError:
            return []

        candidates = []
        for pkg in outdated:
            current_major = pkg["version"].split(".")[0]
            latest_major = pkg["latest_version"].split(".")[0]
            # Patch/minor bump = low risk; major bump = medium
            risk = "low" if current_major == latest_major else "medium"
            candidates.append(UpgradeCandidate(
                component=f"lib:{pkg['name']}",
                current_version=pkg["version"],
                latest_version=pkg["latest_version"],
                cost_usd=0.0,  # pip is free bandwidth-wise
                risk=risk,
                requires_human=(risk != "low"),
                notes=f"pip latest_type={pkg.get('latest_filetype','')}",
            ))
        return candidates

    def _scan_docker_images(self) -> List[UpgradeCandidate]:
        try:
            r = subprocess.run(
                ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True, text=True, timeout=15,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if r.returncode != 0:
            return []
        candidates = []
        for line in r.stdout.strip().splitlines():
            if ":" not in line or "<none>" in line:
                continue
            repo, tag = line.split(":", 1)
            # Stable tags (latest, main) warrant a pull check
            if tag in ("latest", "main", "stable"):
                candidates.append(UpgradeCandidate(
                    component=f"image:{repo}",
                    current_version=tag,
                    latest_version=tag,
                    cost_usd=0.0,
                    risk="medium",  # image upgrades have restart implications
                    requires_human=True,
                    notes=f"re-pull {repo}:{tag}",
                ))
        return candidates

    # -- applying --

    def apply(self, candidate: UpgradeCandidate,
              human_approved: bool = False) -> dict:
        if not self.config.get("enabled", True):
            return {"status": "disabled", "component": candidate.component}

        # Human-gate: risk rule + dollar rule
        needs_human = (
            candidate.requires_human
            or candidate.risk in ("medium", "high")
            or candidate.cost_usd > self.config["human_approval_required_above_usd"]
        )
        if needs_human and not human_approved:
            self._queue_approval(candidate)
            return {"status": "pending_human_approval", "component": candidate.component}

        ok, reason = self.can_afford(candidate.cost_usd)
        if not ok:
            return {"status": "blocked_budget", "component": candidate.component, "reason": reason}

        # Actually apply
        status, rollback_info = self._do_apply(candidate)

        with sqlite3.connect(self.upgrade_db) as conn:
            conn.execute("""
                INSERT INTO upgrades
                (ts, component, from_version, to_version, cost_usd, risk,
                 status, human_approved, rollback_version, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                datetime.utcnow().isoformat(),
                candidate.component,
                candidate.current_version,
                candidate.latest_version,
                candidate.cost_usd,
                candidate.risk,
                status,
                human_approved,
                rollback_info,
                candidate.notes,
            ))
            conn.commit()
        return {"status": status, "component": candidate.component,
                "rollback_version": rollback_info}

    def _do_apply(self, candidate: UpgradeCandidate) -> tuple[str, str]:
        if candidate.component.startswith("lib:"):
            pkg = candidate.component.split(":", 1)[1]
            try:
                r = subprocess.run(
                    ["pip", "install", "--upgrade", f"{pkg}=={candidate.latest_version}"],
                    capture_output=True, text=True, timeout=300,
                )
                if r.returncode == 0:
                    return "applied", candidate.current_version
                log.warning("pip upgrade failed for %s: %s", pkg, r.stderr[:200])
                return "failed", candidate.current_version
            except subprocess.TimeoutExpired:
                return "timeout", candidate.current_version
        if candidate.component.startswith("image:"):
            image = candidate.component.split(":", 1)[1]
            try:
                r = subprocess.run(
                    ["docker", "pull", f"{image}:{candidate.latest_version}"],
                    capture_output=True, text=True, timeout=600,
                )
                if r.returncode == 0:
                    return "applied", candidate.current_version
                return "failed", candidate.current_version
            except subprocess.TimeoutExpired:
                return "timeout", candidate.current_version
        return "not_implemented", candidate.current_version

    def _queue_approval(self, candidate: UpgradeCandidate) -> None:
        with sqlite3.connect(self.upgrade_db) as conn:
            conn.execute("""
                INSERT INTO pending_approvals
                (ts, component, from_version, to_version, cost_usd, risk, notes)
                VALUES (?,?,?,?,?,?,?)
            """, (
                datetime.utcnow().isoformat(),
                candidate.component,
                candidate.current_version,
                candidate.latest_version,
                candidate.cost_usd,
                candidate.risk,
                candidate.notes,
            ))
            conn.commit()

    def list_pending_approvals(self) -> List[dict]:
        with sqlite3.connect(self.upgrade_db) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, ts, component, from_version, to_version, cost_usd, risk, notes "
                "FROM pending_approvals WHERE resolved = 0 ORDER BY id DESC"
            )
            cols = ["id", "ts", "component", "from_version", "to_version",
                    "cost_usd", "risk", "notes"]
            return [dict(zip(cols, row)) for row in c.fetchall()]

    def approve(self, approval_id: int) -> dict:
        with sqlite3.connect(self.upgrade_db) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT component, from_version, to_version, cost_usd, risk, notes "
                "FROM pending_approvals WHERE id = ? AND resolved = 0",
                (approval_id,),
            )
            row = c.fetchone()
            if not row:
                return {"status": "not_found", "id": approval_id}
            candidate = UpgradeCandidate(
                component=row[0], current_version=row[1], latest_version=row[2],
                cost_usd=row[3], risk=row[4], requires_human=False, notes=row[5] or "",
            )
            c.execute("UPDATE pending_approvals SET resolved = 1 WHERE id = ?",
                      (approval_id,))
            conn.commit()
        return self.apply(candidate, human_approved=True)

    def reject(self, approval_id: int) -> dict:
        with sqlite3.connect(self.upgrade_db) as conn:
            conn.execute("UPDATE pending_approvals SET resolved = 1 WHERE id = ?",
                         (approval_id,))
            conn.commit()
        return {"status": "rejected", "id": approval_id}

    def rollback(self, upgrade_id: int) -> dict:
        # Real rollback: reinstall rollback_version
        with sqlite3.connect(self.upgrade_db) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT component, rollback_version FROM upgrades WHERE id = ?",
                (upgrade_id,),
            )
            row = c.fetchone()
        if not row:
            return {"status": "not_found", "id": upgrade_id}
        component, version = row
        if component.startswith("lib:") and version:
            pkg = component.split(":", 1)[1]
            subprocess.run(["pip", "install", f"{pkg}=={version}"], capture_output=True)
        return {"status": "rolled_back", "id": upgrade_id,
                "component": component, "version": version}
