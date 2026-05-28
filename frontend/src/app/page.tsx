"use client";

import { useTranslation } from "react-i18next";

export default function DashboardPage() {
  const { t } = useTranslation();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{t("common.dashboard")}</h1>
        <p className="text-sm text-gray-400 mt-1">
          {t("metrics.subtitle")}
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="stat-card">
          <span className="text-xs text-gray-400 uppercase tracking-wider">
            {t("metrics.totalPnl")}
          </span>
          <span className="mt-2 text-2xl font-bold text-success">$0.00</span>
        </div>
        <div className="stat-card">
          <span className="text-xs text-gray-400 uppercase tracking-wider">
            {t("metrics.openPositions")}
          </span>
          <span className="mt-2 text-2xl font-bold text-white">0</span>
        </div>
        <div className="stat-card">
          <span className="text-xs text-gray-400 uppercase tracking-wider">
            {t("metrics.tradesToday")}
          </span>
          <span className="mt-2 text-2xl font-bold text-white">0</span>
        </div>
        <div className="stat-card">
          <span className="text-xs text-gray-400 uppercase tracking-wider">
            {t("metrics.avgLatency")}
          </span>
          <span className="mt-2 text-2xl font-bold text-white">—</span>
        </div>
      </div>

      {/* Gas Balances */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">{t("metrics.gasBalances")}</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-center justify-between rounded-lg bg-dark-bg p-4">
            <span className="text-sm text-gray-400">{t("metrics.polygon")}</span>
            <span className="font-mono text-sm text-white">0.00 MATIC</span>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-dark-bg p-4">
            <span className="text-sm text-gray-400">{t("metrics.arbitrum")}</span>
            <span className="font-mono text-sm text-white">0.00 ETH</span>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-dark-bg p-4">
            <span className="text-sm text-gray-400">{t("metrics.solana")}</span>
            <span className="font-mono text-sm text-white">0.00 SOL</span>
          </div>
        </div>
      </div>

      {/* Platform Status */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">{t("common.status")}</h2>
        <div className="space-y-3">
          {["Polymarket V2 (Polygon)", "Premu.xyz (Arbitrum)", "Monaco Protocol (Solana)"].map(
            (platform) => (
              <div
                key={platform}
                className="flex items-center justify-between rounded-lg bg-dark-bg p-4"
              >
                <span className="text-sm text-gray-300">{platform}</span>
                <span className="flex items-center gap-2 text-xs text-yellow-400">
                  <span className="h-2 w-2 rounded-full bg-yellow-400" />
                  {t("common.inactive")}
                </span>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
