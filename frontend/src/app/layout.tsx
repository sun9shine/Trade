"use client";

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import "@/i18n";
import "./globals.css";
import { useStore } from "@/store/useStore";
import Sidebar from "@/components/Sidebar";
import LanguageToggle from "@/components/LanguageToggle";
import NotificationStack from "@/components/NotificationStack";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const { i18n } = useTranslation();
  const { language } = useStore();

  useEffect(() => {
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
    document.documentElement.lang = language;
    i18n.changeLanguage(language);
  }, [language, i18n]);

  return (
    <html lang={language} dir={language === "ar" ? "rtl" : "ltr"}>
      <head>
        <title>Cross-Market Arbitrage Bot</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body className="flex h-screen overflow-hidden">
        {/* Sidebar */}
        <Sidebar />

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto">
          {/* Top Bar */}
          <header className="sticky top-0 z-10 flex items-center justify-between border-b border-dark-border bg-dark-bg/80 backdrop-blur-sm px-6 py-4">
            <div />
            <LanguageToggle />
          </header>

          {/* Page Content */}
          <div className="p-6">{children}</div>
        </main>

        {/* Notifications */}
        <NotificationStack />
      </body>
    </html>
  );
}
