import { create } from "zustand";

interface Notification {
  id: string;
  type: "success" | "error" | "warning" | "info";
  message: string;
  timestamp: number;
}

interface Metrics {
  totalPnl: number;
  openPositions: number;
  tradesToday: number;
  avgLatency: number;
  gasBalances: {
    polygon: number;
    arbitrum: number;
    solana: number;
  };
  killSwitchActive: boolean;
}

interface AppStore {
  // Language
  language: "en" | "ar";
  setLanguage: (lang: "en" | "ar") => void;

  // Notifications
  notifications: Notification[];
  addNotification: (type: Notification["type"], message: string) => void;
  removeNotification: (id: string) => void;

  // Metrics
  metrics: Metrics;
  setMetrics: (metrics: Partial<Metrics>) => void;

  // Kill Switch
  killSwitchActive: boolean;
  setKillSwitch: (active: boolean) => void;
}

export const useStore = create<AppStore>((set) => ({
  // Language
  language: "en",
  setLanguage: (lang) => set({ language: lang }),

  // Notifications
  notifications: [],
  addNotification: (type, message) =>
    set((state) => ({
      notifications: [
        ...state.notifications,
        { id: crypto.randomUUID(), type, message, timestamp: Date.now() },
      ].slice(-10), // Keep last 10
    })),
  removeNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    })),

  // Metrics
  metrics: {
    totalPnl: 0,
    openPositions: 0,
    tradesToday: 0,
    avgLatency: 0,
    gasBalances: { polygon: 0, arbitrum: 0, solana: 0 },
    killSwitchActive: false,
  },
  setMetrics: (metrics) =>
    set((state) => ({ metrics: { ...state.metrics, ...metrics } })),

  // Kill Switch
  killSwitchActive: false,
  setKillSwitch: (active) => set({ killSwitchActive: active }),
}));
