import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useId, useRef } from "react";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}

/** Modal built on the native <dialog> element: focus trap, Esc and backdrop handling come from the browser. */
export function Dialog({ open, onClose, title, description, children, footer }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      className="mt-auto mb-0 ml-0 w-full max-w-none rounded-t-sheet rounded-b-none glass p-0 text-ink shadow-pop md:m-auto md:w-[min(40rem,calc(100vw-2rem))] md:rounded-card"
    >
      {open && (
        <div className="glass-plate flex max-h-[85dvh] flex-col rounded-[inherit]">
          <header className="flex items-start justify-between gap-4 px-5 pt-5 pb-2 md:px-6">
            <div>
              <h2 id={titleId} className="text-heading font-semibold">
                {title}
              </h2>
              {description && <p className="mt-0.5 text-secondary text-muted">{description}</p>}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="-mt-1 -mr-2 inline-flex size-11 shrink-0 items-center justify-center rounded-full text-muted hover:bg-subtle hover:text-ink"
              aria-label="Close"
            >
              <X className="size-5" aria-hidden />
            </button>
          </header>
          <div className="overflow-y-auto px-5 py-3 md:px-6">{children}</div>
          {footer && <footer className="flex justify-end gap-2 px-5 pt-2 pb-5 md:px-6">{footer}</footer>}
        </div>
      )}
    </dialog>
  );
}
