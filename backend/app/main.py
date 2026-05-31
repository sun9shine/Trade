"""
FastAPI Application — REST API + WebSocket gateway for the Arbitrage Bot.
Includes: Auth (JWT+RBAC), Rate Limiting, Middleware, Multi-user support.
"""

import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import app_settings, risk_settings
from app.database import get_db, async_session_factory
from app.security import encrypt_secret, decrypt_secret
from app.auth import (
    UserRepository, UserRole, UserCreate, LoginRequest, TokenResponse,
    create_access_token, create_refresh_token, decode_token, check_permission,
)
from app.middleware import RateLimitMiddleware, RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.connectors.polymarket import PolymarketConnector
from app.connectors.premu import PremuConnector
from app.connectors.monaco import MonacoConnector
from app.engine.arbitrage_router import ArbitrageRouter
from app.engine.webhook_handler import WebhookHandler, MacroEventPayload
from app.repositories import TradeRepository, PositionRepository, MetricsRepository

logger = structlog.get_logger(__name__)

# ─── GLOBAL INSTANCES ─────────────────────────────────────────────────────────

polymarket = PolymarketConnector()
premu = PremuConnector()
monaco = MonacoConnector()
arb_router = ArbitrageRouter(polymarket=polymarket, premu=premu, monaco=monaco)
webhook_handler = WebhookHandler()

# WebSocket connections for live metrics
ws_connections: set[WebSocket] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info("app.starting", env=app_settings.app_env)
    # Ensure default admin exists on first run
    await UserRepository.ensure_admin_exists()
    yield
    logger.info("app.shutting_down")


# ─── APP INIT ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Cross-Market Arbitrage Bot",
    version="1.0.0",
    lifespan=lifespan,
)

# Apply middleware (order matters — last added = first executed)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Authenticate user and return JWT tokens."""
    user = await UserRepository.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(user["id"], user["username"], UserRole(user["role"]))
    refresh_token = create_refresh_token(user["id"], user["username"], UserRole(user["role"]))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 3600,
        "user": user,
    }


