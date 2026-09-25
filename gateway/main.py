import logfire
import os
from dotenv import load_dotenv
from gateway.middlewares.auth import AuthMiddleware
from gateway.middlewares.rate_limit import RateLimitMiddleware
import httpx
from fastapi import FastAPI, Response, Request, status
from starlette.responses import StreamingResponse
from typing import Dict, AsyncIterator

load_dotenv()
logfire.configure(token=os.getenv("LOGFIRE_TOKEN"), scrubbing=False)


app = FastAPI(title="Enterprise RAG gateway")

app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)


BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://api:8000")
HTTPX_TIMEOUT = float(os.getenv("GATEWAY_HTTP_TIMEOUT", "30.0"))

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

def _strip_hop_by_hop(headers: Dict[str, str]) -> Dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP_HEADERS and k.lower() != "host"}

async def _iter_request_body(request: Request) -> AsyncIterator[bytes]:
    async for chunk in request.stream():
        if chunk:
            yield chunk

@app.get("/")
def home():
    return {"message": "Enterprice langgraph RAG gateway is live"}

@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_stream(full_path: str, request: Request):
    client_host = request.client.host if request.client else "unknown"
    backend_url = f"{BACKEND_API_URL.rstrip('/')}/{full_path.lstrip('/')}"
    if request.url.query:
        backend_url = f"{backend_url}?{request.url.query}"

    # Forward headers (strip hop-by-hop)
    forward_headers = dict(request.headers)
    forward_headers = _strip_hop_by_hop(forward_headers)
    # X-Forwarded headers
    xff = forward_headers.get("x-forwarded-for", "")
    forward_headers["x-forwarded-for"] = (xff + ", " if xff else "") + client_host
    forward_headers["x-forwarded-proto"] = request.url.scheme
    forward_headers["x-forwarded-host"] = request.url.hostname or forward_headers.get("host", "")

    # Optionally remove Authorization if gateway handles auth only:
    # forward_headers.pop("authorization", None)

    # Read request body for non-GET methods
    body_bytes = await request.body()
    content = body_bytes if request.method not in ("GET", "HEAD", "OPTIONS") and body_bytes else None

    async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=backend_url,
                headers=forward_headers,
                content=content,
            )
            response_headers = _strip_hop_by_hop(dict(resp.headers))
            content_type = resp.headers.get("content-type")

            logfire.info(
                f"gatewayservice: proxied {request.method} {request.url.path} -> {backend_url} (status={resp.status_code})"
            )

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=response_headers,
                media_type=content_type,
            )

        except httpx.TimeoutException:
            logfire.warn(f"gatewayservice: backend request timed out -> {backend_url}")
            return Response(content="Gateway timeout", status_code=status.HTTP_504_GATEWAY_TIMEOUT)
        except httpx.HTTPError as e:
            logfire.error(f"gatewayservice: backend request failed: {e}", extra={"url": backend_url})
            return Response(content=f"Bad gateway: {e}", status_code=status.HTTP_502_BAD_GATEWAY)

