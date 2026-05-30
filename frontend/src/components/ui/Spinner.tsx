/**
 * Spinner — an indeterminate loading indicator.
 *
 * Uses lucide's `Loader2` with the shared spin keyframe (`global.css`) so it
 * matches the spinner already used inside `StatusBadge`'s "recognizing" state.
 * Reads its color from the design tokens (defaults to the brand blue) and
 * carries an accessible label: it is announced as a busy status to screen
 * readers, while sighted users see the icon.
 */
import type { JSX } from 'react';
import { Loader2 } from 'lucide-react';

import { cn } from '@/lib/cn';

/** Props for {@link Spinner}. */
export interface SpinnerProps {
  /** Icon size in px. Defaults to 20 (comfortable inline size). */
  size?: number;
  /**
   * Accessible label announced to assistive tech. Defaults to a Ukrainian
   * "loading" string. Pass `null` to mark the spinner purely decorative (e.g.
   * when an adjacent text already conveys the loading state).
   */
  label?: string | null;
  /** Extra classes (e.g. a color override `text-[var(--color-text-muted)]`). */
  className?: string;
}

/**
 * Render a spinning loader.
 *
 * @param props - {@link SpinnerProps} (size, label, className).
 * @returns The spinner element.
 */
export function Spinner({
  size = 20,
  label = 'Завантаження…',
  className,
}: SpinnerProps): JSX.Element {
  // When labelled, expose status semantics; otherwise hide from a11y entirely.
  const a11y =
    label === null
      ? ({ 'aria-hidden': true } as const)
      : ({ role: 'status', 'aria-label': label } as const);

  return (
    <Loader2
      size={size}
      className={cn('animate-spin text-[var(--color-blue)]', className)}
      {...a11y}
    />
  );
}
