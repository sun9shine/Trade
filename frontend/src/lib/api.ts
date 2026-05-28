import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach JWT token to all requests
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("auth_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// WebSocket connection manager
export function createWebSocket(onMessage: (data: any) => void): WebSocket | null {
  if (typeof window === "undefined") return null;

  const ws = new WebSocket(WS_BASE);

  ws.onopen = () => {
    console.log("[WS] Connected to metrics stream");
    // Keep-alive ping every 30s
    setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send("ping");
      }
    }, 30000);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data !== "pong") {
        onMessage(data);
      }
    } catch {
      // Ignore non-JSON messages (pong)
    }
  };

  ws.onerror = (error) => {
    console.error("[WS] Error:", error);
  };

  ws.onclose = () => {
    console.log("[WS] Disconnected — reconnecting in 5s");
    setTimeout(() => createWebSocket(onMessage), 5000);
  };

  return ws;
}

// API functions
export const credentialsApi = {
  save: (serviceName: string, keyName: string, value: string) =>
    api.post("/api/credentials", { service_name: serviceName, key_name: keyName, value }),

  list: (serviceName: string) => api.get(`/api/credentials/${serviceName}`),
};

export const rpcApi = {
  save: (chain: string, url: string, priority: number = 0) =>
    api.post("/api/rpc-endpoints", { chain, url, priority }),

  list: () => api.get("/api/rpc-endpoints"),
};

export const webhookApi = {
  generate: () => api.post("/api/webhooks/generate"),
};

export const metricsApi = {
  get: () => api.get("/api/metrics"),
};

export const killSwitchApi = {
  activate: () => api.post("/api/kill-switch/activate"),
  deactivate: () => api.post("/api/kill-switch/deactivate"),
};
