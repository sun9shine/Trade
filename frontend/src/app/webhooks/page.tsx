"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { webhookApi } from "@/lib/api";
import { useStore } from "@/store/useStore";

interface Webhook {
  slug: string;
  url: string;
  hmacSecret: string;
  source: string;
  active: boolean;
  lastReceived: string | null;
}

export default function WebhooksPage() {
  const { t } = useTranslation();
  const { addNotification } = useStore();
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const response = await webhookApi.generate();
      const data = response.data;
      setWebhooks((prev) => [
        ...prev,
        {
          slug: data.slug,
          url: `${process.env.NEXT_PUBLIC_API_URL}${data.webhook_url}`,
          hmacSecret: data.hmac_secret,
          source: "custom",
          active: true,
          lastReceived: null,
        },
      ]);
      addNotification("success", t("notifications.webhookGenerated"));
    } catch {
      addNotification("error", t("common.error"));
    } finally {
      setGenerating(false);
    }
  };

  const examplePayload = JSON.stringify(
    {
      event_type: "interest_rate",
      country: "US",
      headline: "Fed raises rates by 25bps",
      actual_value: "5.50%",
      forecast_value: "5.25%",
      previous_value: "5.25%",
      impact_level: "high",
      source: "reuters",
    },
    null,
    2
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{t("webhooks.title")}</h1>
          <p className="text-sm text-gray-400 mt-1">{t("webhooks.subtitle")}</p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="btn-primary disabled:opacity-50"
        >
          {generating ? "..." : t("webhooks.generateNew")}
        </button>
      </div>

      {/* Active Webhooks */}
      {webhooks.length > 0 && (
        <div className="space-y-4">
          {webhooks.map((webhook) => (
            <div key={webhook.slug} className="card">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-1">
                    {t("webhooks.url")}
                  </label>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 rounded bg-dark-bg px-3 py-2 text-xs font-mono text-primary-300 overflow-x-auto">
                      {webhook.url}
                    </code>
                    <button
                      onClick={() => navigator.clipboard.writeText(webhook.url)}
                      className="btn-secondary text-xs"
                    >
                      📋
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-1">
                    {t("webhooks.hmacSecret")}
                  </label>
                  <code className="block rounded bg-dark-bg px-3 py-2 text-xs font-mono text-yellow-300 overflow-x-auto">
                    {webhook.hmacSecret}
                  </code>
                </div>

                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span>
                    {t("webhooks.source")}: {t(`webhooks.sources.${webhook.source}`)}
                  </span>
                  <span>
                    {t("webhooks.lastReceived")}: {webhook.lastReceived || "—"}
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-success" />
                    {t("common.active")}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {webhooks.length === 0 && (
        <div className="card text-center py-12">
          <span className="text-4xl">🔗</span>
          <p className="mt-4 text-gray-400">{t("webhooks.subtitle")}</p>
          <button onClick={handleGenerate} className="btn-primary mt-4">
            {t("webhooks.generateNew")}
          </button>
        </div>
      )}

      {/* Example Payload */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">
          {t("webhooks.payloadExample")}
        </h3>
        <pre className="rounded-lg bg-dark-bg p-4 text-xs font-mono text-gray-300 overflow-x-auto">
          {examplePayload}
        </pre>
      </div>
    </div>
  );
}
