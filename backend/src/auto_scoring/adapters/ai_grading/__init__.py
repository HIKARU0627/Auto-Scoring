"""Real ``AIProvider`` adapters (Issue #44).

Each module here implements ``auto_scoring.domain.ai_provider.AIProvider``
over one transport: direct vendor API keys are not implemented yet (see
``docs/poc-2-ai-grading.md`` section 7 -- credentials/cost/latency tradeoffs
across the three paths), OpenRouter (single-key HTTP gateway,
``openrouter_provider.py``), and Codex CLI's app-server JSON-RPC protocol
(``codex_app_server_provider.py``).
"""
