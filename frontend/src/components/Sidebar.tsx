"use client";

import { useTranslation } from "react-i18next";
import { usePathname } from "next/navigation";
import Link from "next/link";
import clsx from "clsx";

const navigation = [
  { href: "/", key: "common.dashboard", icon: "📊" },
  { href: "/credentials", key: "common.credentials", icon: "🔑" },
  { href: "/rpc", key: "common.rpcSettings", icon: "🌐" },
  { href: "/webhooks", key: "common.webhooks", icon: "🔗" },
  { href: "/metrics", key: "common.metrics", icon: "📈" },
];

export default function Sidebar() {
  const { t } = useTranslation();
  const pathname = usePathname();

  return (
    <aside className="flex w-64 flex-col border-e border-dark-border bg-dark-card">
      {/* Logo / App Name */}
      <div className="flex h-16 items-center gap-3 border-b border-dark-border px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600 text-sm">
          ⚡
        </div>
        <span className="text-sm font-bold text-white truncate">
          {t("common.appName")}
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-4">
        {navigation.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={clsx(
              "sidebar-link",
              pathname === item.href && "active"
            )}
          >
            <span className="text-lg">{item.icon}</span>
            <span>{t(item.key)}</span>
          </Link>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-dark-border p-4">
        <div className="text-xs text-gray-500 text-center">
          v1.0.0 • Arbitrage Engine
        </div>
      </div>
    </aside>
  );
}
