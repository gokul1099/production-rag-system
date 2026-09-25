import time
from collections import deque
from typing import Deque, Dict

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from dotenv import load_dotenv
import os
import logfire

load_dotenv()

RATE_LIMIT_REQUESTS = int(os.getenv("GATEWAY_RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GATE_LIMIT_WINDOW_SECONDS", "60"))

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

        self._requests: Dict[str, Deque[float]] = {}
        self.public_endpoints = ["/", "/docs", "/redoc", "/openapi.json", "/health", "/favicon.ico", "/auth/signup", "/auth/signin"]

    async def dispatch(self, request: Request, call_next):
        normalized_path = request.url.path.rstrip('/') or '/'
        if request.url.path in self.public_endpoints or normalized_path in self.public_endpoints or normalized_path.startswith('/auth'):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        identifier = None

        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                identifier = parts[1]
        if not identifier:
            client = request.client.host if request.client else "unknown"
            identifier = f"ip:{client}"

        now = time.time()
        window = RATE_LIMIT_WINDOW_SECONDS
        limit = RATE_LIMIT_REQUESTS

        dq = self._requests.setdefault(identifier, deque())
        while dq and dq[0] <= now - window:
            dq.popleft()

        if len(dq) >= limit:
            retry_after = int(window - (now - dq[0])) if dq else window
            logfire.warn(f"gatewayservice: Rate limit exceeded for {identifier} (limit={limit}/{window})")
            headers = {"Retry-After": str(retry_after)}
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests. Please retry later"},
                headers=headers,
            )

        dq.append(now)
        return await call_next(request)