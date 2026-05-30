/**
 * Skeleton — a content placeholder shown while data loads.
 *
 * Renders a softly pulsing block (the `valeraup-skeleton-pulse` keyframe in
 * `global.css`, suppressed under `prefers-reduced-motion`). Used by the
 * Suppliers list, the Receipt table while `status === 'recognizing'`, and the
 * mapping search — anywhere we'd otherwise flash empty space on load.
 *
 * Accessibility: a skeleton is decorative scaffolding, so it is `aria-hidden`.
 * The surrounding region should expose its own loading status (e.g. a
 * `role="status"` label or a {@link Spinner}) for screen-reader users.
 */
import type { CSSProperties, JSX } from 'react';

import { cn } from '@/lib/cn';

/** Props for {@link Skeleton}. */
export interface SkeletonProps {
  /** Extra classes — set width/height/shape here, e.g. `h-4 w-32`. */
  className?: string;
  /** Inline width (number → px, or any CSS length string). */
  width?: number | string;
  /** Inline height (number → px, or any CSS length string). */
  height?: number | string;
  /** Render as a circle (e.g. avatar/thumbnail placeholder). */
  circle?: boolean;
  /** Extra inline styles, merged after width/height. */
  style?: CSSProperties;
}

/** Normalize a number to a px string; pass through string lengths untouched. */
function toLength(value: number | string | undefined): string | undefined {
  if (value === undefined) {
    return undefined;
  }
  return typeof value === 'number' ? `${value}px` : value;
}

/**
 * Render a pulsing placeholder block.
 *
 * @param props - {@link SkeletonProps} (className, width, height, circle, style).
 * @returns The skeleton element.
 */
export function Skeleton({
  className,
  width,
  height,
  circle = false,
  style,
}: SkeletonProps): JSX.Element {
  return (
    <span
      aria-hidden
      className={cn(
        'block bg-[var(--color-surface-muted)]',
        'animate-[valeraup-skeleton-pulse_1.4s_ease-in-out_infinite]',
        circle ? 'rounded-[var(--radius-full)]' : 'rounded-[var(--radius-md)]',
        className,
      )}
      style={{ width: toLength(width), height: toLength(height), ...style }}
    />
  );
}
