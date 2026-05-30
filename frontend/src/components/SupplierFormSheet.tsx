/**
 * SupplierFormSheet — a bottom-sheet form to create or edit a {@link Supplier}.
 *
 * One sheet serves both modes (driven by the `supplier` prop): when a supplier
 * is passed the form pre-fills for an edit, otherwise it starts blank for a
 * create. The sheet is *presentation only* — it validates locally (a non-empty
 * name) and hands the resulting {@link SupplierInput} back via `onSubmit`; the
 * caller owns the API call, toasts, and list refresh, then closes the sheet.
 *
 * Built on the kit {@link Sheet} (Radix Dialog), so it inherits a focus trap,
 * Esc-to-dismiss, scroll-lock and the slide-up animation. All controls clear the
 * 44px touch floor for one-handed warehouse use.
 */
import { useEffect, useState } from 'react';
import type { JSX } from 'react';

import { cn } from '@/lib/cn';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import type { Supplier, SupplierInput } from '@/types';

/** Props for {@link SupplierFormSheet}. */
export interface SupplierFormSheetProps {
  /** Whether the sheet is visible. */
  open: boolean;
  /**
   * The supplier to edit, or `null`/`undefined` to create a new one. Drives the
   * title, the pre-filled fields, and the submit button label.
   */
  supplier?: Supplier | null;
  /** True while the caller persists the form (disables inputs + submit). */
  saving?: boolean;
  /**
   * Called with the validated form values when the operator submits. The caller
   * performs the create/update and decides when to close (so it can keep the
   * sheet open on error).
   *
   * @param data - The validated {@link SupplierInput}.
   */
  onSubmit: (data: SupplierInput) => void;
  /** Called to dismiss the sheet without saving. */
  onClose: () => void;
}

/**
 * Create/edit supplier form in a bottom-sheet.
 *
 * @param props - {@link SupplierFormSheetProps}.
 * @returns The sheet element (the Radix portal renders nothing while closed).
 */
export function SupplierFormSheet({
  open,
  supplier,
  saving = false,
  onSubmit,
  onClose,
}: SupplierFormSheetProps): JSX.Element {
  const isEdit = Boolean(supplier);
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [touched, setTouched] = useState(false);

  // (Re)seed the form whenever the sheet opens for a different target. Keying on
  // both `open` and the supplier id ensures switching from "edit A" to "add" (or
  // to "edit B") repaints the fields rather than keeping stale values.
  useEffect(() => {
    if (open) {
      setName(supplier?.name ?? '');
      setNote(supplier?.note ?? '');
      setIsActive(supplier?.is_active ?? true);
      setTouched(false);
    }
  }, [open, supplier?.id, supplier?.name, supplier?.note, supplier?.is_active]);

  const trimmedName = name.trim();
  const nameError = touched && !trimmedName ? 'Вкажіть назву.' : undefined;

  const handleSubmit = (): void => {
    setTouched(true);
    if (!trimmedName) {
      return;
    }
    onSubmit({ name: trimmedName, note: note.trim(), is_active: isActive });
  };

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
    >
      <SheetContent ariaLabel={isEdit ? 'Редагувати постачальника' : 'Додати постачальника'}>
        <SheetHeader>
          <SheetTitle>
            {isEdit ? 'Редагувати постачальника' : 'Додати постачальника'}
          </SheetTitle>
        </SheetHeader>

        <SheetBody className="flex flex-col gap-[var(--space-4)]">
          <Input
            label="Назва"
            value={name}
            disabled={saving}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="Напр. ТОВ «Постачальник»"
            error={nameError}
          />

          <Input
            label="Примітка"
            value={note}
            disabled={saving}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Необовʼязково"
            hint="Особливості накладних, контакти тощо."
          />

          {/* Active toggle — a labelled switch built from a checkbox so it stays
              accessible and keyboard-operable without extra deps. */}
          <label
            className={cn(
              'flex min-h-[var(--touch-target-min)] items-center justify-between gap-[var(--space-3)]',
              'rounded-[var(--radius-md)] border border-[var(--color-border)]',
              'bg-[var(--color-surface)] px-[var(--space-3)]',
              saving && 'opacity-50',
            )}
          >
            <span className="flex flex-col">
              <span className="text-[length:var(--font-size-sm)] font-[var(--font-weight-medium)] text-[color:var(--color-text)]">
                Активний
              </span>
              <span className="text-[length:var(--font-size-xs)] text-[color:var(--color-text-muted)]">
                Доступний операторам для вибору.
              </span>
            </span>
            <input
              type="checkbox"
              checked={isActive}
              disabled={saving}
              onChange={(e) => setIsActive(e.target.checked)}
              className="h-6 w-6 accent-[var(--color-blue)]"
              aria-label="Активний"
            />
          </label>

          <div className="mt-[var(--space-2)] flex flex-col gap-[var(--space-2)]">
            <Button
              fullWidth
              disabled={saving}
              onClick={handleSubmit}
            >
              {saving ? 'Збереження…' : isEdit ? 'Зберегти' : 'Додати'}
            </Button>
            <Button intent="ghost" disabled={saving} onClick={onClose}>
              Скасувати
            </Button>
          </div>
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
