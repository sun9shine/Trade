"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { credentialsApi } from "@/lib/api";
import { useStore } from "@/store/useStore";

interface CredentialField {
  service: string;
  keyName: string;
  labelKey: string;
  type: "text" | "password";
  placeholder: string;
}

const CREDENTIAL_FIELDS: CredentialField[] = [
  // MetaTrader 5
  { service: "mt5", keyName: "login", labelKey: "credentials.mt5Login", type: "text", placeholder: "12345678" },
  { service: "mt5", keyName: "password", labelKey: "credentials.mt5Password", type: "password", placeholder: "••••••••" },
  { service: "mt5", keyName: "server", labelKey: "credentials.mt5Server", type: "text", placeholder: "ICMarkets-Demo" },
  // OANDA
  { service: "oanda", keyName: "api_key", labelKey: "credentials.oandaApiKey", type: "password", placeholder: "your-oanda-api-key" },
  { service: "oanda", keyName: "account_id", labelKey: "credentials.oandaAccountId", type: "text", placeholder: "101-001-12345678-001" },
  // Polymarket
  { service: "polymarket", keyName: "api_key", labelKey: "credentials.polyApiKey", type: "password", placeholder: "your-polymarket-api-key" },
  { service: "polymarket", keyName: "api_secret", labelKey: "credentials.polyApiSecret", type: "password", placeholder: "your-api-secret" },
  { service: "polymarket", keyName: "passphrase", labelKey: "credentials.polyPassphrase", type: "password", placeholder: "your-passphrase" },
  // Wallets
  { service: "polygon", keyName: "private_key", labelKey: "credentials.polygonPrivateKey", type: "password", placeholder: "0x..." },
  { service: "arbitrum", keyName: "private_key", labelKey: "credentials.arbitrumPrivateKey", type: "password", placeholder: "0x..." },
  { service: "solana", keyName: "private_key", labelKey: "credentials.solanaPrivateKey", type: "password", placeholder: "base58-encoded-key" },
  // Premu
  { service: "premu", keyName: "vault_address", labelKey: "credentials.premuVaultAddress", type: "text", placeholder: "0x..." },
];

export default function CredentialsPage() {
  const { t } = useTranslation();
  const { addNotification } = useStore();
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [showValues, setShowValues] = useState<Record<string, boolean>>({});

  const fieldKey = (field: CredentialField) => `${field.service}_${field.keyName}`;

  const handleSave = async (field: CredentialField) => {
    const key = fieldKey(field);
    const value = values[key];
    if (!value) return;

    setSaving(key);
    try {
      await credentialsApi.save(field.service, field.keyName, value);
      addNotification("success", t("notifications.credentialSaved"));
      // Clear the input after saving
      setValues((prev) => ({ ...prev, [key]: "" }));
    } catch {
      addNotification("error", t("notifications.credentialFailed"));
    } finally {
      setSaving(null);
    }
  };

  const toggleShow = (key: string) => {
    setShowValues((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Group by service
  const serviceGroups = [
    { title: "MetaTrader 5", icon: "📊", services: ["mt5"] },
    { title: "OANDA", icon: "💹", services: ["oanda"] },
    { title: "Polymarket (Polygon)", icon: "🟣", services: ["polymarket"] },
    { title: "Premu (Arbitrum)", icon: "🔵", services: ["premu", "arbitrum"] },
    { title: "Monaco (Solana)", icon: "🟢", services: ["solana"] },
    { title: "Polygon Wallet", icon: "💜", services: ["polygon"] },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{t("credentials.title")}</h1>
        <p className="text-sm text-gray-400 mt-1">{t("credentials.subtitle")}</p>
      </div>

      {/* Security Notice */}
      <div className="rounded-lg border border-primary-800 bg-primary-900/20 p-4">
        <div className="flex items-start gap-3">
          <span className="text-lg">🔒</span>
          <p className="text-sm text-primary-200">{t("credentials.securityNotice")}</p>
        </div>
      </div>

      {/* Credential Groups */}
      {serviceGroups.map((group) => {
        const fields = CREDENTIAL_FIELDS.filter((f) => group.services.includes(f.service));
        if (fields.length === 0) return null;

        return (
          <div key={group.title} className="card">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-xl">{group.icon}</span>
              <h2 className="text-lg font-semibold text-white">{group.title}</h2>
            </div>

            <div className="space-y-4">
              {fields.map((field) => {
                const key = fieldKey(field);
                const isPassword = field.type === "password";
                const isShowing = showValues[key];

                return (
                  <div key={key} className="space-y-1.5">
                    <label className="block text-sm font-medium text-gray-300">
                      {t(field.labelKey)}
                    </label>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <input
                          type={isPassword && !isShowing ? "password" : "text"}
                          placeholder={field.placeholder}
                          value={values[key] || ""}
                          onChange={(e) =>
                            setValues((prev) => ({ ...prev, [key]: e.target.value }))
                          }
                          className="input-field pe-10"
                          autoComplete="off"
                        />
                        {isPassword && (
                          <button
                            type="button"
                            onClick={() => toggleShow(key)}
                            className="absolute end-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-sm"
                          >
                            {isShowing ? "🙈" : "👁️"}
                          </button>
                        )}
                      </div>
                      <button
                        onClick={() => handleSave(field)}
                        disabled={!values[key] || saving === key}
                        className="btn-primary whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {saving === key ? "..." : t("common.save")}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
