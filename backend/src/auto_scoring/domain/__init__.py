"""Domain core: scoring rules and state.

This layer is framework-free. It must not import FastAPI, SQLAlchemy, HTTP
clients, or any external service SDK, nor the `api` / `adapters` layers
(see `AGENTS.md` "Architecture" — `api -> domain <- adapters`).
"""
