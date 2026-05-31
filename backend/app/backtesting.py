"""
Backtesting Engine — Test arbitrage strategies on historical data.
Supports:
- Historical forex tick replay
- Simulated prediction market odds
- Strategy performance metrics (Sharpe, max drawdown, win rate)
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog

from app.connectors.forex_engine import TickData
from app.engine.arbitrage_router import ArbitrageRouter, ArbSignal

logger = structlog.get_logger(__name__)


@dataclass
class BacktestTrade:
    """A simulated trade during backtesting."""
    entry_time: datetime
    exit_time: Optional[datetime] = None
    platform: str = ""
    direction: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    size_usd: float = 0.0
    pnl_usd: float = 0.0
    signal_type: str = ""
    edge_pct: float = 0.0


@dataclass
class BacktestResult:
    """Complete backtesting result with performance metrics."""
    strategy_name: str
    start_date: str
    end_date: str
    total_ticks: int
    total_signals: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_consecutive_losses: int
    avg_trade_duration_minutes: float
    trades: list[dict] = field(default_factory=list)


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    strategy: str = "latency_arb"  # "latency_arb" or "neg_risk_arb"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000.0
    position_size_usd: float = 100.0
    min_edge_pct: float = 1.5
    slippage_bps: int = 5  # Basis points of slippage
    commission_bps: int = 0
    market_delay_ms: int = 500  # Simulated market reaction delay


class BacktestEngine:
    """
    Runs backtests by replaying historical tick data through the
    arbitrage detection logic and simulating executions.
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self._trades: list[BacktestTrade] = []
        self._equity_curve: list[float] = []
        self._capital = config.initial_capital
        self._peak_capital = config.initial_capital
        self._max_drawdown = 0.0
        self._signal_count = 0

    async def run(self, tick_data: list[dict]) -> BacktestResult:
        """
        Run backtest on historical tick data.

        Args:
            tick_data: List of dicts with keys: symbol, bid, ask, timestamp_ms
        """
        logger.info(
            "backtest.starting",
            strategy=self.config.strategy,
            ticks=len(tick_data),
            capital=self.config.initial_capital,
        )

        # Build tick buffer for anomaly detection
        buffer: dict[str, list[float]] = {}
        buffer_window = 50

        for i, raw_tick in enumerate(tick_data):
            tick = TickData(
                symbol=raw_tick["symbol"],
                bid=raw_tick["bid"],
                ask=raw_tick["ask"],
                spread=raw_tick["ask"] - raw_tick["bid"],
                source="backtest",
                timestamp_ms=raw_tick["timestamp_ms"],
            )

            # Update buffer
            symbol = tick.symbol
            if symbol not in buffer:
                buffer[symbol] = []

            mid = (tick.bid + tick.ask) / 2
            buffer[symbol].append(mid)
            if len(buffer[symbol]) > buffer_window:
                buffer[symbol].pop(0)

            # Check for anomaly (same logic as live engine)
            if len(buffer[symbol]) >= 10:
                recent_mean = np.mean(buffer[symbol][-10:])
                baseline_mean = np.mean(buffer[symbol][:-10]) if len(buffer[symbol]) > 10 else recent_mean

                if baseline_mean > 0:
                    pct_change = abs(recent_mean - baseline_mean) / baseline_mean * 100

                    if pct_change >= self.config.min_edge_pct:
                        self._signal_count += 1
                        direction = "up" if recent_mean > baseline_mean else "down"

                        # Simulate trade execution
                        self._simulate_trade(
                            tick=tick,
                            pct_change=pct_change,
                            direction=direction,
                            tick_index=i,
                            future_ticks=tick_data[i:i+60],  # Look ahead 60 ticks
                        )

            # Track equity curve
            if i % 100 == 0:
                self._equity_curve.append(self._capital)

        # Calculate final metrics
        return self._calculate_results(len(tick_data))

    def _simulate_trade(
        self,
        tick: TickData,
        pct_change: float,
        direction: str,
        tick_index: int,
        future_ticks: list[dict],
    ):
        """Simulate entering and exiting a trade."""
        # Apply slippage to entry
        slippage = self.config.slippage_bps / 10000
        entry_price = tick.ask * (1 + slippage) if direction == "up" else tick.bid * (1 - slippage)

        # Simulate exit after market reacts (using future ticks)
        exit_price = entry_price
        exit_time_ms = tick.timestamp_ms

        if len(future_ticks) > 10:
            # Exit after ~10 ticks (market should have reacted)
            future_tick = future_ticks[min(10, len(future_ticks) - 1)]
            if direction == "up":
                exit_price = future_tick["bid"] * (1 - slippage)
            else:
                exit_price = future_tick["ask"] * (1 + slippage)
            exit_time_ms = future_tick["timestamp_ms"]

        # Calculate PnL
        if direction == "up":
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - exit_price) / entry_price

        # Apply commission
        commission = self.config.commission_bps / 10000 * 2  # Round trip
        pnl_pct -= commission

        pnl_usd = self.config.position_size_usd * pnl_pct
        self._capital += pnl_usd

        # Track drawdown
        if self._capital > self._peak_capital:
            self._peak_capital = self._capital
        drawdown = (self._peak_capital - self._capital) / self._peak_capital
        if drawdown > self._max_drawdown:
            self._max_drawdown = drawdown

        trade = BacktestTrade(
            entry_time=datetime.fromtimestamp(tick.timestamp_ms / 1000, tz=timezone.utc),
            exit_time=datetime.fromtimestamp(exit_time_ms / 1000, tz=timezone.utc),
            platform="simulated",
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            size_usd=self.config.position_size_usd,
            pnl_usd=pnl_usd,
            signal_type=self.config.strategy,
            edge_pct=pct_change,
        )
        self._trades.append(trade)

    def _calculate_results(self, total_ticks: int) -> BacktestResult:
        """Calculate comprehensive performance metrics."""
        if not self._trades:
            return BacktestResult(
                strategy_name=self.config.strategy,
                start_date="",
                end_date="",
                total_ticks=total_ticks,
                total_signals=self._signal_count,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                total_pnl=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                win_rate=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_factor=0.0,
                max_consecutive_losses=0,
                avg_trade_duration_minutes=0.0,
            )

        pnls = [t.pnl_usd for t in self._trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        # Sharpe Ratio (annualized, assuming ~252 trading days)
        returns = np.array(pnls) / self.config.position_size_usd
        sharpe = 0.0
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252)

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Max consecutive losses
        max_consec = 0
        current_consec = 0
        for p in pnls:
            if p <= 0:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0

        # Avg trade duration
        durations = []
        for t in self._trades:
            if t.exit_time and t.entry_time:
                dur = (t.exit_time - t.entry_time).total_seconds() / 60
                durations.append(dur)

        return BacktestResult(
            strategy_name=self.config.strategy,
            start_date=self._trades[0].entry_time.isoformat() if self._trades else "",
            end_date=self._trades[-1].entry_time.isoformat() if self._trades else "",
            total_ticks=total_ticks,
            total_signals=self._signal_count,
            total_trades=len(self._trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            total_pnl=sum(pnls),
            max_drawdown=self._max_drawdown * 100,
            sharpe_ratio=round(sharpe, 3),
            win_rate=len(wins) / len(self._trades) * 100 if self._trades else 0,
            avg_win=np.mean(wins) if wins else 0,
            avg_loss=np.mean(losses) if losses else 0,
            profit_factor=round(profit_factor, 3),
            max_consecutive_losses=max_consec,
            avg_trade_duration_minutes=np.mean(durations) if durations else 0,
            trades=[
                {
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                    "direction": t.direction,
                    "entry_price": round(t.entry_price, 6),
                    "exit_price": round(t.exit_price, 6),
                    "pnl_usd": round(t.pnl_usd, 2),
                    "edge_pct": round(t.edge_pct, 3),
                }
                for t in self._trades[-100:]  # Last 100 trades
            ],
        )
