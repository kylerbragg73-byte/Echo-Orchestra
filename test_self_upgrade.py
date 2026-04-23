"""Tests for self_upgrade engine."""
import json
import os
import sqlite3
import tempfile

import pytest

from platform_tier.self_upgrade import SelfUpgradeEngine, UpgradeCandidate


@pytest.fixture
def tmp_env():
    """Spin up temp DBs and a temp config."""
    tax_fd, tax_db = tempfile.mkstemp(suffix=".db")
    up_fd, up_db = tempfile.mkstemp(suffix=".db")
    cfg_fd, cfg_path = tempfile.mkstemp(suffix=".json")
    os.close(tax_fd); os.close(up_fd); os.close(cfg_fd)

    # Seed business_reserve with $100 balance
    with sqlite3.connect(tax_db) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS business_reserve (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT,
            amount_added REAL, amount_spent REAL, balance REAL)""")
        conn.execute(
            "INSERT INTO business_reserve (date, amount_added, amount_spent, balance) "
            "VALUES (?, 100.0, 0, 100.0)",
            ("2026-04-01",),
        )
        conn.commit()

    with open(cfg_path, "w") as f:
        json.dump({"self_upgrade": {
            "enabled": True,
            "auto_apply_risk": "low",
            "max_single_upgrade_pct_of_reserve": 0.10,
            "max_monthly_upgrade_pct_of_reserve": 0.30,
            "human_approval_required_above_usd": 25.00,
            "scan_frequency": "weekly",
        }}, f)

    engine = SelfUpgradeEngine(tax_db=tax_db, upgrade_db=up_db, config_path=cfg_path)

    yield engine

    for p in (tax_db, up_db, cfg_path):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass


def test_reserve_balance(tmp_env):
    assert tmp_env.get_business_reserve_balance() == pytest.approx(100.0)


def test_can_afford_within_cap(tmp_env):
    # 10% of 100 = 10 cap
    ok, reason = tmp_env.can_afford(5.0)
    assert ok, reason


def test_can_afford_exceeds_single_cap(tmp_env):
    # $15 > $10 single cap
    ok, reason = tmp_env.can_afford(15.0)
    assert not ok


def test_low_risk_free_lib_is_applied_path(tmp_env):
    """A zero-cost low-risk library upgrade does not require human approval."""
    candidate = UpgradeCandidate(
        component="lib:requests",
        current_version="2.32.0",
        latest_version="2.32.1",
        cost_usd=0.0,
        risk="low",
        requires_human=False,
    )
    result = tmp_env.apply(candidate)
    # The actual pip install will either succeed or fail in the test env;
    # what matters is it did NOT get gated to human_approval.
    assert result["status"] not in ("pending_human_approval",)


def test_medium_risk_queued_for_approval(tmp_env):
    candidate = UpgradeCandidate(
        component="lib:somepkg",
        current_version="1.0.0",
        latest_version="2.0.0",  # major bump
        cost_usd=0.0,
        risk="medium",
        requires_human=True,
    )
    result = tmp_env.apply(candidate)
    assert result["status"] == "pending_human_approval"
    pending = tmp_env.list_pending_approvals()
    assert len(pending) == 1
    assert pending[0]["component"] == "lib:somepkg"


def test_over_dollar_cap_queued(tmp_env):
    """Anything costing more than the configured dollar threshold should queue."""
    candidate = UpgradeCandidate(
        component="model:premium-code",
        current_version="opus-4.6",
        latest_version="opus-4.7",
        cost_usd=30.00,
        risk="low",
        requires_human=False,
    )
    result = tmp_env.apply(candidate)
    assert result["status"] == "pending_human_approval"


def test_budget_blocks_expensive_upgrade(tmp_env):
    candidate = UpgradeCandidate(
        component="lib:expensive",
        current_version="1.0",
        latest_version="1.1",
        cost_usd=50.00,  # exceeds $10 single-upgrade cap
        risk="low",
        requires_human=False,
    )
    # Even with human_approved=True, budget should block
    result = tmp_env.apply(candidate, human_approved=True)
    assert result["status"] == "blocked_budget"


def test_reject_clears_pending(tmp_env):
    candidate = UpgradeCandidate(
        component="lib:somepkg",
        current_version="1.0", latest_version="2.0",
        cost_usd=0.0, risk="medium", requires_human=True,
    )
    tmp_env.apply(candidate)
    pending = tmp_env.list_pending_approvals()
    assert len(pending) == 1
    approval_id = pending[0]["id"]
    tmp_env.reject(approval_id)
    assert tmp_env.list_pending_approvals() == []
