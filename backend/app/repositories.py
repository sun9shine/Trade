"""
Database Repository Layer — CRUD operations for trades, positions, and metrics.
Provides a clean interface between the execution engine and PostgreSQL.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import (
    TradeExecution,
    OpenPosition,
    ForexTick,
    MacroEvent,
    MetricsSnapshot,
    EncryptedCredential,
    RPCEndpoint,
    WebhookEndpoint,
)

logger = structlog.get_logger(__name__)


# ─── TRADE EXECUTION REPOSITORY ──────────────────────────────────────────────

class TradeRepository:
    """CRUD operations for trade executions."""

    @staticmethod
    async def create(
        platform: str,
        market_id: str,
        direction: str,
        outcome: Optional[str],
        quantity: float,
        price: float,
        total_cost_usd: float,
        strategy: str,
        signal_source: Optional[str] = None,
        tx_hash: Optional[str] = None,
        gas_cost_usd: Optional[float] = None,
        status: str = "pending",
    ) -> Optional[UUID]:
        """Record a new trade execution."""
        try:
            async with async_session_factory() as session:
                trade = TradeExecution(
                    platform=platform,
                    market_id=market_id,
                    direction=direction,
                    outcome=outcome,
                    quantity=quantity,
                    price=price,
                    total_cost_usd=total_cost_usd,
                    gas_cost_usd=gas_cost_usd,
                    tx_hash=tx_hash,
                    status=status,
                    strategy=strategy,
                    signal_source=signal_source,
                )
                session.add(trade)
                await session.commit()
                await session.refresh(trade)
                logger.info("repo.trade_created", trade_id=str(trade.id), platform=platform)
                return trade.id
        except Exception as e:
            logger.error("repo.trade_create_failed", error=str(e))
            return None

    @staticmethod
    async def update_status(
        trade_id: UUID,
        status: str,
        tx_hash: Optional[str] = None,
        gas_cost_usd: Optional[float] = None,
        pnl_usd: Optional[float] = None,
    ):
        """Update trade status after confirmation or failure."""
        try:
            async with async_session_factory() as session:
                values = {"status": status}
                if tx_hash:
                    values["tx_hash"] = tx_hash
                if gas_cost_usd is not None:
                    values["gas_cost_usd"] = gas_cost_usd
                if pnl_usd is not None:
                    values["pnl_usd"] = pnl_usd
                if status == "confirmed":
                    values["settled_at"] = datetime.now(timezone.utc)

                stmt = update(TradeExecution).where(TradeExecution.id == trade_id).values(**values)
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error("repo.trade_update_failed", error=str(e))

    @staticmethod
    async def get_trades_today(platform: Optional[str] = None) -> list[dict]:
        """Get all trades from today."""
        try:
            async with async_session_factory() as session:
                today_start = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                stmt = select(TradeExecution).where(
                    TradeExecution.executed_at >= today_start
                )
                if platform:
                    stmt = stmt.where(TradeExecution.platform == platform)
                stmt = stmt.order_by(TradeExecution.executed_at.desc())

                result = await session.execute(stmt)
                trades = result.scalars().all()
                return [
                    {
                        "id": str(t.id),
                        "platform": t.platform,
                        "market_id": t.market_id,
                        "direction": t.direction,
                        "quantity": t.quantity,
                        "price": t.price,
                        "total_cost_usd": t.total_cost_usd,
                        "tx_hash": t.tx_hash,
                        "status": t.status,
                        "strategy": t.strategy,
                        "pnl_usd": t.pnl_usd,
                        "executed_at": t.executed_at.isoformat() if t.executed_at else None,
                    }
                    for t in trades
                ]
        except Exception as e:
            logger.error("repo.get_trades_today_failed", error=str(e))
            return []

    @staticmethod
    async def get_total_pnl() -> float:
        """Calculate total realized PnL across all settled trades."""
        try:
            async with async_session_factory() as session:
                stmt = select(func.sum(TradeExecution.pnl_usd)).where(
                    TradeExecution.pnl_usd.isnot(None)
                )
                result = await session.execute(stmt)
                total = result.scalar()
                return total or 0.0
        except Exception as e:
            logger.error("repo.get_pnl_failed", error=str(e))
            return 0.0

    @staticmethod
    async def count_today() -> int:
        """Count trades executed today."""
        try:
            async with async_session_factory() as session:
                today_start = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                stmt = select(func.count(TradeExecution.id)).where(
                    TradeExecution.executed_at >= today_start
                )
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            logger.error("repo.count_today_failed", error=str(e))
            return 0


# ─── POSITION REPOSITORY ─────────────────────────────────────────────────────

class PositionRepository:
    """CRUD operations for open positions."""

    @staticmethod
    async def open_position(
        platform: str,
        market_id: str,
        market_title: Optional[str],
        outcome: str,
        shares: float,
        avg_entry_price: float,
    ) -> Optional[UUID]:
        """Open a new position or add to existing one."""
        try:
            async with async_session_factory() as session:
                # Check if position already exists for this market+outcome
                stmt = select(OpenPosition).where(
                    and_(
                        OpenPosition.platform == platform,
                        OpenPosition.market_id == market_id,
                        OpenPosition.outcome == outcome,
                    )
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing position (average in)
                    total_cost = (existing.shares * existing.avg_entry_price) + (shares * avg_entry_price)
                    new_shares = existing.shares + shares
                    new_avg = total_cost / new_shares if new_shares > 0 else 0

                    existing.shares = new_shares
                    existing.avg_entry_price = new_avg
                    existing.updated_at = datetime.now(timezone.utc)
                    await session.commit()
                    return existing.id
                else:
                    # Create new position
                    position = OpenPosition(
                        platform=platform,
                        market_id=market_id,
                        market_title=market_title,
                        outcome=outcome,
                        shares=shares,
                        avg_entry_price=avg_entry_price,
                    )
                    session.add(position)
                    await session.commit()
                    await session.refresh(position)
                    return position.id

        except Exception as e:
            logger.error("repo.open_position_failed", error=str(e))
            return None

    @staticmethod
    async def close_position(position_id: UUID, close_price: float) -> Optional[float]:
        """Close a position and calculate PnL."""
        try:
            async with async_session_factory() as session:
                stmt = select(OpenPosition).where(OpenPosition.id == position_id)
                result = await session.execute(stmt)
                position = result.scalar_one_or_none()

                if not position:
                    return None

                pnl = (close_price - position.avg_entry_price) * position.shares
                await session.delete(position)
                await session.commit()

                logger.info(
                    "repo.position_closed",
                    position_id=str(position_id),
                    pnl=pnl,
                )
                return pnl

        except Exception as e:
            logger.error("repo.close_position_failed", error=str(e))
            return None

    @staticmethod
    async def update_current_prices(platform: str, prices: dict[str, float]):
        """Batch update current prices and unrealized PnL for a platform."""
        try:
            async with async_session_factory() as session:
                stmt = select(OpenPosition).where(OpenPosition.platform == platform)
                result = await session.execute(stmt)
                positions = result.scalars().all()

                for pos in positions:
                    key = f"{pos.market_id}_{pos.outcome}"
                    if key in prices:
                        pos.current_price = prices[key]
                        pos.unrealized_pnl = (prices[key] - pos.avg_entry_price) * pos.shares
                        pos.updated_at = datetime.now(timezone.utc)

                await session.commit()
        except Exception as e:
            logger.error("repo.update_prices_failed", error=str(e))

    @staticmethod
    async def get_all_open() -> list[dict]:
        """Get all open positions across all platforms."""
        try:
            async with async_session_factory() as session:
                stmt = select(OpenPosition).order_by(OpenPosition.opened_at.desc())
                result = await session.execute(stmt)
                positions = result.scalars().all()
                return [
                    {
                        "id": str(p.id),
                        "platform": p.platform,
                        "market_id": p.market_id,
                        "market_title": p.market_title,
                        "outcome": p.outcome,
                        "shares": p.shares,
                        "avg_entry_price": p.avg_entry_price,
                        "current_price": p.current_price,
                        "unrealized_pnl": p.unrealized_pnl,
                        "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                    }
                    for p in positions
                ]
        except Exception as e:
            logger.error("repo.get_positions_failed", error=str(e))
            return []

    @staticmethod
    async def count_open() -> int:
        """Count total open positions."""
        try:
            async with async_session_factory() as session:
                stmt = select(func.count(OpenPosition.id))
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            return 0

    @staticmethod
    async def close_all_for_platform(platform: str):
        """Close all positions for a platform (used by kill switch)."""
        try:
            async with async_session_factory() as session:
                stmt = delete(OpenPosition).where(OpenPosition.platform == platform)
                await session.execute(stmt)
                await session.commit()
                logger.info("repo.all_positions_closed", platform=platform)
        except Exception as e:
            logger.error("repo.close_all_failed", error=str(e))


# ─── METRICS REPOSITORY ──────────────────────────────────────────────────────

class MetricsRepository:
    """Operations for metrics snapshots."""

    @staticmethod
    async def save_snapshot(
        total_pnl: float,
        open_positions: int,
        trades_today: int,
        polygon_gas: float,
        arbitrum_gas: float,
        solana_gas: float,
        avg_latency: float,
        kill_switch: bool,
    ):
        """Save a metrics snapshot."""
        try:
            async with async_session_factory() as session:
                snapshot = MetricsSnapshot(
                    total_pnl_usd=total_pnl,
                    open_position_count=open_positions,
                    total_trades_today=trades_today,
                    polygon_gas_balance=polygon_gas,
                    arbitrum_gas_balance=arbitrum_gas,
                    solana_gas_balance=solana_gas,
                    avg_latency_ms=avg_latency,
                    kill_switch_active=kill_switch,
                )
                session.add(snapshot)
                await session.commit()
        except Exception as e:
            logger.error("repo.save_snapshot_failed", error=str(e))

    @staticmethod
    async def get_latest() -> Optional[dict]:
        """Get the most recent metrics snapshot."""
        try:
            async with async_session_factory() as session:
                stmt = (
                    select(MetricsSnapshot)
                    .order_by(MetricsSnapshot.recorded_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                snap = result.scalar_one_or_none()
                if not snap:
                    return None
                return {
                    "total_pnl_usd": snap.total_pnl_usd,
                    "open_positions": snap.open_position_count,
                    "trades_today": snap.total_trades_today,
                    "gas_balances": {
                        "polygon_matic": snap.polygon_gas_balance or 0,
                        "arbitrum_eth": snap.arbitrum_gas_balance or 0,
                        "solana_sol": snap.solana_gas_balance or 0,
                    },
                    "avg_latency_ms": snap.avg_latency_ms or 0,
                    "kill_switch_active": snap.kill_switch_active,
                    "recorded_at": snap.recorded_at.isoformat() if snap.recorded_at else None,
                }
        except Exception as e:
            logger.error("repo.get_latest_metrics_failed", error=str(e))
            return None


# ─── MACRO EVENT REPOSITORY ──────────────────────────────────────────────────

class MacroEventRepository:
    """Operations for macro economic events."""

    @staticmethod
    async def save_event(
        event_type: str,
        country: str,
        headline: str,
        impact_level: str,
        source: str,
        actual_value: Optional[str] = None,
        forecast_value: Optional[str] = None,
        previous_value: Optional[str] = None,
        raw_payload: Optional[str] = None,
    ) -> Optional[UUID]:
        """Persist an ingested macro event."""
        try:
            async with async_session_factory() as session:
                event = MacroEvent(
                    event_type=event_type,
                    country=country,
                    headline=headline,
                    actual_value=actual_value,
                    forecast_value=forecast_value,
                    previous_value=previous_value,
                    impact_level=impact_level,
                    source=source,
                    raw_payload=raw_payload,
                )
                session.add(event)
                await session.commit()
                await session.refresh(event)
                return event.id
        except Exception as e:
            logger.error("repo.save_event_failed", error=str(e))
            return None

    @staticmethod
    async def get_recent(limit: int = 50) -> list[dict]:
        """Get recent macro events."""
        try:
            async with async_session_factory() as session:
                stmt = (
                    select(MacroEvent)
                    .order_by(MacroEvent.received_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                events = result.scalars().all()
                return [
                    {
                        "id": str(e.id),
                        "event_type": e.event_type,
                        "country": e.country,
                        "headline": e.headline,
                        "actual_value": e.actual_value,
                        "forecast_value": e.forecast_value,
                        "impact_level": e.impact_level,
                        "source": e.source,
                        "processed": e.processed,
                        "received_at": e.received_at.isoformat() if e.received_at else None,
                    }
                    for e in events
                ]
        except Exception as e:
            logger.error("repo.get_events_failed", error=str(e))
            return []


# ─── CREDENTIAL REPOSITORY ───────────────────────────────────────────────────

class CredentialRepository:
    """Operations for encrypted credentials."""

    @staticmethod
    async def upsert(service_name: str, key_name: str, encrypted_value: str):
        """Create or update an encrypted credential."""
        try:
            async with async_session_factory() as session:
                stmt = select(EncryptedCredential).where(
                    and_(
                        EncryptedCredential.service_name == service_name,
                        EncryptedCredential.key_name == key_name,
                    )
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.encrypted_value = encrypted_value
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    cred = EncryptedCredential(
                        service_name=service_name,
                        key_name=key_name,
                        encrypted_value=encrypted_value,
                    )
                    session.add(cred)

                await session.commit()
        except Exception as e:
            logger.error("repo.upsert_credential_failed", error=str(e))

    @staticmethod
    async def get_encrypted(service_name: str, key_name: str) -> Optional[str]:
        """Retrieve an encrypted credential value."""
        try:
            async with async_session_factory() as session:
                stmt = select(EncryptedCredential.encrypted_value).where(
                    and_(
                        EncryptedCredential.service_name == service_name,
                        EncryptedCredential.key_name == key_name,
                    )
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error("repo.get_credential_failed", error=str(e))
            return None

    @staticmethod
    async def list_keys(service_name: str) -> list[str]:
        """List all key names for a service (values stay encrypted)."""
        try:
            async with async_session_factory() as session:
                stmt = select(EncryptedCredential.key_name).where(
                    EncryptedCredential.service_name == service_name
                )
                result = await session.execute(stmt)
                return [row[0] for row in result.all()]
        except Exception as e:
            logger.error("repo.list_keys_failed", error=str(e))
            return []

    @staticmethod
    async def delete(service_name: str, key_name: str):
        """Delete a credential."""
        try:
            async with async_session_factory() as session:
                stmt = delete(EncryptedCredential).where(
                    and_(
                        EncryptedCredential.service_name == service_name,
                        EncryptedCredential.key_name == key_name,
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error("repo.delete_credential_failed", error=str(e))


# ─── FOREX TICK REPOSITORY ───────────────────────────────────────────────────

class TickRepository:
    """Operations for forex tick data."""

    @staticmethod
    async def save_batch(ticks: list[dict]):
        """Save a batch of tick data."""
        try:
            async with async_session_factory() as session:
                for t in ticks:
                    tick = ForexTick(
                        symbol=t["symbol"],
                        bid=t["bid"],
                        ask=t["ask"],
                        spread=t["spread"],
                        source=t["source"],
                        timestamp=t["timestamp"],
                    )
                    session.add(tick)
                await session.commit()
        except Exception as e:
            logger.error("repo.save_ticks_failed", error=str(e))

    @staticmethod
    async def cleanup_old(hours: int = 24):
        """Delete ticks older than N hours."""
        try:
            async with async_session_factory() as session:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                stmt = delete(ForexTick).where(ForexTick.timestamp < cutoff)
                result = await session.execute(stmt)
                await session.commit()
                logger.info("repo.ticks_cleaned", deleted=result.rowcount)
        except Exception as e:
            logger.error("repo.tick_cleanup_failed", error=str(e))
