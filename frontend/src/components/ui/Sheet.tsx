/**
 * Sheet — an accessible bottom-sheet built on `@radix-ui/react-dialog`.
 *
 * This is the primitive the {@link ../MappingSheet} (and any future mobile
 * dialog) composes with. Radix gives us, for free, the things a hand-rolled
 * sheet repeatedly gets wrong:
 * - a real focus trap + focus restore on close,
 * - `Esc` to dismiss and `aria-modal` / labelled-dialog semantics,
 * - a portal so the sheet escapes overflow/stacking contexts,
 * - scroll-locking the page behind the sheet.
 *
 * We layer on the *visual* part: a navy backdrop and a token-styled panel that
 * slides up from the bottom (animations in `global.css`, suppressed under
 * `prefers-reduced-motion`). All colors/radii come from the design tokens, so
 * the sheet reskins in dark mode.
 *
 * Composition (mirrors Radix Dialog):
 * @example
 * <Sheet open={open} onOpenChange={setOpen}>
 *   <SheetContent>
 *     <SheetHeader>
 *       <SheetTitle>Прив’язати товар</SheetTitle>
 *       <SheetDescription>{sku}</SheetDescription>
 *     </SheetHeader>
 *     …body…
 *   </SheetContent>
 * </Sheet>
 */
import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type JSX,
  type ReactNode,
} from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';

import { cn } from '@/lib/cn';

/**
 * Sheet root — controls open state. Thin pass-through over `Dialog.Root` so the
 * controlled `open` / `onOpenChange` API matches Radix exactly.
 */
export const Sheet = Dialog.Root;

/** Optional trigger element (`Dialog.Trigger`) for uncontrolled usage. */
export const SheetTrigger = Dialog.Trigger;

/** Programmatic close affordance (`Dialog.Close`) usable inside the content. */
export const SheetClose = Dialog.Close;

/** Props for {@link SheetContent}. */
export interface SheetContentProps
  extends ComponentPropsWithoutRef<typeof Dialog.Content> {
  /** Sheet body. Typically a {@link SheetHeader} plus scrollable content. */
  children: ReactNode;
  /** Hide the built-in top-right close button (e.g. a custom header X). */
  hideClose?: boolean;
  /** Accessible label when no visible {@link SheetTitle} is rendered. Prefer a
   * real `SheetTitle` for sighted users; this is the fallback Radix needs. */
  ariaLabel?: string;
}

/**
 * The sliding bottom panel + backdrop, rendered into a portal.
 *
 * @param props - {@link SheetContentProps} (children, hideClose, ariaLabel,
 *   plus any `Dialog.Content` props such as `onOpenAutoFocus`).
 * @param ref - Forwarded to the Radix content element.
 * @returns The portalled overlay + sheet panel.
 */
export const SheetContent = forwardRef<HTMLDivElement, SheetContentProps>(
  ({ children, hideClose = false, ariaLabel, className, ...props }, ref) => (
    <Dialog.Portal>
      {/* Backdrop — navy wash; click-outside closes via Radix. */}
      <Dialog.Overlay
        data-valeraup-sheet-overlay=""
        className="fixed inset-0 z-50"
        style={{ backgroundColor: 'rgba(10,26,63,0.45)' }}
      />
      <Dialog.Content
        ref={ref}
        data-valeraup-sheet-content=""
        aria-label={ariaLabel}
        className={cn(
          'fixed inset-x-0 bottom-0 z-50',
          'flex max-h-[85dvh] flex-col',
          'rounded-t-[var(--radius-lg)] border-t border-[var(--color-border)]',
          'bg-[var(--color-surface)] text-[color:var(--color-text)]',
          'shadow-[var(--shadow-lg)]',
          // Honor the home-indicator safe area at the bottom of the panel.
          'pb-[env(safe-area-inset-bottom)]',
          'focus-visible:outline-none',
          className,
        )}
        {...props}
      >
        {/* Grab handle — a familiar bottom-sheet affordance. */}
        <div
          aria-hidden
          className="mx-auto mt-[var(--space-2)] h-1 w-10 rounded-[var(--radius-full)] bg-[var(--color-border)]"
        />

        {children}

        {!hideClose && (
          <Dialog.Close
            aria-label="Закрити"
            className={cn(
              'absolute right-[var(--space-3)] top-[var(--space-3)]',
              'flex h-11 w-11 items-center justify-center rounded-[var(--radius-md)]',
              'text-[color:var(--color-text-muted)]',
              'hover:bg-[var(--color-surface-muted)]',
              'focus-visible:outline-none',
            )}
          >
            <X size={20} aria-hidden />
          </Dialog.Close>
        )}
      </Dialog.Content>
    </Dialog.Portal>
  ),
);

SheetContent.displayName = 'SheetContent';

/** Props for {@link SheetHeader}. */
export type SheetHeaderProps = ComponentPropsWithoutRef<'div'>;

/**
 * Header region — groups the title/description with a divider below.
 *
 * @param props - Native `div` props (children, className).
 * @returns The header element.
 */
export function SheetHeader({
  className,
  ...props
}: SheetHeaderProps): JSX.Element {
  return (
    <div
      className={cn(
        'flex flex-col gap-[var(--space-1)]',
        'border-b border-[var(--color-border)]',
        'px-[var(--space-4)] pb-[var(--space-3)] pt-[var(--space-2)] pr-[var(--space-12)]',
        className,
      )}
      {...props}
    />
  );
}

/**
 * The sheet's accessible title (`Dialog.Title`). Renders a visible heading and
 * is announced as the dialog's name.
 *
 * @param props - `Dialog.Title` props (children, className).
 * @returns The title element.
 */
export function SheetTitle({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof Dialog.Title>): JSX.Element {
  return (
    <Dialog.Title
      className={cn(
        'text-[length:var(--font-size-lg)] font-[var(--font-weight-semibold)]',
        className,
      )}
      {...props}
    />
  );
}

/**
 * Secondary description line (`Dialog.Description`), e.g. the recognized SKU.
 *
 * @param props - `Dialog.Description` props (children, className).
 * @returns The description element.
 */
export function SheetDescription({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof Dialog.Description>): JSX.Element {
  return (
    <Dialog.Description
      className={cn(
        'text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)]',
        className,
      )}
      {...props}
    />
  );
}

/** Props for {@link SheetBody}. */
export type SheetBodyProps = ComponentPropsWithoutRef<'div'>;

/**
 * Scrollable body region — fills remaining height and scrolls independently so
 * the header/grab-handle stay pinned.
 *
 * @param props - Native `div` props (children, className).
 * @returns The body element.
 */
export function SheetBody({
  className,
  ...props
}: SheetBodyProps): JSX.Element {
  return (
    <div
      className={cn(
        'flex-1 overflow-y-auto px-[var(--space-4)] py-[var(--space-4)]',
        className,
      )}
      {...props}
    />
  );
}
