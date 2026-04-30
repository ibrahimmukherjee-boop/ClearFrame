"""
Rate Limiting Patch for ops/server.py
======================================
Add the following to clearframe/clearframe/ops/server.py.
This uses slowapi (already added to pyproject.toml dependencies).

STEP 1 — Add these imports at the top of server.py:
----------------------------------------------------

    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

STEP 2 — Create the limiter (add just below your imports):
----------------------------------------------------------

    limiter = Limiter(
        key_func  = get_remote_address,
        default_limits = ["200/minute"],   # global fallback
    )

STEP 3 — Wire the limiter into create_ops_app():
-------------------------------------------------
Inside your create_ops_app() function, after `app = FastAPI(...)`, add:

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

STEP 4 — Decorate the endpoints that need per-route limits:
-----------------------------------------------------------

    @app.get("/status")
    @limiter.limit("60/minute")
    async def status(request: Request) -> dict:
        ...

    @app.post("/sessions/{session_id}/approve")
    @limiter.limit("30/minute")
    async def approve_session(request: Request, session_id: str) -> dict:
        ...

    @app.get("/sessions/{session_id}/decision")
    @limiter.limit("120/minute")   # polling endpoint — higher limit
    async def session_decision(request: Request, session_id: str) -> dict:
        ...

NOTE: slowapi requires `request: Request` as the FIRST parameter of each
decorated endpoint. FastAPI injects it automatically — no change needed
for the caller.

STEP 5 — Verify it works:
-------------------------

    # Should return 200 for the first 60 requests per minute:
    curl http://localhost:7477/status

    # After the limit is hit, returns:
    # HTTP 429 Too Many Requests
    # {"error": "Rate limit exceeded: 60 per 1 minute"}
