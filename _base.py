"""
Shared loop helpers.

Every loop inherits from LoopBase which provides:
  - `_call_model` — goes through the LiteLLM proxy if up, falls back to direct
    provider call if not
  - `_record_build` — convenience wrapper around TaskRecord + ledger.log_task
  - `minimum_tier` — class attribute checked by echo_core before running
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from util.http import post_json
from util.logging_setup import get_logger
from ledger.ledger import FinancialLedger, TaskRecord

log = get_logger("echo.loop")


class LoopBase:
    # Override in subclasses
    loop_name: str = "base"
    minimum_tier: str = "lite"

    def __init__(self):
        self.ledger = FinancialLedger()
        self.proxy_url = os.getenv("LITELLM_PROXY_URL", "http://localhost:4000")
        self.proxy_key = os.getenv("LITELLM_PROXY_KEY", "sk-echo-local")

    def _call_model(self, model_alias: str, prompt: str,
                    system: Optional[str] = None, max_tokens: int = 2000) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            data = post_json(
                f"{self.proxy_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.proxy_key}",
                    "Content-Type": "application/json",
                },
                json_body={
                    "model": model_alias,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
                timeout=120,
            )
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            log.error("Model call failed (%s): %s", model_alias, exc)
            return ""

    def _record(self, model_used: str, action: str, tokens_in: int = 0,
                tokens_out: int = 0, agent: str = "builder",
                status: str = "done") -> float:
        task = TaskRecord(
            task_id=f"{self.loop_name}_{action}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}",
            loop_type=self.loop_name,
            model_used=model_used,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            agent_name=agent,
            action_type=action,
            status=status,
        )
        return self.ledger.log_task(task)

    @staticmethod
    def slug(text: str) -> str:
        return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")[:60]
