"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "./cn";

interface Toast {
  id: number;
  message: string;
  tone: "success" | "error" | "info";
}

const ToastContext = createContext<{ push: (message: string, tone?: Toast["tone"]) => void } | null>(
  null,
);

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  // The portal must not render during SSR or the first client render (both
  // have no `document.body` node to portal into yet, and must produce
  // identical output for hydration to succeed) — only after mount, once
  // this effect flips `mounted` to true, does the portal actually attach.
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const push = useCallback((message: string, tone: Toast["tone"] = "info") => {
    const id = nextId++;
    setToasts((current) => [...current, { id, message, tone }]);
    setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      {mounted
        ? createPortal(
            <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
              {toasts.map((toast) => (
                <div
                  key={toast.id}
                  role="status"
                  className={cn(
                    "animate-slide-up rounded-lg px-4 py-3 text-sm font-medium shadow-popover",
                    toast.tone === "success" && "bg-emerald-600 text-white",
                    toast.tone === "error" && "bg-red-600 text-white",
                    toast.tone === "info" && "bg-slate-900 text-white",
                  )}
                >
                  {toast.message}
                </div>
              ))}
            </div>,
            document.body,
          )
        : null}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