@app.post("/api/auth/refresh")
async def refresh_token(token: str = Header(alias="X-Refresh-Token")):
    """Refresh an access token using a valid refresh token."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    new_access = create_access_token(payload["sub"], payload["username"], UserRole(payload["role"]))
    return {"access_token": new_access, "token_type": "bearer", "expires_in": 3600}


@app.post("/api/auth/register", dependencies=[Depends(require_auth)])
async def register_user(user: UserCreate, current_user=Depends(require_auth)):
    """Create a new user (admin only)."""
    if not check_permission(UserRole(current_user["role"]), "users:write"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await UserRepository.create_user(user)
    if not result:
        raise HTTPException(status_code=409, detail="Username already exists")
    return result


@app.get("/api/auth/users", dependencies=[Depends(require_auth)])
async def list_users(current_user=Depends(require_auth)):
    """List all users (admin only)."""
    if not check_permission(UserRole(current_user["role"]), "users:read"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return await UserRepository.list_users()


def require_auth(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency to validate JWT token and extract user info."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


# ─── CREDENTIALS CRUD ─────────────────────────────────────────────────────────

class CredentialInput(BaseModel):
    service_name: str
    key_name: str
    value: str  # Plaintext — will be encrypted before storage


@app.post("/api/credentials", dependencies=[Depends(require_auth)])
async def save_credential(cred: CredentialInput):
    """Save an encrypted API credential."""
    encrypted = encrypt_secret(cred.value)
    # Store in database (simplified — use proper ORM in full impl)
    return {
        "service_name": cred.service_name,
        "key_name": cred.key_name,
        "status": "saved",
        "encrypted_preview": encrypted[:20] + "...",
    }


@app.get("/api/credentials/{service_name}", dependencies=[Depends(require_auth)])
async def get_credentials(service_name: str):
    """List credential keys for a service (values masked)."""
    # In production: query from DB
    return {"service_name": service_name, "keys": []}


# ─── RPC CONFIGURATION ────────────────────────────────────────────────────────

class RPCInput(BaseModel):
    chain: str  # polygon, arbitrum, solana
    url: str
    priority: int = 0


@app.post("/api/rpc-endpoints", dependencies=[Depends(require_auth)])
async def save_rpc_endpoint(rpc: RPCInput):
    """Save a custom RPC endpoint."""
    return {"chain": rpc.chain, "url": rpc.url, "status": "configured"}


@app.get("/api/rpc-endpoints", dependencies=[Depends(require_auth)])
async def get_rpc_endpoints():
    """List all configured RPC endpoints."""
    return {"endpoints": []}


# ─── WEBHOOK MANAGEMENT ──────────────────────────────────────────────────────

@app.post("/api/webhooks/generate", dependencies=[Depends(require_auth)])
async def generate_webhook():
    """Generate a new unique webhook URL with HMAC secret."""
    slug = secrets.token_urlsafe(16)
    hmac_secret = secrets.token_hex(32)
    webhook_url = f"/api/ingest/{slug}"
    return {
        "webhook_url": webhook_url,
        "hmac_secret": hmac_secret,
        "slug": slug,
        "status": "active",
    }


@app.post("/api/ingest/{slug}")
async def ingest_webhook(slug: str, payload: MacroEventPayload):
    """
    Public webhook endpoint for macroeconomic event ingestion.
    External feeds push JSON payloads here.
    """
    result = await webhook_handler.process_event(payload)

    # If actionable, push to arb router
    if result["should_execute"]:
        # Broadcast to WebSocket clients
        await broadcast_ws({"type": "macro_event", "data": result})

    return {"status": "received", "processed": result["should_execute"]}


# ─── LIVE METRICS ─────────────────────────────────────────────────────────────

@app.get("/api/metrics", dependencies=[Depends(require_auth)])
async def get_metrics():
    """Get current system metrics snapshot."""
    return {
        "total_pnl_usd": 0.0,
        "open_positions": 0,
        "total_trades_today": 0,
        "gas_balances": {
            "polygon_matic": 0.0,
            "arbitrum_eth": 0.0,
            "solana_sol": 0.0,
        },
        "avg_latency_ms": 0.0,
        "kill_switch_active": risk_settings.kill_switch_enabled,
    }


# ─── KILL SWITCH ──────────────────────────────────────────────────────────────

@app.post("/api/kill-switch/activate", dependencies=[Depends(require_auth)])
async def activate_kill_switch():
    """Emergency: cancel ALL orders across ALL platforms."""
    await arb_router.activate_kill_switch()
    await broadcast_ws({"type": "kill_switch", "active": True})
    return {"status": "activated", "message": "All orders cancelled across all platforms"}


@app.post("/api/kill-switch/deactivate", dependencies=[Depends(require_auth)])
async def deactivate_kill_switch():
    """Re-enable trading after kill switch."""
    arb_router.deactivate_kill_switch()
    await broadcast_ws({"type": "kill_switch", "active": False})
    return {"status": "deactivated"}


# ─── WEBSOCKET (Live Metrics Stream) ─────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket connection for real-time metrics streaming to admin panel."""
    await ws.accept()
    ws_connections.add(ws)
    logger.info("ws.connected", total=len(ws_connections))
    try:
        while True:
            # Keep connection alive, listen for pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        ws_connections.discard(ws)
        logger.info("ws.disconnected", total=len(ws_connections))


async def broadcast_ws(message: dict):
    """Broadcast a message to all connected WebSocket clients."""
    import orjson
    data = orjson.dumps(message).decode()
    disconnected = set()
    for ws in ws_connections:
        try:
            await ws.send_text(data)
        except Exception:
            disconnected.add(ws)
    ws_connections -= disconnected


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
