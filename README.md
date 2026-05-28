# Cross-Market Latency Arbitrage & Prediction Bot

A production-grade system that bridges traditional Forex infrastructure with Decentralized Prediction Markets (Polymarket V2, Premu.xyz, Monaco Protocol) to detect and execute arbitrage opportunities at millisecond speeds.

## Architecture

```
Admin Panel (Next.js + Tailwind, AR/EN)
         │
    REST/WebSocket
         │
    API Gateway (FastAPI)
         │
    ┌────┼────┐
    │    │    │
 Forex  Macro  Arbitrage
Engine  Events  Router
    │    │    │
    └────┼────┘
         │
  ┌──────┼──────┐
  │      │      │
Polymarket Premu Monaco
(Polygon) (Arb) (Solana)
```

## Quick Start

```bash
# 1. Copy environment variables
cp .env.example .env
# Edit .env with your actual credentials

# 2. Start all services
docker-compose up -d

# 3. Access
# Admin Panel: http://localhost:3000
# API Server:  http://localhost:8000
# API Docs:    http://localhost:8000/docs
```

## Features

- **Bilingual Admin Panel** — Arabic (RTL) and English with instant toggle
- **Forex Integration** — MetaTrader 5 SDK + OANDA streaming API
- **Polymarket V2** — CLOB API with EIP-712 signing, pUSD collateral
- **Premu.xyz** — Arbitrum Fast Markets, ERC-2612 permit execution
- **Monaco Protocol** — Solana on-chain order book with priority fees
- **Latency Arbitrage** — Forex spike → delayed prediction market odds
- **Negative Risk Arbitrage** — Multi-outcome pools with total probability < 96%
- **Kill Switch** — Instant cancellation across all platforms
- **Encrypted Vault** — AES-256-GCM for all API keys and private keys

## Project Structure

```
Trade/
├── backend/                 # Python execution engine
│   ├── app/
│   │   ├── config.py        # Centralized env-var config
│   │   ├── database.py      # Async PostgreSQL connection
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   ├── security.py      # AES encryption, JWT, HMAC
│   │   ├── main.py          # FastAPI app + all endpoints
│   │   ├── connectors/
│   │   │   ├── forex_engine.py    # MT5 + OANDA streaming
│   │   │   ├── polymarket.py      # Polymarket V2 CLOB
│   │   │   ├── premu.py           # Premu.xyz Arbitrum
│   │   │   └── monaco.py          # Monaco Protocol Solana
│   │   └── engine/
│   │       ├── arbitrage_router.py # Core arb logic
│   │       └── webhook_handler.py  # Macro event processing
│   ├── migrations/init.sql  # PostgreSQL schema
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                # Next.js admin panel
│   ├── src/
│   │   ├── app/             # Pages (dashboard, credentials, rpc, webhooks, metrics)
│   │   ├── components/      # Sidebar, LanguageToggle, Notifications
│   │   ├── i18n/            # en.json + ar.json translations
│   │   ├── lib/api.ts       # Axios + WebSocket client
│   │   └── store/           # Zustand state management
│   ├── tailwind.config.ts   # RTL + dark theme config
│   └── Dockerfile
├── docs/ARCHITECTURE.md     # Full system architecture diagram
├── docker-compose.yml       # PostgreSQL + Redis + Backend + Frontend
├── .env.example             # All required environment variables
└── .gitignore
```

## Security

- All private keys and API secrets encrypted with AES-256-GCM at rest
- Master encryption key sourced from environment variable
- JWT-based admin panel authentication
- HMAC-SHA256 webhook payload validation
- No secrets stored in code or version control
