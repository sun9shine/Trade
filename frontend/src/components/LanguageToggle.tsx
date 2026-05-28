"use client";

import { useTranslation } from "react-i18next";
import { useStore } from "@/store/useStore";

export default function LanguageToggle() {
  const { t } = useTranslation();
  const { language, setLanguage } = useStore();

  const toggle = () => {
    const newLang = language === "en" ? "ar" : "en";
    setLanguage(newLang);
  };

  return (
    <button
      onClick={toggle}
      className="flex items-center gap-2 rounded-lg border border-dark-border px-3 py-2 text-sm font-medium text-gray-300 hover:bg-dark-card hover:text-white transition-colors"
      aria-label="Toggle language"
    >
      <span className="text-base">🌐</span>
      <span>{language === "en" ? t("common.arabic") : t("common.english")}</span>
      <span className="rounded bg-primary-600/20 px-1.5 py-0.5 text-xs font-bold text-primary-400 uppercase">
        {language === "en" ? "AR" : "EN"}
      </span>
    </button>
  );
}
