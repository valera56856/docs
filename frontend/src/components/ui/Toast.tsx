/**
 * Toast — transient, non-blocking notifications (context-based).
 *
 * This module owns the toast *state machine* and public API:
 * - {@link ToastProvider} holds the live toast list and auto-dismiss timers.
 * - {@link useToast} is the hook pages call to push toasts:
 *   `toast({ variant: 'error', title: '…' })`, plus `dismiss(id)`.
 * - {@link ToastItem} renders a single toast (icon + title/description + close),
 *   color-coded by variant but never color-only (each variant has an icon and
 *   the close button is labelled) — matching the `StatusBadge` a11y rule.
 *
 * The visual stack is rendered by {@link ../Toaster} (a thin component that
 * reads this context and portals the toasts to a fixed, safe-area-aware region).
 * Splitting state (here) from layout (Toaster) keeps the provider importable
 * without pulling layout into non-UI modules.
 *
 * WHY context: any page can fire a toast without prop-drilling; the single
 * provider (mounted once in App) owns timers so toasts survive route changes.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
  type ReactNode,
} from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  XCircle,
  type LucideIcon,
} from 'lucide-react';

import { cn } from '@/lib/cn';

/** Semantic flavor of a toast. Drives icon + color (and screen-reader urgency). */
export type ToastVariant = 'success' | 'error' | 'warning' | 'info';

/** A fully-resolved toast in the live list. */
export interface Toast {
  /** Stable unique id (used as React key and dismissal handle). */
  id: string;
  /** Visual/semantic variant. Defaults to `info` when omitted at push time. */
  variant: ToastVariant;
  /** Primary message. */
  title: string;
  /** Optional secondary detail line. */
  description?: ReactNode;
  /** Auto-dismiss delay in ms. `0`/negative keeps the toast until dismissed. */
  duration: number;
}

/** Options accepted by {@link ToastContextValue.toast}. `id`/`variant`/
 * `duration` are optional and defaulted. */
export interface ToastOptions {
  /** Primary message. */
  title: string;
  /** Optional secondary detail line. */
  description?: ReactNode;
  /** Variant; defaults to `info`. */
  variant?: ToastVariant;
  /** Auto-dismiss delay in ms; defaults to {@link DEFAULT_DURATION}. */
  duration?: number;
  /** Provide a stable id to de-dupe / replace an existing toast. */
  id?: string;
}

/** Public toast API exposed via {@link useToast}. */
export interface ToastContextValue {
  /** The current live toasts (consumed by {@link ../Toaster}). */
  toasts: Toast[];
  /**
   * Push a toast. Returns its id so the caller can dismiss it early.
   *
   * @param options - {@link ToastOptions}.
   * @returns The toast id.
   */
  toast: (options: ToastOptions) => string;
  /** Dismiss a single toast by id. */
  dismiss: (id: string) => void;
  /** Dismiss every visible toast. */
  dismissAll: () => void;
}

/** Default auto-dismiss window — long enough to read a short Ukrainian line. */
const DEFAULT_DURATION = 4000;

const ToastContext = createContext<ToastContextValue | null>(null);

/** Per-variant icon. Meaning never relies on color alone (WCAG 1.4.1). */
const VARIANT_ICON: Record<ToastVariant, LucideIcon> = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

/** Per-variant token colors (fg = icon/accent, bg = subtle tinted surface). */
const VARIANT_COLORS: Record<ToastVariant, { fg: string; bg: string }> = {
  success: { fg: 'var(--color-success)', bg: 'var(--color-success-bg)' },
  error: { fg: 'var(--color-danger)', bg: 'var(--color-danger-bg)' },
  warning: { fg: 'var(--color-warning)', bg: 'var(--color-warning-bg)' },
  info: { fg: 'var(--color-info)', bg: 'var(--color-info-bg)' },
};

