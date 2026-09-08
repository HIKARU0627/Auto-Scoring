"""Real ``AIProvider`` adapters (Issues #44, #35).

One module per transport, together covering all four links of the ordered
fallback chain the project owner adopted in Issue #81
(business-rules-and-evaluation-data.md section 3 (B); credentials, cost and
latency tradeoffs across the four are in ``docs/poc-2-ai-grading.md``
section 7):

1. ``vertex_gemini_provider.py`` -- Gemini on Vertex AI, authenticated with
   Application Default Credentials (Gemini API keys are blocked by
   organization policy);
2. ``codex_app_server_provider.py`` -- Codex CLI's app-server JSON-RPC
   protocol, reusing the operator's own ``codex login``;
3. ``openrouter_provider.py`` -- OpenRouter's single-key HTTP gateway;
4. ``openai_provider.py`` -- the OpenAI API directly.

``fallback_provider.py`` composes them into that order as one more
``AIProvider``, and ``factory.py`` builds the chain from configuration.
"""
