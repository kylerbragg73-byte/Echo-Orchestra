"""
Human tax module.

Splits revenue into tax reserve / business reserve / human dividend.
Pays obligations on a schedule. Files quarterly tax reports.

Uses APScheduler with a SQLAlchemy job store, so scheduled payouts survive
process restarts — unlike the previous `schedule` lib running in a daemon thread,
which silently died if the main process crashed.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger

from util.logging_setup import get_logger

log = get_logger("echo.tax")


class ObligationType(Enum):
    TAX_FEDERAL = "tax_federal"
    TAX_STATE = "tax_state"
    TAX_SELF_EMPLOYMENT = "tax_se"
    NEEDS = "needs"
    WANTS = "wants"
    LUXURY = "luxury"
    RESERVE = "reserve"
    EMERGENCY = "emergency"


@dataclass
class Obligation:
    obligation_id: str
    obligation_type: ObligationType
    name: str
    amount: float
    frequency: str
    next_due: datetime
    auto_pay: bool
    destination: str
    status: str = "pending"


_DAY_NAMES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
              "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
              "friday": 4, "saturday": 5, "sunday": 6}


class HumanTaxModule:
    DEFAULT_ALLOCATION = {
        "tax_reserve": 0.30,
        "business_reserve": 0.20,
        "human_dividend": 0.50,
    }

    def __init__(
        self,
        ledger_db: str = "echo_ledger.db",
        tax_db: str = "human_tax.db",
        scheduler_db: str = "echo_scheduler.db",
        config_path: str = "human_config.json",
    ):
        self.ledger_db = ledger_db
        self.tax_db = tax_db
        self.scheduler_db = scheduler_db
        self.config_path = config_path
        self.config = self._load_config()
        self._init_db()

        jobstore = SQLAlchemyJobStore(url=f"sqlite:///{self.scheduler_db}")
        self.scheduler = BackgroundScheduler(
            jobstores={"default": jobstore},
            job_defaults={"coalesce": True, "max_instances": 1},
        )

    def _load_config(self) -> Dict:
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            log.info("No %s found — using defaults", self.config_path)
            return {
                "human_name": "Owner",
                "business_entity": "Single-Member LLC",
                "tax_rate": 0.30,
                "payout_schedule": {"frequency": "weekly", "day": "friday", "time": "17:00"},
                "allocation": dict(self.DEFAULT_ALLOCATION),
                "obligations": [],
                "bank_account": {"account_number": "", "routing_number": "", "bank_name": ""},
                "crypto_wallet": {"usdc_solana": "", "btc_lightning": ""},
            }

    def _save_config(self) -> None:
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)

    def _init_db(self) -> None:
        with sqlite3.connect(self.tax_db) as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS obligations (
                obligation_id TEXT PRIMARY KEY, obligation_type TEXT, name TEXT,
                amount REAL, frequency TEXT, next_due TEXT, auto_pay BOOLEAN,
                destination TEXT, status TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS tax_reserve (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT,
                amount_reserved REAL, amount_paid REAL, amount_owed REAL,
                quarter TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS human_payouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT,
                gross_profit REAL, tax_reserve REAL, business_reserve REAL,
                human_dividend REAL, needs_allocation REAL, wants_allocation REAL,
                luxury_allocation REAL, status TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS business_reserve (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT,
                amount_added REAL, amount_spent REAL, balance REAL)""")
            conn.commit()

    # -- configuration --

    def set_payout_schedule(self, frequency: str, day: str, time_str: str) -> None:
        self.config["payout_schedule"] = {
            "frequency": frequency, "day": day, "time": time_str
        }
        self._save_config()
        log.info("Payout schedule: %s on %s at %s", frequency, day, time_str)

    def set_tax_rate(self, rate: float) -> None:
        self.config["tax_rate"] = rate
        self._save_config()

    def set_allocation(self, tax: float, business: float, human: float) -> None:
        if abs(tax + business + human - 1.0) > 0.001:
            raise ValueError("Allocations must sum to 1.0")
        self.config["allocation"] = {
            "tax_reserve": tax,
            "business_reserve": business,
            "human_dividend": human,
        }
        self._save_config()

    def add_obligation(
        self,
        name: str,
        obligation_type: str,
        amount: float,
        frequency: str,
        destination: str,
        auto_pay: bool = True,
    ) -> Obligation:
        obl = Obligation(
            obligation_id=f"obl_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}",
            obligation_type=ObligationType(obligation_type),
            name=name, amount=amount, frequency=frequency,
            next_due=datetime.utcnow(), auto_pay=auto_pay, destination=destination,
        )
        with sqlite3.connect(self.tax_db) as conn:
            conn.execute(
                "INSERT INTO obligations VALUES (?,?,?,?,?,?,?,?,?)",
                (obl.obligation_id, obl.obligation_type.value, obl.name,
                 obl.amount, obl.frequency, obl.next_due.isoformat(),
                 obl.auto_pay, obl.destination, obl.status),
            )
            conn.commit()
        log.info("Obligation added: %s — $%.2f %s", name, amount, frequency)
        return obl

    # -- core money flow --

    def process_profit(self, profit_amount: float) -> Dict:
        if profit_amount <= 0:
            return {"gross_profit": profit_amount, "skipped": True}
        alloc = self.config["allocation"]
        tax = profit_amount * alloc["tax_reserve"]
        biz = profit_amount * alloc["business_reserve"]
        hum = profit_amount * alloc["human_dividend"]
        needs, wants, luxury = hum * 0.50, hum * 0.30, hum * 0.20

        quarter = self._get_current_quarter()
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.tax_db) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO tax_reserve (date, amount_reserved, amount_paid, amount_owed, quarter) "
                "VALUES (?,?,0,?,?)",
                (now, tax, tax, quarter),
            )
            # Running business reserve balance
            c.execute("SELECT COALESCE(balance,0) FROM business_reserve ORDER BY id DESC LIMIT 1")
            prior = c.fetchone()
            prior_balance = prior[0] if prior else 0.0
            c.execute(
                "INSERT INTO business_reserve (date, amount_added, amount_spent, balance) "
                "VALUES (?,?,0,?)",
                (now, biz, prior_balance + biz),
            )
            conn.commit()

        return {
            "gross_profit": profit_amount,
            "tax_reserve": tax,
            "business_reserve": biz,
            "human_dividend": hum,
            "needs": needs, "wants": wants, "luxury": luxury,
            "quarter": quarter,
        }

    def execute_payout(self) -> Dict:
        """Called by scheduler on the configured cadence."""
        with sqlite3.connect(self.tax_db) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM obligations WHERE status = 'pending' AND next_due <= ?",
                (datetime.utcnow().isoformat(),),
            )
            due = c.fetchall()
            total_due = sum(row[3] for row in due)

            # Available = sum of tax-reserve releases + business-reserve spendable
            # For this version: approximate with recent human_dividend allocations
            c.execute("SELECT COALESCE(SUM(human_dividend),0) FROM human_payouts WHERE status='pending'")
            pending = c.fetchone()[0] or 0.0

            if pending < total_due:
                log.warning("Insufficient funds: need %.2f, have %.2f", total_due, pending)
                return {"status": "insufficient_funds", "shortfall": total_due - pending}

            payments = []
            for row in due:
                obl_id, obl_type, name, amount, freq, next_due, auto_pay, dest, status = row
                payments.append({"obligation": name, "amount": amount, "destination": dest})
                new_due = self._calculate_next_due(freq, datetime.fromisoformat(next_due))
                c.execute(
                    "UPDATE obligations SET next_due = ?, status = 'pending' "
                    "WHERE obligation_id = ?",
                    (new_due.isoformat(), obl_id),
                )

            c.execute(
                "INSERT INTO human_payouts "
                "(date, gross_profit, tax_reserve, business_reserve, human_dividend, "
                " needs_allocation, wants_allocation, luxury_allocation, status) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (datetime.utcnow().isoformat(), pending, pending * 0.30,
                 pending * 0.20, pending * 0.50, pending * 0.25,
                 pending * 0.15, pending * 0.10, "paid"),
            )
            conn.commit()

        log.info("PAYOUT EXECUTED: $%.2f (%d obligations)", total_due, len(payments))
        for p in payments:
            log.info("  -> %s: $%.2f to %s", p["obligation"], p["amount"], p["destination"])
        return {
            "status": "paid",
            "total": total_due,
            "payments": payments,
            "remaining": pending - total_due,
        }

    # -- scheduler lifecycle --

    def start_scheduler(self) -> None:
        cfg = self.config["payout_schedule"]
        trigger = self._build_trigger(cfg)
        # Replace existing job with the same id so config changes stick
        self.scheduler.add_job(
            self.execute_payout,
            trigger=trigger,
            id="human_payout",
            replace_existing=True,
            name="Human payout",
        )
        if not self.scheduler.running:
            self.scheduler.start()
        log.info("Scheduler started: %s %s %s",
                 cfg["frequency"], cfg.get("day", ""), cfg.get("time", ""))

    def stop_scheduler(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            log.info("Scheduler stopped")

    def _build_trigger(self, cfg: dict) -> CronTrigger:
        hour_str, minute_str = cfg.get("time", "17:00").split(":")
        hour, minute = int(hour_str), int(minute_str)
        freq = cfg["frequency"]

        if freq == "weekly":
            day = cfg.get("day", "friday").lower()
            day_num = _DAY_NAMES.get(day, 4)
            return CronTrigger(day_of_week=day_num, hour=hour, minute=minute)
        if freq == "biweekly":
            # APScheduler doesn't have biweekly natively; approximate as 1st & 15th
            return CronTrigger(day="1,15", hour=hour, minute=minute)
        if freq == "monthly":
            day_of_month = int(cfg.get("day", 1))
            return CronTrigger(day=day_of_month, hour=hour, minute=minute)
        # Default: daily
        return CronTrigger(hour=hour, minute=minute)

    # -- reporting --

    def get_human_dashboard(self) -> Dict:
        with sqlite3.connect(self.tax_db) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT quarter, COALESCE(SUM(amount_reserved),0), "
                "COALESCE(SUM(amount_paid),0), COALESCE(SUM(amount_owed),0) "
                "FROM tax_reserve GROUP BY quarter ORDER BY quarter DESC LIMIT 1"
            )
            tax_row = c.fetchone()

            c.execute("SELECT COALESCE(balance,0) FROM business_reserve ORDER BY id DESC LIMIT 1")
            biz_row = c.fetchone()

            c.execute(
                "SELECT name, amount, next_due FROM obligations "
                "WHERE status = 'pending' ORDER BY next_due"
            )
            upcoming = [{"name": r[0], "amount": r[1], "due": r[2]} for r in c.fetchall()]

            c.execute("SELECT COALESCE(SUM(human_dividend),0) FROM human_payouts WHERE status = 'paid'")
            total_paid = c.fetchone()[0] or 0

        return {
            "tax_status": {
                "quarter": tax_row[0] if tax_row else "N/A",
                "reserved": tax_row[1] if tax_row else 0,
                "paid": tax_row[2] if tax_row else 0,
                "owed": tax_row[3] if tax_row else 0,
            },
            "business_reserve": biz_row[0] if biz_row else 0,
            "total_paid_to_human": total_paid,
            "upcoming_obligations": upcoming,
            "next_payout": self.config["payout_schedule"],
            "allocation": self.config["allocation"],
        }

    def generate_tax_report(self, year: int, quarter: int) -> str:
        with sqlite3.connect(self.tax_db) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COALESCE(SUM(amount_reserved),0), COALESCE(SUM(amount_paid),0), "
                "COALESCE(SUM(amount_owed),0) FROM tax_reserve WHERE quarter = ?",
                (f"{year}-Q{quarter}",),
            )
            reserved, paid, owed = c.fetchone()
        due_dates = {
            1: f"April 15, {year}",
            2: f"June 15, {year}",
            3: f"September 15, {year}",
            4: f"January 15, {year+1}",
        }
        return (
            f"ESTIMATED TAX REPORT — {year} Q{quarter}\n"
            f"Business Entity: {self.config['business_entity']}\n"
            f"Taxpayer: {self.config['human_name']}\n\n"
            f"Reserved: ${reserved:,.2f}\n"
            f"Paid (EFTPS): ${paid:,.2f}\n"
            f"Owed (Due {due_dates.get(quarter, 'Unknown')}): ${owed:,.2f}\n\n"
            f"Payment: https://www.eftps.gov — Form 1040-ES\n"
        )

    # -- helpers --

    @staticmethod
    def _get_current_quarter() -> str:
        now = datetime.utcnow()
        return f"{now.year}-Q{(now.month - 1) // 3 + 1}"

    @staticmethod
    def _calculate_next_due(frequency: str, current: datetime) -> datetime:
        if frequency == "weekly":
            return current + timedelta(weeks=1)
        if frequency == "biweekly":
            return current + timedelta(weeks=2)
        if frequency == "monthly":
            if current.month == 12:
                return current.replace(year=current.year + 1, month=1)
            return current.replace(month=current.month + 1)
        if frequency == "quarterly":
            return current + timedelta(days=90)
        if frequency == "annual":
            return current + timedelta(days=365)
        return current
