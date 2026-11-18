import { clsx } from "clsx";
import { LoaderCircle } from "lucide-react";
import type {
  ComponentProps,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { useId } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

// The primary action is signal yellow with dark ink (glowing in dark mode); everything else is glass or plain.
const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-brand text-on-brand glow-yellow hover:brightness-95",
  secondary: "glass-ctl text-ink hover:brightness-95",
  ghost: "text-muted hover:text-ink hover:bg-subtle",
  danger: "glass-ctl text-bad hover:bg-bad-soft",
};

// Touch targets are at least 44px (md); `sm` is for dense toolbars under a mouse.
const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-9 px-4 text-secondary",
  md: "h-11 px-5 text-secondary",
  lg: "h-12 px-6 text-subheading",
};

export function buttonClass(variant: ButtonVariant = "secondary", size: ButtonSize = "md"): string {
  return clsx(
    "inline-flex items-center justify-center gap-2 rounded-full font-display font-semibold tracking-wide uppercase whitespace-nowrap",
    "transition-colors duration-(--duration-quick) ease-(--ease-calm)",
    "disabled:pointer-events-none disabled:opacity-50",
    BUTTON_SIZES[size],
    BUTTON_VARIANTS[variant],
  );
}

interface ButtonProps extends ComponentProps<"button"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  busy?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant,
  size,
  busy = false,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={clsx(buttonClass(variant, size), className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <LoaderCircle aria-hidden className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

type CardVariant = "surface" | "subtle" | "plain";

const CARDS: Record<CardVariant, string> = {
  surface: "glass",
  subtle: "glass-plate",
  plain: "",
};

/** A glass panel (`surface`) or the denser plate small text sits on (`subtle`). */
export function Card({
  variant = "surface",
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { variant?: CardVariant }) {
  return <div className={clsx("rounded-card", CARDS[variant], className)} {...rest} />;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-10 text-secondary text-muted">
      <LoaderCircle aria-hidden className="size-5 animate-spin" />
      {label}…
    </div>
  );
}

type Tone = "neutral" | "accent" | "good" | "warn" | "bad";

const TONES: Record<Tone, string> = {
  neutral: "bg-subtle text-muted",
  accent: "bg-accent-soft text-accent",
  good: "bg-good-soft text-good",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
};

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-muted",
  accent: "text-accent",
  good: "text-good",
  warn: "text-warn",
  bad: "text-bad",
};

/** Quiet secondary text for a row of facts ("Toronto · 2 days ago"). */
export function Meta({
  tone = "neutral",
  className,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return <span className={clsx("text-caption whitespace-nowrap", TONE_TEXT[tone], className)} {...rest} />;
}

/** A state word with a small dot in the same colour. Colour never carries the meaning alone: the word does. */
export function Dot({
  tone = "neutral",
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 text-caption font-medium whitespace-nowrap",
        TONE_TEXT[tone],
        className,
      )}
      {...rest}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {children}
    </span>
  );
}

export function Alert({
  tone = "bad",
  title,
  children,
}: {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div
      role={tone === "bad" ? "alert" : "status"}
      className={clsx("rounded-control px-4 py-3 text-secondary", TONES[tone])}
    >
      {title && <p className="font-medium">{title}</p>}
      {children && <div className={clsx(title && "mt-1")}>{children}</div>}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="glass flex flex-col items-center gap-3 rounded-card px-6 py-12 text-center">
      {icon && <div className="text-faint">{icon}</div>}
      <h2 className="text-subheading font-semibold">{title}</h2>
      {children && <div className="max-w-md text-secondary text-muted">{children}</div>}
    </div>
  );
}

const CONTROL =
  "w-full rounded-control glass-plate border border-line px-4 text-subheading text-ink placeholder:text-faint sm:text-secondary " +
  "transition-shadow duration-(--duration-quick) ease-(--ease-calm) " +
  "focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-60";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string | undefined;
  className?: string;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}

export function Field({ label, hint, error, className, children }: FieldProps) {
  const id = useId();
  const hintId = hint || error ? `${id}-hint` : undefined;
  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-secondary font-medium">
        {label}
      </label>
      {children(id, hintId)}
      {(error ?? hint) && (
        <p id={hintId} className={clsx("text-caption", error ? "text-bad" : "text-muted")}>
          {error ?? hint}
        </p>
      )}
    </div>
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={clsx(CONTROL, "h-12", className)} {...rest} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={clsx(CONTROL, "py-3 leading-relaxed", className)} {...rest} />;
}

export function Select({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={clsx(CONTROL, "h-12 pr-8", className)} {...rest} />;
}

/** A select sized to its content (for toolbars), instead of filling the row. */
export function InlineSelect({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={clsx("min-w-0", className)}>
      <Select {...rest} />
    </div>
  );
}

export function ErrorNote({ message, reference }: { message: string; reference: string | null }) {
  return (
    <Alert tone="bad">
      {message}
      {reference && <span className="mt-1 block text-caption">Reference: {reference}</span>}
    </Alert>
  );
}

interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
  /** Only for `kind="tabs"`: the id of this tab and of the panel it controls. */
  tabId?: string;
  panelId?: string;
}

/**
 * A row of mutually exclusive choices. `radio` (default) is a radio group; `tabs` is a tab list whose panels the
 * caller renders. Arrow keys move the choice and the focus in both.
 */
export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
  kind = "radio",
  className,
}: {
  label: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  kind?: "radio" | "tabs";
  className?: string;
}) {
  const itemRole = kind === "tabs" ? "tab" : "radio";
  function move(group: HTMLElement, from: number, step: number) {
    const next = options[(from + step + options.length) % options.length];
    if (!next) return;
    onChange(next.value);
    group.querySelectorAll<HTMLElement>(`[role="${itemRole}"]`)[options.indexOf(next)]?.focus();
  }
  return (
    <div
      role={kind === "tabs" ? "tablist" : "radiogroup"}
      aria-label={label}
      className={clsx("glass-ctl inline-flex max-w-full gap-1 overflow-x-auto rounded-full p-1", className)}
    >
      {options.map((option, index) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role={itemRole}
            {...(kind === "tabs"
              ? { id: option.tabId, "aria-selected": selected, "aria-controls": option.panelId }
              : { "aria-checked": selected })}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => {
              const group = event.currentTarget.parentElement as HTMLElement;
              if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                event.preventDefault();
                move(group, index, 1);
              } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                event.preventDefault();
                move(group, index, -1);
              }
            }}
            className={clsx(
              "h-9 shrink-0 rounded-full px-4 font-display text-secondary font-semibold tracking-wide uppercase",
              "transition-colors duration-(--duration-quick) ease-(--ease-calm)",
              selected ? "bg-brand text-on-brand glow-yellow" : "text-muted hover:text-ink",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
