"use client";

import { useEffect } from "react";
import { useStore } from "@/store/useStore";
import clsx from "clsx";

export default function NotificationStack() {
  const { notifications, removeNotification } = useStore();

  // Auto-dismiss after 5 seconds
  useEffect(() => {
    const timers = notifications.map((n) =>
      setTimeout(() => removeNotification(n.id), 5000)
    );
    return () => timers.forEach(clearTimeout);
  }, [notifications, removeNotification]);

  if (notifications.length === 0) return null;

  return (
    <div className="fixed bottom-4 end-4 z-50 flex flex-col gap-2 max-w-sm">
      {notifications.map((notification) => (
        <div
          key={notification.id}
          className={clsx(
            "rounded-lg border px-4 py-3 shadow-lg backdrop-blur-sm transition-all animate-in slide-in-from-bottom",
            {
              "border-green-800 bg-green-900/80 text-green-200":
                notification.type === "success",
              "border-red-800 bg-red-900/80 text-red-200":
                notification.type === "error",
              "border-yellow-800 bg-yellow-900/80 text-yellow-200":
                notification.type === "warning",
              "border-blue-800 bg-blue-900/80 text-blue-200":
                notification.type === "info",
            }
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm">{notification.message}</p>
            <button
              onClick={() => removeNotification(notification.id)}
              className="text-xs opacity-60 hover:opacity-100"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
