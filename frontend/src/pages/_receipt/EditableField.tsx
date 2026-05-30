/**
 * EditableField — an inline, tap-to-edit numeric field for receipt lines.
 *
 * Used on {@link ../ReceiptTablePage} for quantity and price. It shows the
 * current value as a labelled, full-size (≥44px) input and commits the change
 * via {@link EditableFieldProps.onCommit} when the field loses focus or the
 * operator presses Enter — cheap edits without a separate "save" tap, which
 * matters one-handed on a warehouse floor.
 *
 * It keeps a local draft so typing is smooth, and reconciles the draft whenever
 * the upstream `value` changes (e.g. after the parent refetches the receipt and
 * the server-normalized number comes back). Escape reverts to the last
 * committed value without firing `onCommit`.
 *
 * Decimal note: values are passed and returned as **strings** end-to-end so the
 * exact decimal (DRF serializes `DecimalField` as a string) is never coerced to
 * a lossy float. Parsing/validation is the backend's job; this field is purely
 * a string editor with a numeric keypad hint.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { InputHTMLAttributes, JSX } from 'react';

import { cn } from '@/lib/cn';

/** Props for {@link EditableField}. */
export interface EditableFieldProps {
  /** Visible field label (e.g. "Кількість", "Ціна"). */
  label: string;
  /** Current committed value as a string (empty string for "no value"). */
  value: string;
  /** Commit handler, called on blur / Enter with the new string value. */
  onCommit: (value: string) => void | Promise<void>;
  /** Placeholder shown when the value is empty. */
  placeholder?: string;
  /** Keyboard hint; defaults to `decimal` for the numeric pad. */
  inputMode?: InputHTMLAttributes<HTMLInputElement>['inputMode'];
  /** Disable editing (e.g. while the receipt is read-only). */
  disabled?: boolean;
}

/**
 * Render an inline-editable numeric string field.
 *
 * @param props - {@link EditableFieldProps}.
 * @returns The labelled inline field.
 */
export function EditableField({
  label,
  value,
  onCommit,
  placeholder,
  inputMode = 'decimal',
  disabled = false,
}: EditableFieldProps): JSX.Element {
  const [draft, setDraft] = useState<string>(value);
  // Track focus so we don't clobber the operator's in-progress edit when the
  // parent refetches and pushes a new `value` in.
  const focusedRef = useRef<boolean>(false);

  useEffect(() => {
    if (!focusedRef.current) {
      setDraft(value);
    }
  }, [value]);

  /** Commit the draft if it differs from the committed value. */
  const commit = useCallback(() => {
    focusedRef.current = false;
    if (draft !== value) {
      void onCommit(draft);
    }
  }, [draft, value, onCommit]);

  return (
    <label className="flex min-w-[6rem] flex-1 flex-col gap-[var(--space-1)]">
      <span className="text-[var(--font-size-xs)] font-[var(--font-weight-medium)] text-[var(--color-text-muted)]">
        {label}
      </span>
      <input
        type="text"
        inputMode={inputMode}
        value={draft}
        placeholder={placeholder}
        disabled={disabled}
        onFocus={() => {
          focusedRef.current = true;
        }}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            e.currentTarget.blur();
          } else if (e.key === 'Escape') {
            // Revert without committing.
            focusedRef.current = false;
            setDraft(value);
            e.currentTarget.blur();
          }
        }}
        className={cn(
          'min-h-[var(--touch-target-min)] w-full rounded-[var(--radius-md)]',
          'border border-[var(--color-border)] bg-[var(--color-surface)]',
          'px-[var(--space-3)] text-[var(--font-size-base)] text-[var(--color-text)]',
          'placeholder:text-[var(--color-text-muted)]',
          'transition-colors duration-150 focus-visible:outline-none',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
      />
    </label>
  );
}
