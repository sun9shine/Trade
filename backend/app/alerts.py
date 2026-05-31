"""
Monitoring & Alerting System
- Telegram notifications for critical events
- Email alerts via SMTP
- Configurable alert thresholds
- Rate-limited to prevent spam
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx
import structlog

from app.config import app_settings

logger = structlog.get_logger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertConfig:
    """Alert configuration loaded from environment."""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    alert_email_to: str = ""
    enabled: bool = True
    min_interval_seconds: int = 60  # Minimum time between same alerts


@dataclass
class AlertState:
    """Tracks alert sending to prevent spam."""
    last_sent: dict = field(default_factory=dict)  # alert_key → timestamp
    total_sent: int = 0


class AlertManager:
    """
    Sends notifications via Telegram and Email for critical trading events.
    Implements rate limiting to prevent alert fatigue.
    """

    def __init__(self, config: Optional[AlertConfig] = None):
        self.config = config or AlertConfig()
        self._state = AlertState()
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    def _should_send(self, alert_key: str) -> bool:
        """Check rate limit for this alert type."""
        if not self.config.enabled:
            return False
        now = time.time()
        last = self._state.last_sent.get(alert_key, 0)
        if now - last < self.config.min_interval_seconds:
            return False
        self._state.last_sent[alert_key] = now
        return True

    # ─── TELEGRAM ─────────────────────────────────────────────────────────────

    async def send_telegram(self, message: str, level: AlertLevel = AlertLevel.INFO):
        """Send a Telegram notification."""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return

        alert_key = f"telegram:{hash(message[:50])}"
        if not self._should_send(alert_key):
            return

        # Format with emoji based on level
        emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
        formatted = f"{emoji.get(level.value, 'ℹ️')} *{level.value.upper()}*\n\n{message}"

        try:
            client = await self._get_client()
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
            response = await client.post(url, json={
                "chat_id": self.config.telegram_chat_id,
                "text": formatted,
                "parse_mode": "Markdown",
                "disable_notification": level == AlertLevel.INFO,
            })
            response.raise_for_status()
            self._state.total_sent += 1
            logger.debug("alert.telegram_sent", level=level.value)
        except Exception as e:
            logger.error("alert.telegram_failed", error=str(e))

    # ─── EMAIL ────────────────────────────────────────────────────────────────

    async def send_email(self, subject: str, body: str, level: AlertLevel = AlertLevel.WARNING):
        """Send an email alert via SMTP."""
        if not self.config.smtp_host or not self.config.alert_email_to:
            return

        alert_key = f"email:{hash(subject)}"
        if not self._should_send(alert_key):
            return

        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{level.value.upper()}] {subject}"
            msg["From"] = self.config.smtp_from
            msg["To"] = self.config.alert_email_to

            html_body = f"""
            <html><body>
            <h2 style="color: {'red' if level == AlertLevel.CRITICAL else 'orange'}">
                {level.value.upper()}: {subject}
            </h2>
            <pre>{body}</pre>
            <hr>
            <small>Cross-Market Arbitrage Bot Alert System</small>
            </body></html>
            """
            msg.attach(MIMEText(html_body, "html"))

            await aiosmtplib.send(
                msg,
                hostname=self.config.smtp_host,
                port=self.config.smtp_port,
                username=self.config.smtp_user,
                password=self.config.smtp_password,
                use_tls=True,
            )
            self._state.total_sent += 1
            logger.debug("alert.email_sent", subject=subject)
        except ImportError:
            logger.warning("alert.aiosmtplib_not_installed")
        except Exception as e:
            logger.error("alert.email_failed", error=str(e))

    # ─── PRE-BUILT ALERT METHODS ──────────────────────────────────────────────

    async def alert_kill_switch_activated(self):
        """Alert when kill switch is triggered."""
        msg = (
            "🚨 KILL SWITCH ACTIVATED\n\n"
            "All open orders have been cancelled across:\n"
            "• Polymarket (Polygon)\n"
            "• Premu (Arbitrum)\n"
            "• Monaco Protocol (Solana)\n\n"
            "Manual intervention may be required."
        )
        await self.send_telegram(msg, AlertLevel.CRITICAL)
        await self.send_email("Kill Switch Activated", msg, AlertLevel.CRITICAL)

    async def alert_large_loss(self, amount: float, platform: str, market_id: str):
        """Alert on significant realized loss."""
        msg = (
            f"📉 Large Loss Detected\n\n"
            f"Platform: {platform}\n"
            f"Market: {market_id}\n"
            f"Loss: ${abs(amount):.2f}\n"
        )
        await self.send_telegram(msg, AlertLevel.WARNING)

    async def alert_execution_failure(self, platform: str, error: str, attempts: int):
        """Alert on repeated execution failures."""
        msg = (
            f"⚠️ Execution Failure\n\n"
            f"Platform: {platform}\n"
            f"Error: {error}\n"
            f"Attempts: {attempts}\n"
        )
        await self.send_telegram(msg, AlertLevel.WARNING)

    async def alert_low_gas_balance(self, chain: str, balance: float, minimum: float):
        """Alert when gas balance is critically low."""
        msg = (
            f"⛽ Low Gas Balance\n\n"
            f"Chain: {chain}\n"
            f"Balance: {balance:.6f}\n"
            f"Minimum: {minimum:.6f}\n\n"
            f"Trades may fail without sufficient gas."
        )
        await self.send_telegram(msg, AlertLevel.WARNING)
        await self.send_email(f"Low Gas on {chain}", msg, AlertLevel.WARNING)

    async def alert_arb_opportunity(self, signal_type: str, platform: str, edge_pct: float):
        """Alert on significant arbitrage opportunity detected."""
        msg = (
            f"💰 Arbitrage Opportunity\n\n"
            f"Type: {signal_type}\n"
            f"Platform: {platform}\n"
            f"Edge: {edge_pct:.2f}%\n"
        )
        await self.send_telegram(msg, AlertLevel.INFO)

    async def alert_connection_lost(self, service: str, reconnect_attempt: int):
        """Alert on connection loss to critical service."""
        msg = (
            f"🔌 Connection Lost\n\n"
            f"Service: {service}\n"
            f"Reconnect attempt: #{reconnect_attempt}\n"
        )
        if reconnect_attempt >= 5:
            await self.send_telegram(msg, AlertLevel.CRITICAL)
        else:
            await self.send_telegram(msg, AlertLevel.WARNING)

    async def close(self):
        """Cleanup HTTP client."""
        if self._http_client:
            await self._http_client.aclose()


# Singleton
alert_manager = AlertManager()
