# Echo-Orchestra

**A human-operated AI business framework.**

Version 3.0 — April 23, 2026

---

## 1. What Echo Is

Echo is a modular framework that coordinates several AI providers to research, build, ship, and sell digital products — and to track every dollar it earns, split profit on a schedule, and reserve a portion for its own upkeep.

Echo is human-operated. The framework decides how to route work, what to build, and when to stop. The human owner decides whether to deploy it, in which jurisdictions, and whether to accept each payout. Echo is not a legal person and carries no legal authority on its own.

### Core capabilities (by design)

- **Research before build.** Every loop starts with a grounded web search via Perplexity. If the market isn't there, the product doesn't get built.
- **Multi-model routing.** Cheap models handle bulk, premium models handle synthesis, local models (when available) handle throwaway work.
- **Compliance gate.** A pre-build check against EU AI Act prohibited/high-risk categories and US FTC high-risk categories.
- **Financial ledger.** SQLite-backed record of every task's cost and every sale's revenue.
- **Automatic profit split.** Revenue → tax reserve, business reserve, human dividend. Obligations paid on a schedule.
- **Human loop.** Captures the operator's frustrations/desires/observations as product sparks.
- **Device-adaptive execution.** Echo detects what it's running on and enables only the loops the host can actually run.
- **Self-upgrade.** A capped slice of the business reserve funds automatic library upgrades and human-approved model/image upgrades.

### Capabilities are device-dependent

Echo does not claim capabilities its host cannot deliver. At startup, Echo reads the host OS, RAM, disk, Docker availability, and GPU presence, classifies it into one of five tiers, and enables only the loops that tier supports. See Section 3.

### What Echo is not

