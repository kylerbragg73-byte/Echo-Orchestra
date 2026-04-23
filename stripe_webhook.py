"""
Stripe webhook handler.

Run with:  uvicorn ledger.stripe_webhook:app --host 0.0.0.0 --port 8787

Expose behind HTTPS (eg. via Cloudflare tunnel or ngrok) and configure the
Stripe webhook endpoint in the Stripe dashboard. Set STRIPE_WEBHOOK_SECRET
in .env — it is used to verify the signature on every call.
"""

from __future__ import annotations

import os
from datetime import datetime

import stripe
from fastapi import FastAPI, Header, HTTPException, Request

from ledger.ledger import FinancialLedger, TaskRecord
from util.logging_setup import get_logger

log = get_logger("echo.stripe")

stripe.api_key = os.getenv("STRIPE_API_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

app = FastAPI(title="Echo Stripe webhook")
ledger = FinancialLedger()


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    if not WEBHOOK_SECRET:
        log.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="webhook not configured")

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid payload")
    except stripe.error.SignatureVerificationError:
        log.warning("bad stripe signature")
        raise HTTPException(status_code=400, detail="invalid signature")

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type in ("payment_intent.succeeded", "checkout.session.completed",
                      "invoice.paid"):
        amount_cents = obj.get("amount_received") or obj.get("amount_total") or obj.get("amount_paid") or 0
        amount = amount_cents / 100.0
        description = obj.get("description") or event_type
        product_id = obj.get("id")

        task = TaskRecord(
            task_id=f"rev_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}",
            loop_type="revenue",
            model_used="stripe",
            tokens_in=0,
            tokens_out=0,
            revenue_usd=amount,
            agent_name="stripe",
            action_type="revenue",
            product_id=product_id,
            status="paid",
        )
        ledger.log_task(task)
        log.info("Recorded revenue $%.2f from %s (%s)", amount, event_type, product_id)

    return {"received": True}


@app.get("/health")
async def health():
    return {"ok": True}
