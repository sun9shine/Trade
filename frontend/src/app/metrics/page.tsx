"use client";

import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { metricsApi, killSwitchApi, createWebSocket } from "@/lib/api";
import { useStore } from "@/store/useStore";
import clsx from "clsx";

export default function MetricsPage() {
  const { t } = useTranslation();
  const { metrics, setMetrics, addNotification, killSwitchActive, setKillSwitch } = useStore();
  const [confirmKill, setConfirmKill] = useState(false);

  // Fetch initial metrics
  useEffect(() => {
    metricsApi.get().then((res) => {
      const data = res.data;
      setMetrics({
        totalPnl: data.total_pnl_usd,
        openPositions: data.open_positions,
        tradesToday: data.total_trades_today,
        avgLatency: data.avg_latency_ms,
        gasBalances: {
          polygon: data.gas_balances.polygon_matic,
          arbitrum: data.gas_balances.arbitrum_eth,
          solana: data.gas_balances.solana_sol,
        },
        killSwitchActive: data.kill_switch_active,
      });
      setKillSwitch(data.kill_switch_active);
    }).catch(() => {});
  }, [setMetrics, setKillSwitch]);

  // WebSocket for real-time updates
  useEffect(() => {
    const ws = createWebSocket((data) => {
      if (data.type === "metrics_update") {
        setMetrics(data.data);
      } else if (data.type === "kill_switch") {
        setKillSwitch(data.active);
      }
    });
    return () => ws?.close();
  }, [setMetrics, setKillSwitch]);

  const handleKillSwitch = async () => {
    if (!confirmKill) {
      setConfirmKill(true);
      return;
    }

    try {
      if (killSwitchActive) {
        await killSwitchApi.deactivate();
        setKillSwitch(false);
        addNotification("info", t("notifications.killSwitchDeactivated"));
      } else {
        await killSwitchApi.activate();
        setKillSwitch(true);
        addNotification("warning", t("notifications.killSwitchActivated"));
      }
    } catch {
      addNotification("error", t("common.error"));
    } finally {
      setConfirmKill(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{t("metrics.title")}</h1>
        <p className="text-sm text-gray-400 mt-1">{t("metrics.subtitle")}</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="stat-card">
          <span className="text-xs text-gray-400 uppercase tracking-wider">
            {t("metrics.totalPnl")}
          </span>
          <span
            className={clsx(
              "mt-2 text-2xl font-bold",
              metrics.totalPnl >= 0 ? "text-success" : "text-danger"
            )}
          >
            ${metrics.totalPnl.toFixed(2)}
          </span>
        </div>
        <div className="stat-card">
          <span className="text-xs text-gray-400 uppercase tracking-wider">
            {t("metrics.openPositions")}
          </span>
          <span className="mt-2 text-2xl font-bold text-white">{metrics.openPositions}</span>
        </div>
        <div className="stat-card">
          <span className="text-xs text-gray-400 uppercase tracking-wider">
            {t("metrics.tradesToday")}
          </span>
          <span className="mt-2 text-2xl font-bold text-white">{metrics.tradesToday}</span>
        </div>
        <div className="stat-card">
          <span className="text-xs text-gray-400 uppercase tracking-wider">
            {t("metrics.avgLatency")}
          </span>
          <span className="mt-2 text-2xl font-bold text-white">
            {metrics.avgLatency > 0 ? `${metrics.avgLatency.toFixed(0)}ms` : "—"}
          </span>
        </div>
      </div>

      {/* Gas Balances */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">{t("metrics.gasBalances")}</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-center justify-between rounded-lg bg-dark-bg p-4">
            <div className="flex items-center gap-2">
              <span className="text-lg">🟣</span>
              <span className="text-sm text-gray-400">{t("metrics.polygon")}</span>
            </div>
            <span className="font-mono text-sm font-medium text-white">
              {metrics.gasBalances.polygon.toFixed(4)}
            </span>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-dark-bg p-4">
            <div className="flex items-center gap-2">
              <span className="text-lg">🔵</span>
              <span className="text-sm text-gray-400">{t("metrics.arbitrum")}</span>
            </div>
            <span className="font-mono text-sm font-medium text-white">
              {metrics.gasBalances.arbitrum.toFixed(6)}
            </span>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-dark-bg p-4">
            <div className="flex items-center gap-2">
              <span className="text-lg">🟢</span>
              <span className="text-sm text-gray-400">{t("metrics.solana")}</span>
            </div>
            <span className="font-mono text-sm font-medium text-white">
              {metrics.gasBalances.solana.toFixed(4)}
            </span>
          </div>
        </div>
      </div>

      {/* Positions Table */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">{t("metrics.openPositions")}</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left text-gray-300">
            <thead className="text-xs uppercase text-gray-500 border-b border-dark-border">
              <tr>
                <th className="px-4 py-3">{t("metrics.positionTable.platform")}</th>
                <th className="px-4 py-3">{t("metrics.positionTable.market")}</th>
                <th className="px-4 py-3">{t("metrics.positionTable.outcome")}</th>
                <th className="px-4 py-3">{t("metrics.positionTable.shares")}</th>
                <th className="px-4 py-3">{t("metrics.positionTable.entryPrice")}</th>
                <th className="px-4 py-3">{t("metrics.positionTable.currentPrice")}</th>
                <th className="px-4 py-3">{t("metrics.positionTable.pnl")}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                  {t("metrics.openPositions")}: 0
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Kill Switch */}
      <div
        className={clsx(
          "card border-2",
          killSwitchActive ? "border-danger" : "border-dark-border"
        )}
      >
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">{t("metrics.killSwitch")}</h2>
            <p className="text-sm text-gray-400 mt-1">{t("metrics.killSwitchDesc")}</p>
            {confirmKill && !killSwitchActive && (
              <p className="text-sm text-danger mt-2 font-medium">
                ⚠️ {t("metrics.killSwitchWarning")}
              </p>
            )}
          </div>
          <button
            onClick={handleKillSwitch}
            className={clsx(
              "px-6 py-3 rounded-lg font-bold text-sm transition-all",
              killSwitchActive
                ? "bg-gray-700 text-gray-200 hover:bg-gray-600"
                : confirmKill
                ? "bg-danger text-white animate-pulse"
                : "bg-danger/20 text-danger border border-danger hover:bg-danger hover:text-white"
            )}
          >
            {killSwitchActive
              ? t("metrics.killSwitchDeactivate")
              : confirmKill
              ? `⚠️ ${t("common.confirm")}`
              : t("metrics.killSwitchActivate")}
          </button>
        </div>

        {/* Kill Switch Status Indicator */}
        {killSwitchActive && (
          <div className="mt-4 flex items-center gap-2 rounded bg-danger/10 p-3">
            <span className="h-3 w-3 rounded-full bg-danger animate-pulse" />
            <span className="text-sm font-medium text-danger">
              {t("notifications.killSwitchActivated")}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