- Not a legal person. The operator carries full responsibility for deployment, jurisdiction, and compliance.
- Not a financial or legal advisor. The compliance gate is a filter, not counsel.
- Not magic. API keys cost money. Running loops costs money. The survival rules exist because this will go broke if they don't.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ LAYER 6: ECONOMY & COMPLIANCE                                    │
│   Ledger · Tax Module · Legal Gate · Stripe Webhook              │
├──────────────────────────────────────────────────────────────────┤
│ LAYER 5: EXECUTION                                               │
│   Docker · MCP servers (Godot, Blender, FFmpeg) · pip · git      │
├──────────────────────────────────────────────────────────────────┤
│ LAYER 4: ORCHESTRATION & ROUTING                                 │
│   LiteLLM Router · Strategy Engine · Device Profiler ·           │
│   Self-Upgrade Engine                                            │
├──────────────────────────────────────────────────────────────────┤
│ LAYER 3: AGENT RUNTIME                                           │
│   Loop runners · scheduler                                       │
├──────────────────────────────────────────────────────────────────┤
│ LAYER 2: RESEARCH (Echo Intel)                                   │
│   Perplexity Sonar                                               │
├──────────────────────────────────────────────────────────────────┤
│ LAYER 1: INTELLIGENCE                                            │
│   Premium: Claude Opus 4.7, GPT-5.4, Gemini 3.1 Pro              │
│   Standard: Grok 4.20, Kimi K2.6                                 │
│   Cheap: DeepSeek V3.2, Llama 4 Scout (local)                    │
└──────────────────────────────────────────────────────────────────┘
```

### Loops

| Loop | Type | Minimum Tier |
|------|------|--------------|
| LOOP-01 | Digital Products (templates, guides, PDFs) | LITE |
| LOOP-02 | Content (articles, newsletters, scripts) | LITE |
| LOOP-03 | SaaS / Web Tools | STANDARD |
| LOOP-04 | Human-Centered (spark-driven) | LITE |
| LOOP-05 | Game Creation (Godot project export) | WORKSTATION |
| LOOP-06 | Cinematic / Video (FFmpeg render) | WORKSTATION |

The first loop that works on a decent computer is **LOOP-01: Digital Products**. It runs on any machine that can run Python 3.11 with 8 GB RAM and outbound internet. No Docker required. No GPU required.

---

## 3. Device Tiers

Echo classifies its host at startup:

| Tier | Signals | What runs |
|------|---------|-----------|
| PHONE | Termux / iOS Pythonista / < 4 GB RAM / no Docker | API routing, ledger, compliance, tax, human loop, Echo Intel — read/write only |
| LITE | 4–8 GB RAM, no Docker | All of the above + LOOP-01, 02, 04 |
| STANDARD | 8–16 GB RAM, Docker available | + LOOP-03, LiteLLM proxy, Stripe webhook, scheduler daemon |
| WORKSTATION | 16+ GB RAM, Docker, GPU (NVIDIA or Apple Silicon) | + local Llama, MCP Godot/Blender/FFmpeg, LOOP-05, LOOP-06 |
| SERVER | Linux headless, Docker, 16+ GB RAM | + 24/7 scheduled runs, unattended operation |

Decent computer = STANDARD tier. That is what LOOP-01 targets. Everything above STANDARD is an upgrade path, not a prerequisite.

---

## 4. Model Reference (April 2026)

| Model | Strength | Context | Notes |
|-------|----------|---------|-------|
| Claude Opus 4.7 | Coding, long-horizon agents, synthesis | 1M | Primary premium. Released Apr 16, 2026. |
| Claude Opus 4.6 | Same, older generation | 1M | Fallback. $5/$25 per MTok. |
| GPT-5.4 | All-rounder, good tool use | 1M | |
| Gemini 3.1 Pro | Multimodal, cheap for image/video | 1M | $2/$12 per MTok. |
| Grok 4.20 | 4-agent parallel system (Grok, Harper, Benjamin, Lucas), real-time X data | 128K | |
| Kimi K2.6 | Long-context agent workflows, cheap | 200K+ | Current tracked version. |
| DeepSeek V3.2 | Cheap, MIT-licensed, ~90% of GPT-5.4 quality | 128K | Use this until V4 ships. |
| Llama 4 Scout | Local inference, 10M context | 10M | Requires GPU or Apple Silicon. |

**Important:** model prices and names change monthly in this market. The self-upgrade loop (Section 11) is how Echo keeps up.

---

## 5. File Tree

```
echo-orchestra/
├── README.md
├── CHANGELOG.md
├── LICENSE
├── docker-compose.yml
├── .env.example
├── human_config.json
├── requirements.txt
├── echo_core.py
├── intel/
│   ├── __init__.py
│   └── perplexity_client.py
├── compliance/
│   ├── __init__.py
│   └── legal_gate.py
├── ledger/
│   ├── __init__.py
│   ├── ledger.py
│   ├── tax_module.py
│   └── stripe_webhook.py
├── orchestration/
│   ├── __init__.py
│   └── strategy.py
├── router/
│   ├── simple_router.py
│   └── router.yaml
├── agents/
│   ├── __init__.py
│   └── human_loop.py
├── loops/
│   ├── __init__.py
│   ├── digital_product_loop.py
│   ├── content_loop.py
│   ├── saas_loop.py
│   ├── human_centered_loop.py
│   ├── game_loop.py
│   └── movie_loop.py
├── platform_tier/
│   ├── __init__.py
│   ├── device_tier.py
│   └── self_upgrade.py
├── mcp_servers/
│   ├── godot_server.py
│   ├── blender_server.py
│   └── ffmpeg_server.py
├── util/
│   ├── __init__.py
│   ├── logging_setup.py
│   └── http.py
├── tests/
│   ├── test_ledger.py
│   ├── test_legal_gate.py
│   ├── test_device_tier.py
│   └── test_self_upgrade.py
└── workspace/
    ├── products/
    ├── games/
    ├── movies/
    └── memory/
