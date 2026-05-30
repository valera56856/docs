/**
 * Input — a labelled text field with optional helper text and an error state.
 *
 * Design rules baked in:
 * - A visible `<label>` is associated with the control (generated id if none is
 *   passed) so taps on the label focus the field and screen readers announce it.
 * - The 44px touch floor (`--touch-target-min`) — mobile is the primary surface.
 * - Reads colors / radii / spacing exclusively from the NextCRM design tokens,
 *   so it reskins automatically in dark mode.
 * - Error messaging is wired via `aria-invalid` + `aria-describedby` and never
 *   relies on color alone (an explicit message is rendered).
 */
import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';

import { cn } from '@/lib/cn';

/** Props for {@link Input}. Extends the native input attributes. */
export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Visible field label (required for accessibility). */
  label: string;
  /**
   * Error message. When present the field paints its danger border and the
   * message is announced to assistive tech via `aria-describedby`.
   */
  error?: string;
  /** Optional helper/hint text shown below the field when there is no error. */
  hint?: ReactNode;
  /** Hide the label visually while keeping it for screen readers. */
  labelHidden?: boolean;
  /** Extra classes for the outer wrapper (the label + field + message group). */
  wrapperClassName?: string;
}

/**
 * Accessible labelled text input with an error state.
 *
 * @param props - {@link InputProps} (label, error, hint, plus any native input
 *   attributes such as `type`, `value`, `onChange`, `inputMode`).
 * @param ref - Forwarded to the underlying `<input>`.
 * @returns The rendered field group.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      hint,
      labelHidden = false,
      wrapperClassName,
      className,
      id,
      disabled,
      ...props
    },
    ref,
  ) => {
    // Stable generated ids so label/field/message wiring works even when the
    // caller does not pass an explicit `id`.
    const generatedId = useId();
    const inputId = id ?? `${generatedId}-input`;
    const messageId = `${generatedId}-message`;
    const hasError = Boolean(error);
    // Only describe by a message element when one is actually rendered.
    const describedBy = hasError || hint ? messageId : undefined;

    return (
      <div className={cn('flex flex-col gap-[var(--space-1)]', wrapperClassName)}>
        <label
          htmlFor={inputId}
          className={cn(
            'text-[length:var(--font-size-sm)] font-[var(--font-weight-medium)] text-[color:var(--color-text)]',
            labelHidden && 'sr-only',
          )}
        >
          {label}
        </label>

        <input
          ref={ref}
          id={inputId}
          disabled={disabled}
          aria-invalid={hasError || undefined}
          aria-describedby={describedBy}
          className={cn(
            'min-h-[var(--touch-target-min)] w-full rounded-[var(--radius-md)]',
            'border bg-[var(--color-surface)] px-[var(--space-3)]',
            'text-[length:var(--font-size-base)] text-[color:var(--color-text)]',
            'shadow-[var(--shadow-xs)]',
            'placeholder:text-[color:var(--color-text-muted)]',
            'transition-[border-color,box-shadow] duration-150',
            'focus-visible:outline-none focus-visible:border-[var(--color-blue)]',
            'disabled:cursor-not-allowed disabled:opacity-50',
            // Danger border on error, neutral border otherwise. The focus ring
            // is supplied globally by the :focus-visible rule.
            hasError
              ? 'border-[var(--color-danger)]'
              : 'border-[var(--color-border-strong)]',
            className,
          )}
          {...props}
        />

        {/* Error wins over hint; both share the described-by target. The error
            uses role="alert" so it is announced when it appears. */}
        {hasError ? (
          <p
            id={messageId}
            role="alert"
            className="text-[length:var(--font-size-xs)] text-[color:var(--color-danger)]"
          >
            {error}
          </p>
        ) : hint ? (
          <p
            id={messageId}
            className="text-[length:var(--font-size-xs)] text-[color:var(--color-text-muted)]"
          >
            {hint}
          </p>
        ) : null}
      </div>
    );
  },
);

Input.displayName = 'Input';
