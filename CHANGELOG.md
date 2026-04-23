# Changelog

## v3.0 — 2026-04-23

### Breaking
- Renamed `platform/` module to `platform_tier/` to avoid shadowing the Python stdlib `platform` module.
- Changed primary premium Claude model from 4.6 to 4.7 in `router/router.yaml`. 4.6 is now a fallback. Both use the correct API ID strings (`claude-opus-4-7`, `claude-opus-4-6`).
- Removed `sqlite3` from `requirements.txt` (it is stdlib).

### Security
- Replaced `eval()` in `intel/perplexity_client.py` with `json.loads()`. The previous code could execute arbitrary Python from a poisoned model response.
- Added retry/backoff via `tenacity` on every external HTTP call in `util/http.py`.
- Added structured logging with rotating file handler in `util/logging_setup.py`. Replaces `print()` calls across the stack.

### Accuracy
- Updated model reference table to match the April 2026 landscape:
  - Claude Opus 4.7 (primary), 4.6 (fallback)
  - Kimi K2.6 (was K2.5)
  - DeepSeek V3.2 (was V4 — unshipped)
  - Llama 4 Scout (was generic "Llama 4")
  - Grok 4.20 documented as 4-agent system (Grok, Harper, Benjamin, Lucas)
- Fixed Perplexity endpoint: `https://api.perplexity.ai/chat/completions` (no `/v1/` prefix).

### Correctness
- `compliance/legal_gate.py`: replaced single-keyword substring match (which approved nearly everything) with per-category keyword lists and a confidence score. Optional LLM fallback for ambiguous cases is stubbed with an interface.
- `orchestration/strategy.py`: fixed comment mislabeling "lifetime loss" where the query was 30-day.
- `ledger/ledger.py`: `get_profit_loss(1)` now handles empty-today case by returning zeros instead of None arithmetic.
- `ledger/tax_module.py`: replaced the single-threaded `schedule` daemon with `APScheduler` using a SQLAlchemy job store. Scheduled payouts now survive a process restart.

### New — not vaporware
- `loops/digital_product_loop.py` — writes a real Notion-compatible markdown template to `workspace/products/`.
- `loops/content_loop.py` — writes a real article markdown file to `workspace/content/`.
- `loops/saas_loop.py` — scaffolds a real Next.js + Stripe-ready starter project to `workspace/saas/<slug>/`.
- `loops/human_centered_loop.py` — consumes sparks from the human loop and routes them to an appropriate build loop.
- `loops/game_loop.py` — produces a real Godot 4 project on disk (main scene, GDScript, `project.godot`).
- `loops/movie_loop.py` — produces a real MP4 via FFmpeg (scene images + narration + concat).
- `mcp_servers/godot_server.py`, `blender_server.py`, `ffmpeg_server.py` — real MCP server stubs over stdio.
- `ledger/stripe_webhook.py` — FastAPI endpoint that receives Stripe webhooks and writes revenue rows.

### New — device-adaptive + self-upgrade
- `platform_tier/device_tier.py` — detects OS, RAM, Docker, GPU, and classifies into PHONE / LITE / STANDARD / WORKSTATION / SERVER.
- `platform_tier/self_upgrade.py` — scans `pip list --outdated`, applies low-risk patch upgrades within budget cap, defers medium/high risk to human approval.
- `human_config.json` grew a `self_upgrade` section with budget caps.
- New survival rule #7: upgrade budget cap.

### Tests
- `tests/test_ledger.py`, `tests/test_legal_gate.py`, `tests/test_device_tier.py`, `tests/test_self_upgrade.py` — pytest coverage on the money and gating paths.

### Removed
- Fake "https://echo-games.example.com/build/…" and "https://echo-films.example.com/…" URLs that did nothing. Replaced with real output paths.