```

(Note: `platform_tier/` not `platform/` — Python has a stdlib module named `platform` that the latter would shadow.)

---

## 6. Installation

### Minimum requirements

- Python 3.11 or newer
- 8 GB RAM (for LOOP-01 only; more for higher loops)
- Outbound internet
- One API key: Perplexity (for research). At least one model provider key (DeepSeek is cheapest).

### Install steps

```bash
git clone <your-repo-url> echo-orchestra
cd echo-orchestra
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your API keys
python echo_core.py --init
```

`--init` runs device detection, prints the tier, initializes databases, and exits without starting any scheduler.

### Optional: Docker stack (STANDARD tier and up)

```bash
docker compose up -d
```

Brings up LiteLLM proxy, Ollama for local models, and the SQLite web viewer.

### Optional: MCP servers (WORKSTATION tier and up)

The MCP server source lives in `mcp_servers/`. Build and run them yourself — the Compose file references local build contexts, not external images. See `mcp_servers/README.md`.

---

## 7. Survival Rules

These are enforced in code, not just listed here.

1. **Revenue ≥ Cost.** If the 7-day moving average net profit is negative, Echo enters maintenance mode: no new loops start, active loops finish and stop.
2. **Daily budget caps.** Premium $50/day, Standard $10/day, Cheap $5/day. Exceeding a cap halts that tier for the rest of the day.
3. **Kill switches.** A loop with 30-day lifetime loss below `-$10` gets killed by the strategy engine.
4. **Portfolio limits.** Max 5 parallel loops. At least one loop must be cash-positive for new exploratory loops to start.
5. **Research before build.** Every loop calls Echo Intel first. A "no market demand" result blocks the build.
6. **Financial constraints.** Max 5% of the business reserve to speculative instruments. Minimum 30% tax reserve, 20% business reserve.
7. **Self-upgrade budget cap.** The self-upgrade engine may not consume more than 10% of the current business reserve in any single upgrade, or more than 30% of monthly business reserve inflow across all upgrades in a calendar month. Any upgrade above $25 USD or flagged medium/high risk requires human approval via the Human Loop.

---

## 8. Revenue Streams

| Stream | Source | Channel | Typical Price |
|--------|--------|---------|---------------|
| Digital products | LOOP-01 | Gumroad, Payhip | $5–$30 |
| Content | LOOP-02 | Substack, Medium, Ghost | Subscription or ads |
| SaaS | LOOP-03 | Vercel + Stripe | $5–$50/month |
| Games | LOOP-05 | itch.io | $0–$10 |
| Videos | LOOP-06 | YouTube, licensing | Ad rev / license |

---

## 9. Quick Start (what it actually does)

```python
from echo_core import EchoSystem

echo = EchoSystem()
# Prints device tier, active capabilities, opens databases.

# Configure the human side
echo.tax_module.set_allocation(tax=0.30, business=0.20, human=0.50)
echo.tax_module.set_payout_schedule("weekly", "friday", "17:00")
echo.tax_module.add_obligation("Rent", "needs", 1200.00, "monthly", "bank")
echo.tax_module.add_obligation("Internet", "needs", 80.00, "monthly", "bank")

# Research
research = echo.research("productivity templates for freelancers", "Notion template")
print(research["analysis"]["recommendation"])

# Run the first loop (works on LITE tier and up)
if echo.loop_available("digital_product_loop"):
    from loops.digital_product_loop import DigitalProductLoop
    loop = DigitalProductLoop()
    result = loop.run(niche="freelance invoicing", product_type="notion_template")
    print(result["status"], "->", result.get("output_path"))

# Record a sale (normally Stripe webhook does this)
echo.process_revenue(19.99, "Gumroad - Freelance Invoicing Template")

# Weekly upgrade check
upgrades = echo.weekly_upgrade_check()
print(f"Applied: {upgrades['applied']}")
print(f"Pending human review: {upgrades['pending_human']}")

# Dashboard
dash = echo.tax_module.get_human_dashboard()
print(f"Paid to human so far: ${dash['total_paid_to_human']:,.2f}")
```

---

## 10. Open-Source Notes

Echo is MIT-licensed. A single person can start with a Perplexity key and a DeepSeek key and a $10/month budget, and grow from there.

The operator running Echo carries full responsibility for jurisdiction, deployment, and legality. Echo informs, logs, warns, and routes. The human decides. The compliance gate is not legal counsel.

When forking: update the model IDs in `router/router.yaml` to whatever is current, regenerate disclosures in `compliance/legal_gate.py` for your jurisdiction, and set your own obligations in `human_config.json`.

---

## 11. How Echo Grows

Echo is not expected to stay at v3.0. Three growth paths are built in:

- **Capability growth.** As the host machine improves (more RAM, GPU, Docker), Echo auto-enables more loops. No code change needed.
- **Model upgrades.** The self-upgrade engine scans for newer library versions and (with human approval for non-trivial changes) newer model IDs. Funded by a capped slice of the business reserve.
- **New loops.** Loops are single files under `loops/`. Copy `digital_product_loop.py`, change the build step, register it in `echo_core.py`. Done.

Do not add a loop that promises a capability the host can't deliver. Register the minimum tier in the loop class. Echo will refuse to run it on lower tiers.

End of README.
