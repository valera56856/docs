/**
 * Card — the surface primitive for grouping content (supplier rows, receipt
 * line cards, generate-screen panels, etc.).
 *
 * Two visual treatments, selectable via `variant`:
 * - `solid` — a flat opaque surface (`--color-surface`) for dense lists where
 *   blur would be distracting or costly.
 * - `glass` (default) — the "Liquid Glass 2026" treatment: a translucent
 *   surface with a `backdrop-filter` blur+saturate, a soft navy→cyan accent
 *   gradient, a hairline border, and a subtle inset highlight. All of it is
 *   driven by the `--surface-glass*` / `--glass-*` tokens so it adapts to dark
 *   mode automatically. The blur degrades gracefully to the plain translucent
 *   surface where `backdrop-filter` is unsupported.
 *
 * When `interactive` is set the card grows hover/active affordances and a
 * focus ring, and renders as a `<button>` by default so a whole card is a
 * single ≥44px tap target (the supplier/receipt-row pattern).
 */
import {
  forwardRef,
  type CSSProperties,
  type ElementType,
  type HTMLAttributes,
} from 'react';

import { cn } from '@/lib/cn';

/** Visual treatment of the card surface. */
export type CardVariant = 'glass' | 'solid';

/** Props for {@link Card}. Extends generic element attributes. */
export interface CardProps extends HTMLAttributes<HTMLElement> {
  /** Surface treatment. Defaults to the frosted `glass` look. */
  variant?: CardVariant;
  /**
   * Add hover/active/focus affordances and render as a `<button>` (unless `as`
   * overrides the element). Use for tappable rows.
   */
  interactive?: boolean;
  /**
   * Override the rendered element (e.g. `'article'`, `'li'`, `'section'`).
   * Defaults to `'button'` when `interactive`, otherwise `'div'`.
   */
  as?: ElementType;
  /**
   * Disable an interactive card (only meaningful when it renders as a
   * `<button>`). Exposed here because `HTMLAttributes` omits it.
   */
  disabled?: boolean;
  /**
   * Button `type` for the interactive (`<button>`) case. Defaults to `'button'`
   * so a card inside a `<form>` never submits it accidentally.
   */
  type?: 'button' | 'submit' | 'reset';
}

/** Inline styles applied to the glass variant. Kept inline (not Tailwind
 * arbitrary values) because `backdrop-filter` + a gradient `background` are
 * cleaner to express here and read straight from tokens. */
const glassStyle: CSSProperties = {
  background: 'var(--glass-gradient), var(--surface-glass)',
  backdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
  WebkitBackdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
  borderColor: 'var(--surface-glass-border)',
  boxShadow: 'var(--glass-shadow), inset 0 1px 0 var(--glass-highlight)',
};

/**
 * Surface container with an optional frosted-glass treatment.
 *
 * @param props - {@link CardProps} (variant, interactive, as, plus native
 *   attributes for the chosen element).
 * @param ref - Forwarded to the underlying element.
 * @returns The rendered card.
 */
export const Card = forwardRef<HTMLElement, CardProps>(
  (
    {
      variant = 'glass',
      interactive = false,
      as,
      type,
      className,
      style,
      ...props
    },
    ref,
  ) => {
    const Comp = (as ?? (interactive ? 'button' : 'div')) as ElementType;
    const isGlass = variant === 'glass';
    // Default the button `type` so an interactive card inside a form never
    // submits it; only forward `type` when we actually render a <button>.
    const buttonType =
      Comp === 'button' ? { type: type ?? 'button' } : undefined;

    return (
      <Comp
        ref={ref}
        {...buttonType}
        className={cn(
          'rounded-[var(--radius-lg)] border p-[var(--space-4)]',
          'text-left text-[var(--color-text)]',
          'transition-[transform,box-shadow,background-color] duration-150',
          // Solid variant: opaque surface + token border + standard elevation.
          !isGlass && [
            'bg-[var(--color-surface)] border-[var(--color-border)]',
            'shadow-[var(--shadow-sm)]',
          ],
          // Interactive affordances: lift on hover, settle on press, focus ring.
          interactive && [
            'block w-full cursor-pointer',
            'hover:-translate-y-0.5 hover:shadow-[var(--shadow-md)]',
            'active:translate-y-0 active:shadow-[var(--shadow-sm)]',
            'focus-visible:outline-none',
            'disabled:cursor-not-allowed disabled:opacity-50',
          ],
          className,
        )}
        // Glass styles are inline (token-driven); caller `style` can still
        // override individual properties.
        style={isGlass ? { ...glassStyle, ...style } : style}
        {...props}
      />
    );
  },
);

Card.displayName = 'Card';
