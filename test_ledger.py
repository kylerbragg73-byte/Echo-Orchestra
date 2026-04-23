"""Tests for ledger module."""
import os
import tempfile

import pytest

from ledger.ledger import FinancialLedger, TaskRecord, COST_TABLE, ModelTier


@pytest.fixture
def ledger():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield FinancialLedger(db_path=path)
    os.unlink(path)


def test_cost_calculation(ledger):
    task = TaskRecord(
        task_id="t1", loop_type="test", model_used="claude-opus-4-7",
        tokens_in=1_000_000, tokens_out=500_000,
    )
    cost = ledger.log_task(task)
    # 5.00 * 1 + 25.00 * 0.5 = 17.50
    assert cost == pytest.approx(17.50, abs=0.01)


def test_unknown_model_zero_cost(ledger):
    task = TaskRecord(
        task_id="t2", loop_type="test", model_used="not-a-real-model",
        tokens_in=1000, tokens_out=500,
    )
    assert ledger.log_task(task) == 0.0


def test_revenue_row_keeps_cost_zero(ledger):
    task = TaskRecord(
        task_id="rev1", loop_type="revenue", model_used="stripe",
        tokens_in=0, tokens_out=0, revenue_usd=19.99,
    )
    assert ledger.log_task(task) == 0.0


def test_fresh_day_no_crash(ledger):
    # On a brand new DB with no tasks, get_profit_loss must not blow up
    pnl = ledger.get_profit_loss(days=7)
    assert pnl["net_profit"] == 0
    assert pnl["total_cost"] == 0
    assert pnl["total_revenue"] == 0
    assert pnl["daily_breakdown"] == []


def test_daily_budget_breach(ledger):
    # Spend $60 on premium — exceeds default $50 cap
    task = TaskRecord(
        task_id="big", loop_type="test", model_used="claude-opus-4-7",
        tokens_in=12_000_000, tokens_out=0,
    )
    ledger.log_task(task)
    caps = {"cheap": 5.0, "standard": 10.0, "premium": 50.0}
    assert ledger.daily_budget_breached(ModelTier.PREMIUM, caps) is True
    assert ledger.daily_budget_breached(ModelTier.CHEAP, caps) is False


def test_halt_only_after_seven_days(ledger):
    # A single negative day should NOT halt the system
    task = TaskRecord(
        task_id="loss", loop_type="test", model_used="claude-opus-4-7",
        tokens_in=1_000_000, tokens_out=0,
    )
    ledger.log_task(task)
    assert ledger.should_halt() is False


def test_cost_table_has_current_models():
    # Regression guard: the April 2026 names must be present
    for name in ("claude-opus-4-7", "deepseek-v3.2", "kimi-k2.6",
                 "grok-4.20", "llama-4-scout-local"):
        assert name in COST_TABLE, f"missing {name}"
