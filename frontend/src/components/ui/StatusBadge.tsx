/**
 * StatusBadge — compact pill that communicates a mapping or receipt status.
 *
 * ACCESSIBILITY (WCAG 1.4.1 "Use of Color"): status is NEVER conveyed by color
 * alone. Every badge pairs a distinct lucide icon AND a Ukrainian text label
 * with its color, so colorblind users and screen readers get the same meaning.
 *
 * Two badge families are supported:
 * - `match` — a {@link MatchStatus} for an individual receipt line
 *   (auto / manual / unmapped).
 * - `receipt` — a {@link ReceiptStatus} for the whole receipt lifecycle.
 */
import type { JSX } from 'react';

import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  FileSpreadsheet,
  Hand,
  Loader2,
  XCircle,
  type LucideIcon,
} from 'lucide-react';

import { cn } from '@/lib/cn';
import type { MatchStatus, ReceiptStatus } from '@/types';

/** Visual descriptor for a single status value. */
interface BadgeSpec {
  /** Ukrainian label shown to the user (and read by screen readers). */
  label: string;
  /** Distinct icon so meaning never depends on color alone. */
  icon: LucideIcon;
  /** Foreground (text + icon) color token. */
  fg: string;
  /** Background color token. */
  bg: string;
}

/** Per-line mapping statuses -> visual spec. */
const MATCH_SPECS: Record<MatchStatus, BadgeSpec> = {
  auto: {
    label: 'Авто',
    icon: CheckCircle2,
    fg: 'var(--color-success)',
    bg: 'var(--color-success-bg)',
  },
  manual: {
    label: 'Вручну',
    icon: Hand,
    fg: 'var(--color-warning)',
    bg: 'var(--color-warning-bg)',
  },
  unmapped: {
    label: 'Не знайдено',
    icon: AlertTriangle,
    fg: 'var(--color-danger)',
    bg: 'var(--color-danger-bg)',
  },
};

/** Receipt lifecycle statuses -> visual spec. */
const RECEIPT_SPECS: Record<ReceiptStatus, BadgeSpec> = {
  draft: {
    label: 'Чернетка',
    icon: CircleDot,
    fg: 'var(--color-text-muted)',
    bg: 'var(--color-surface-muted)',
  },
  recognizing: {
    label: 'Розпізнається',
    icon: Loader2,
    fg: 'var(--color-info)',
    bg: 'var(--color-info-bg)',
  },
  needs_mapping: {
    label: 'Потрібен маппінг',
    icon: AlertTriangle,
    fg: 'var(--color-warning)',
    bg: 'var(--color-warning-bg)',
  },
  ready: {
    label: 'Готовий',
    icon: CheckCircle2,
    fg: 'var(--color-success)',
    bg: 'var(--color-success-bg)',
  },
  xlsx_ready: {
    label: 'Excel готовий',
    icon: FileSpreadsheet,
    fg: 'var(--color-success)',
    bg: 'var(--color-success-bg)',
  },
  error: {
    label: 'Помилка',
    icon: XCircle,
    fg: 'var(--color-danger)',
    bg: 'var(--color-danger-bg)',
  },
};

/** Props for {@link StatusBadge}. Exactly one of `match` / `receipt` is given. */
export type StatusBadgeProps = { className?: string } & (
  | { match: MatchStatus; receipt?: never }
  | { receipt: ReceiptStatus; match?: never }
);

/**
 * Render a status pill with an icon + text label.
 *
 * @param props - {@link StatusBadgeProps}: either a `match` or a `receipt`
 *   status, plus an optional `className`.
 * @returns The rendered badge element.
 */
export function StatusBadge({
  match,
  receipt,
  className,
}: StatusBadgeProps): JSX.Element {
  const spec: BadgeSpec =
    match !== undefined ? MATCH_SPECS[match] : RECEIPT_SPECS[receipt];
  const Icon = spec.icon;
  // Spinner-style icons (recognizing) get a subtle rotation to signal progress.
  const isBusy = receipt === 'recognizing';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-[var(--radius-full)]',
        'px-[var(--space-2)] py-[2px] text-[var(--font-size-xs)] font-[var(--font-weight-medium)]',
        className,
      )}
      style={{ color: spec.fg, backgroundColor: spec.bg }}
    >
      <Icon
        size={14}
        aria-hidden
        className={isBusy ? 'animate-spin' : undefined}
      />
      <span>{spec.label}</span>
    </span>
  );
}
