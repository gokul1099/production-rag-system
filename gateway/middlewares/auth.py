import os
from fastapi import HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from dotenv import load_dotenv
import logfire
import jwt

load_dotenv()


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware that validates API keys or JWT tokens on every request
    """

    def __init__(self, app):
        super().__init__(app)
        self.valid_keys = os.getenv("GATEWAY_API_KEYS", "").split(",")
        self.valid_keys = [key.strip() for key in self.valid_keys if key.strip()]

        self.public_endpoints = ["/docs", "/redoc", "/openapi.json", "/health", "/auth/signup", "/auth/signin"]

        self.jwt_secret = os.getenv("JWT_SECRET", "")
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        valid_algorithms = {
            "HS256", "HS384", "HS512",
            "RS256", "RS384", "RS512",
            "ES256", "ES384", "ES512",
            "PS256", "PS384", "PS512",
        }
        if self.jwt_algorithm not in valid_algorithms:
            self.jwt_algorithm = "HS256"

    async def dispatch(self, request, call_next):
        # Skip public endpoints
        if request.url.path in self.public_endpoints:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logfire.warn(f"gatewayservice: Missing Authorization header from {getattr(request.client, 'host', 'unknown')}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing Authorization header"}
            )

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logfire.warn(f"gatewayservice: Invalid Authorization format from {getattr(request.client, 'host', 'unknown')}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid Authorization header format. Use: Bearer <token>"}
            )

        token = parts[1]

        # First check if token matches a static API key
        if token in self.valid_keys:
            logfire.info(f"gatewayservice: Valid API key authenticated from {getattr(request.client, 'host', 'unknown')}")
            return await call_next(request)

        # Otherwise treat it as JWT and validate
        if not self.jwt_secret:
            logfire.warn("gatewayservice: JWT_SECRET not configured in gateway; rejecting JWT authentication")
            return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Unauthorized"})

        try:
            decoded = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            # Attach user info to request.state for downstream handlers
            request.state.user = decoded
            logfire.info(f"gatewayservice: Valid JWT for sub={decoded.get('sub')} from {getattr(request.client, 'host', 'unknown')}")
            return await call_next(request)
        except jwt.ExpiredSignatureError:
            logfire.warn(f"gatewayservice: Expired JWT from {getattr(request.client, 'host', 'unknown')}")
            return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Token expired"})
        except jwt.InvalidTokenError as e:
            logfire.warn(f"gatewayservice: Invalid JWT from {getattr(request.client, 'host', 'unknown')}: {e}")
            return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Invalid token"})