/** Generate a reasonably unique id without pulling in a uuid dependency. */
function makeId(): string {
  return `toast-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Props for {@link ToastProvider}. */
export interface ToastProviderProps {
  /** App subtree that can fire toasts. */
  children: ReactNode;
  /** Override the default auto-dismiss duration (ms) for all toasts. */
  defaultDuration?: number;
}

/**
 * Provide the toast context and own auto-dismiss timers.
 *
 * Mount once near the app root (above the router). Render {@link ../Toaster}
 * inside it to display the toasts.
 *
 * @param props - {@link ToastProviderProps}.
 * @returns The provider wrapping `children`.
 */
export function ToastProvider({
  children,
  defaultDuration = DEFAULT_DURATION,
}: ToastProviderProps): JSX.Element {
  const [toasts, setToasts] = useState<Toast[]>([]);
  // Track timers so we can clear them on manual dismiss / unmount (no leaks).
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const clearTimer = useCallback((id: string) => {
    const handle = timers.current.get(id);
    if (handle) {
      clearTimeout(handle);
      timers.current.delete(id);
    }
  }, []);

  const dismiss = useCallback(
    (id: string) => {
      clearTimer(id);
      setToasts((current) => current.filter((t) => t.id !== id));
    },
    [clearTimer],
  );

  const dismissAll = useCallback(() => {
    timers.current.forEach((handle) => clearTimeout(handle));
    timers.current.clear();
    setToasts([]);
  }, []);

  const toast = useCallback(
    (options: ToastOptions): string => {
      const id = options.id ?? makeId();
      const next: Toast = {
        id,
        title: options.title,
        description: options.description,
        variant: options.variant ?? 'info',
        duration: options.duration ?? defaultDuration,
      };

      // If an id was reused, replace the existing toast (and reset its timer).
      setToasts((current) => {
        const without = current.filter((t) => t.id !== id);
        return [...without, next];
      });
      clearTimer(id);

      if (next.duration > 0) {
        const handle = setTimeout(() => dismiss(id), next.duration);
        timers.current.set(id, handle);
      }
      return id;
    },
    [defaultDuration, clearTimer, dismiss],
  );

  // Clear all pending timers on unmount.
  useEffect(() => {
    const map = timers.current;
    return () => {
      map.forEach((handle) => clearTimeout(handle));
      map.clear();
    };
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({ toasts, toast, dismiss, dismissAll }),
    [toasts, toast, dismiss, dismissAll],
  );

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}

/**
 * Access the toast API.
 *
 * @returns The {@link ToastContextValue} (toast / dismiss / dismissAll / list).
 * @throws Error if called outside a {@link ToastProvider}.
 * @example
 * const { toast } = useToast();
 * toast({ variant: 'error', title: 'Не вдалося завантажити' });
 */
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (ctx === null) {
    throw new Error('useToast must be used within a <ToastProvider>.');
  }
  return ctx;
}

/** Props for {@link ToastItem}. */
export interface ToastItemProps {
  /** The toast to render. */
  toast: Toast;
  /** Dismiss callback (wired to the close button). */
  onDismiss: (id: string) => void;
}

/**
 * Render a single toast card (icon + text + close), color-coded by variant.
 *
 * `error`/`warning` use `role="alert"` (assertive) so they interrupt; the
 * gentler `success`/`info` use `role="status"` (polite).
 *
 * @param props - {@link ToastItemProps}.
 * @returns The toast element.
 */
export function ToastItem({ toast, onDismiss }: ToastItemProps): JSX.Element {
  const Icon = VARIANT_ICON[toast.variant];
  const colors = VARIANT_COLORS[toast.variant];
  const assertive = toast.variant === 'error' || toast.variant === 'warning';

  return (
    <div
      role={assertive ? 'alert' : 'status'}
      aria-live={assertive ? 'assertive' : 'polite'}
      className={cn(
        'pointer-events-auto flex w-full items-start gap-[var(--space-3)]',
        'rounded-[var(--radius-md)] border border-[var(--color-border)]',
        'bg-[var(--color-surface)] p-[var(--space-3)]',
        'shadow-[var(--shadow-md)]',
        'animate-[valeraup-toast-in_200ms_ease]',
      )}
    >
      {/* Variant chip — icon on a tinted background; decorative (text conveys). */}
      <span
        aria-hidden
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-md)]"
        style={{ color: colors.fg, backgroundColor: colors.bg }}
      >
        <Icon size={18} aria-hidden />
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
        <p className="text-[length:var(--font-size-sm)] font-[var(--font-weight-semibold)] text-[color:var(--color-text)]">
          {toast.title}
        </p>
        {toast.description && (
          <p className="text-[length:var(--font-size-xs)] text-[color:var(--color-text-muted)]">
            {toast.description}
          </p>
        )}
      </div>

      <button
        type="button"
        aria-label="Закрити сповіщення"
        onClick={() => onDismiss(toast.id)}
        className={cn(
          'flex h-11 w-11 shrink-0 items-center justify-center',
          'rounded-[var(--radius-md)] text-[color:var(--color-text-muted)]',
          'hover:bg-[var(--color-surface-muted)]',
          'focus-visible:outline-none',
        )}
      >
        <X size={18} aria-hidden />
      </button>
    </div>
  );
}
