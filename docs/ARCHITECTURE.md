# Cross-Market Latency Arbitrage & Prediction Bot — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ADMIN PANEL (Next.js + Tailwind)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌────────────┐  │
│  │ API Keys │ │ RPC Cfg  │ │ Webhook Mgmt │ │  Metrics  │ │ Kill Switch│  │
│  └──────────┘ └──────────┘ └──────────────┘ └───────────┘ └────────────┘  │
│          AR/EN Bilingual │ RTL/LTR Dynamic │ i18n Toggle                    │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ REST/WebSocket
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      API GATEWAY (FastAPI + WebSocket Server)                 │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────────────────┐    │
│  │ Auth/JWT     │  │ Config CRUD    │  │ Webhook Ingest Endpoints     │    │
│  └──────────────┘  └────────────────┘  └──────────────────────────────┘    │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼──────────────────────────┐
        ▼                           ▼                          ▼
┌───────────────┐  ┌────────────────────────────┐  ┌────────────────────────┐
│ FOREX ENGINE  │  │  MACRO-EVENT ENGINE         │  │  ARBITRAGE ROUTER      │
│               │  │                              │  │                        │
│ • MT5 SDK     │  │ • Webhook Listener           │  │ • Latency Arb Logic    │
│ • FIX Proto   │  │ • Calendar Parser            │  │ • Neg Risk Arb Logic   │
│ • OANDA WS    │  │ • Reuters/Bloomberg Feed     │  │ • Position Sizing      │
│ • Tick Store  │  │ • Event Classification       │  │ • Risk Limits          │
└───────┬───────┘  └─────────────┬────────────────┘  └───────────┬──────────┘
        │                        │                                │
        └────────────────────────┼────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EXECUTION LAYER (DEX Connectors)                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │ POLYMARKET V2    │  │ PREMU.XYZ        │  │ MONACO PROTOCOL          │  │
│  │                  │  │                  │  │                          │  │
│  │ • CLOB API       │  │ • Arbitrum Vault │  │ • Solana Order Book      │  │
│  │ • EIP-712 Sign   │  │ • ERC-2612 Permit│  │ • @monaco-protocol/sdk  │  │
│  │ • pUSD Collateral│  │ • 5-min Markets  │  │ • Priority Fee Mgmt     │  │
│  │ • Polygon RPC    │  │ • Arbitrum RPC   │  │ • Solana RPC             │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER (PostgreSQL + Redis)                     │
│  ┌───────────────────────┐  ┌─────────────────────┐  ┌──────────────────┐  │
│  │ Encrypted Credentials │  │ Trade/Position Log   │  │ Redis Pub/Sub    │  │
│  │ (AES-256-GCM)        │  │ PnL Tracking         │  │ Real-time Metrics│  │
│  └───────────────────────┘  └─────────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Technology Stack

| Layer          | Technology                        | Purpose                                |
|----------------|-----------------------------------|----------------------------------------|
| Frontend       | Next.js 14, Tailwind CSS, i18next | Bilingual admin panel (AR/EN)          |
| API Server     | FastAPI (Python 3.11+)            | REST + WebSocket gateway               |
| Forex Engine   | MetaTrader5 SDK, simplefix        | FIX protocol & tick data ingestion     |
| DEX: Polymarket| py-clob-client, web3.py           | CLOB orders, EIP-712 signing           |
| DEX: Premu     | web3.py (Arbitrum)                | Vault contract interaction             |
| DEX: Monaco    | solana-py, anchorpy               | Solana order book execution            |
| Database       | PostgreSQL 15                     | Persistent config, trades, audit log   |
| Cache/PubSub   | Redis 7                           | Real-time metrics streaming            |
| Encryption     | cryptography (Fernet/AES-256)     | API keys & private key vault           |
| Containers     | Docker Compose                    | Local & production deployment          |

## Data Flow

1. **Forex Tick → Event Detection:** MT5/OANDA feeds stream ticks via WebSocket → Anomaly detection (>1.5% spike within 500ms window)
2. **Macro Event → Classification:** Webhook receives Reuters/Bloomberg JSON → NLP classifier tags urgency level
3. **Signal → Arbitrage Check:** Router checks prediction market odds vs. implied fair value from forex data
4. **Execution → Multi-chain:** Simultaneous execution on Polygon (Polymarket), Arbitrum (Premu), Solana (Monaco)
5. **Monitoring → Dashboard:** All state pushed to Redis pub/sub → WebSocket relay to Next.js admin panel

## Security Model

- All private keys encrypted at rest with AES-256-GCM (master key from env)
- JWT authentication for admin panel access
- Rate limiting on all API endpoints
- Webhook payloads validated via HMAC signatures
- Environment-variable-driven configuration (no secrets in code)
