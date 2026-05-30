/**
 * EmptyState — the friendly "there's nothing here (yet)" panel.
 *
 * Shown when a list resolves to zero items (no suppliers, no recognized lines,
 * search with no hits) or, with an action, as a soft error/recovery surface
 * ("couldn't load — retry"). A first-class empty state beats rendering blank
 * space: it tells the operator *why* it's empty and *what to do next*.
 *
 * Layout: centered icon → title → hint → optional action button, all from the
 * design tokens so it reskins in dark mode.
 */
import type { JSX, ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

import { cn } from '@/lib/cn';

/** Props for {@link EmptyState}. */
export interface EmptyStateProps {
  /** Icon illustrating the empty/idle state (e.g. `Inbox`, `SearchX`). */
  icon: LucideIcon;
  /** Short, primary message (the "what"). */
  title: string;
  /** Optional secondary line giving guidance (the "why / what next"). */
  hint?: ReactNode;
  /**
   * Optional call-to-action, typically a {@link ../ui/Button} ("Спробувати ще
   * раз", "Синхронізувати каталог"). Rendered below the hint.
   */
  action?: ReactNode;
  /** Extra classes for the outer container. */
  className?: string;
}

/**
 * Render a centered empty/idle state.
 *
 * @param props - {@link EmptyStateProps} (icon, title, hint, action, className).
 * @returns The empty-state element.
 */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  action,
  className,
}: EmptyStateProps): JSX.Element {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        'gap-[var(--space-3)] px-[var(--space-6)] py-[var(--space-12)]',
        className,
      )}
    >
      {/* Token-tinted icon chip keeps the illustration on-brand and subtle —
          a soft info wash + ring reads more intentional than flat grey. */}
      <span
        aria-hidden
        className={cn(
          'flex h-16 w-16 items-center justify-center rounded-[var(--radius-full)]',
          'bg-[var(--color-info-bg)] text-[color:var(--color-blue)]',
          'ring-1 ring-inset ring-[var(--color-surface-glass-border,transparent)]',
        )}
      >
        <Icon size={28} aria-hidden />
      </span>

      <h2 className="text-[length:var(--font-size-lg)] font-[var(--font-weight-semibold)] text-[color:var(--color-text)]">
        {title}
      </h2>

      {hint && (
        <p className="max-w-xs text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)]">
          {hint}
        </p>
      )}

      {action && <div className="mt-[var(--space-2)]">{action}</div>}
    </div>
  );
}
