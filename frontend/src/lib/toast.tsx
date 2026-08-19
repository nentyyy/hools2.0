import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { haptics } from "./telegram";

type ToastKind = "info" | "error" | "success";

interface Toast {
  id: number;
  text: string;
  kind: ToastKind;
}

interface ToastValue {
  show: (text: string, kind?: ToastKind) => void;
  error: (text: string) => void;
  success: (text: string) => void;
}

const ToastContext = createContext<ToastValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((text: string, kind: ToastKind = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current.slice(-2), { id, text, kind }]);
    if (kind === "error") haptics.notify("error");
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 3600);
  }, []);

  const value = useMemo<ToastValue>(
    () => ({
      show,
      error: (text: string) => show(text, "error"),
      success: (text: string) => show(text, "success"),
    }),
    [show],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts">
        {toasts.map((toast) => (
          <div key={toast.id} className="toast" data-kind={toast.kind}>
            {toast.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
