"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { rpcApi } from "@/lib/api";
import { useStore } from "@/store/useStore";

interface ChainConfig {
  id: string;
  labelKey: string;
  icon: string;
  defaultUrl: string;
}

const CHAINS: ChainConfig[] = [
  {
    id: "polygon",
    labelKey: "rpc.polygon",
    icon: "🟣",
    defaultUrl: "https://polygon-rpc.com",
  },
  {
    id: "arbitrum",
    labelKey: "rpc.arbitrum",
    icon: "🔵",
    defaultUrl: "https://arb1.arbitrum.io/rpc",
  },
  {
    id: "solana",
    labelKey: "rpc.solana",
    icon: "🟢",
    defaultUrl: "https://api.mainnet-beta.solana.com",
  },
];

export default function RPCSettingsPage() {
  const { t } = useTranslation();
  const { addNotification } = useStore();
  const [endpoints, setEndpoints] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState<string | null>(null);
  const [latencies, setLatencies] = useState<Record<string, number | null>>({});

  const handleSave = async (chain: ChainConfig) => {
    const url = endpoints[chain.id];
    if (!url) return;

    try {
      await rpcApi.save(chain.id, url);
      addNotification("success", t("notifications.rpcSaved"));
    } catch {
      addNotification("error", t("notifications.rpcTestFailed"));
    }
  };

  const handleTest = async (chain: ChainConfig) => {
    const url = endpoints[chain.id] || chain.defaultUrl;
    setTesting(chain.id);

    try {
      const start = performance.now();
      // Simple connectivity test
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          method: chain.id === "solana" ? "getHealth" : "eth_blockNumber",
          params: [],
        }),
      });

      const latency = Math.round(performance.now() - start);
      setLatencies((prev) => ({ ...prev, [chain.id]: latency }));

      if (response.ok) {
        addNotification("success", t("notifications.rpcTestSuccess", { ms: latency }));
      } else {
        addNotification("error", t("notifications.rpcTestFailed"));
        setLatencies((prev) => ({ ...prev, [chain.id]: null }));
      }
    } catch {
      addNotification("error", t("notifications.rpcTestFailed"));
      setLatencies((prev) => ({ ...prev, [chain.id]: null }));
    } finally {
      setTesting(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{t("rpc.title")}</h1>
        <p className="text-sm text-gray-400 mt-1">{t("rpc.subtitle")}</p>
      </div>

      {/* Chain Configuration Cards */}
      {CHAINS.map((chain) => (
        <div key={chain.id} className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <span className="text-xl">{chain.icon}</span>
              <h2 className="text-lg font-semibold text-white">{t(chain.labelKey)}</h2>
            </div>
            {latencies[chain.id] !== undefined && latencies[chain.id] !== null && (
              <span className="rounded-full bg-success/20 px-3 py-1 text-xs font-medium text-success">
                {t("rpc.latencyMs", { ms: latencies[chain.id] })}
              </span>
            )}
          </div>

          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                {t("rpc.endpoint")}
              </label>
              <input
                type="text"
                placeholder={chain.defaultUrl}
                value={endpoints[chain.id] || ""}
                onChange={(e) =>
                  setEndpoints((prev) => ({ ...prev, [chain.id]: e.target.value }))
                }
                className="input-field font-mono text-xs"
              />
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => handleTest(chain)}
                disabled={testing === chain.id}
                className="btn-secondary disabled:opacity-50"
              >
                {testing === chain.id ? "..." : t("rpc.testConnection")}
              </button>
              <button
                onClick={() => handleSave(chain)}
                disabled={!endpoints[chain.id]}
                className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t("common.save")}
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
