import { clsx } from "clsx";
import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

export type ToastTone = "success" | "error" | "info";

export interface ToastInput {
  tone?: ToastTone;
  title: string;
  description?: string;
  reference?: string | null;
  action?: { label: string; onClick: () => void };
}

interface Toast extends ToastInput {
  id: number;
}

const ToastContext = createContext<((toast: ToastInput) => void) | null>(null);

// The bar is inverted (ink on canvas) so it reads on any page; the tone shows in the icon's shape, not its colour.
const ICONS: Record<ToastTone, ReactNode> = {
  success: <CircleCheck className="size-5 shrink-0" aria-hidden />,
  error: <CircleAlert className="size-5 shrink-0" aria-hidden />,
  info: <Info className="size-5 shrink-0" aria-hidden />,
};

/** Small dependency-free toast stack (no runtime-injected styles, so the strict CSP holds). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (input: ToastInput) => {
      const id = nextId.current++;
      setToasts((current) => [...current.slice(-3), { ...input, id }]);
      window.setTimeout(() => dismiss(id), input.tone === "error" ? 10000 : 6000);
    },
    [dismiss],
  );

  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:items-end"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.tone === "error" ? "alert" : "status"}
            className={clsx(
              "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-control bg-ink p-4 text-canvas shadow-pop",
            )}
          >
            {ICONS[toast.tone ?? "info"]}
            <div className="min-w-0 flex-1 text-secondary">
              <p className="font-medium">{toast.title}</p>
              {toast.description && <p className="mt-0.5">{toast.description}</p>}
              {toast.reference && <p className="mt-1 text-caption">Reference: {toast.reference}</p>}
              {toast.action && (
                <button
                  type="button"
                  className="mt-2 font-medium underline underline-offset-2"
                  onClick={() => {
                    toast.action?.onClick();
                    dismiss(toast.id);
                  }}
                >
                  {toast.action.label}
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={() => dismiss(toast.id)}
              className="-m-2 inline-flex size-11 shrink-0 items-center justify-center rounded-full hover:bg-canvas/15"
              aria-label="Dismiss notification"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): (toast: ToastInput) => void {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <ToastProvider>");
  return context;
}
