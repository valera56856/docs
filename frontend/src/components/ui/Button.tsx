/**
 * Button — the primary interactive control for the Valeraup PWA.
 *
 * Built on {@link https://cva.style class-variance-authority} for typed,
 * composable variants and on Radix `Slot` for the `asChild` pattern (so a
 * `<Button asChild><Link/></Button>` renders the child element while keeping
 * the button styling and a11y attributes).
 *
 * Design rules baked in:
 * - Minimum 44x44px touch target (`--touch-target-min`) — mobile is primary.
 * - Reads colors / radii / spacing exclusively from the NextCRM design tokens.
 * - Visible focus ring via the global `:focus-visible` rule.
 */
import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/cn';

/**
 * Variant definitions for the button.
 *
 * `intent` controls color treatment; `size` controls padding + min height.
 * The base classes enforce the shared shape, typography, transition, and the
 * disabled / focus behaviour every button shares.
 */
export const buttonVariants = cva(
  // Base: layout, typography, focus, disabled, and the 44px touch floor.
  [
    'inline-flex items-center justify-center gap-2',
    'rounded-[var(--radius-md)] font-[var(--font-weight-semibold)]',
    'min-h-[var(--touch-target-min)]',
    'transition-[background-color,box-shadow,color,transform,border-color] duration-150',
    'active:scale-[0.98]',
    'select-none whitespace-nowrap',
    'disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100',
    'focus-visible:outline-none',
  ].join(' '),
  {
    variants: {
      /** Visual treatment / semantic weight of the action. */
      intent: {
        /** Brand-filled call to action (electric blue). ONE per view. The
            always-white `--color-on-accent` keeps the label crisp, and a soft
            brand glow lifts it off the surface. */
        primary:
          'bg-[var(--color-blue)] text-[color:var(--color-on-accent)] shadow-[var(--shadow-accent)] hover:bg-[var(--color-blue-600)]',
        /** Low-emphasis bordered button on the app surface. */
        secondary:
          'bg-[var(--color-surface)] text-[color:var(--color-text)] border border-[var(--color-border-strong)] shadow-[var(--shadow-xs)] hover:bg-[var(--color-surface-muted)] hover:border-[var(--color-border-strong)]',
        /** Minimal, text-only button (e.g. inline actions). */
        ghost:
          'bg-transparent text-[color:var(--color-blue)] hover:bg-[var(--color-info-bg)]',
        /** Destructive action, QUIET by default — a tinted text button, not a
            loud red fill. Reserve the filled look for the confirm step. */
        danger:
          'bg-transparent text-[color:var(--color-danger)] hover:bg-[var(--color-danger-bg)]',
        /** Loud destructive fill — for the final confirm only, used sparingly. */
        'danger-solid':
          'bg-[var(--color-danger)] text-[color:var(--color-on-accent)] hover:opacity-90',
      },
      /** Control sizing — `lg` is the comfortable mobile default. */
      size: {
        sm: 'h-11 px-[var(--space-3)] text-[length:var(--font-size-sm)]',
        md: 'h-11 px-[var(--space-4)] text-[length:var(--font-size-base)]',
        lg: 'h-12 px-[var(--space-5)] text-[length:var(--font-size-lg)]',
        /** Square icon-only button; still respects the 44px minimum. */
        icon: 'h-11 w-11 p-0',
      },
      /** Stretch to fill the parent width — common on mobile full-width CTAs. */
      fullWidth: {
        true: 'w-full',
        false: '',
      },
    },
    defaultVariants: {
      intent: 'primary',
      size: 'md',
      fullWidth: false,
    },
  },
);

/** Props accepted by {@link Button}. */
export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /**
   * Render the button's styling onto its single child element instead of a
   * native `<button>`. Useful for links: `<Button asChild><Link/></Button>`.
   */
  asChild?: boolean;
}

/**
 * Accessible, variant-driven button.
 *
 * @param props - {@link ButtonProps} (intent, size, fullWidth, asChild, plus
 *   any native button attributes).
 * @param ref - Forwarded to the underlying element.
 * @returns The rendered button (or slotted child when `asChild`).
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, intent, size, fullWidth, asChild = false, ...props }, ref) => {
    // When `asChild` is set, Slot merges our props/classes onto the child.
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ intent, size, fullWidth }), className)}
        {...props}
      />
    );
  },
);

Button.displayName = 'Button';
