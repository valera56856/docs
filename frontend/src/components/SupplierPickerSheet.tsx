/**
 * SupplierPickerSheet — a reusable bottom-sheet for searching the supplier
 * directory and picking a single {@link Supplier}.
 *
 * This is the supplier-side sibling of {@link ProductPickerSheet}: it owns the
 * same explicit loading / empty / error UX (≥44px result rows, idle hint, search
 * box) but is *side-effect free* — instead of persisting anything, it hands the
 * chosen supplier back to the caller via `onSelect`. The receipt table uses it
 * to set / change the auto-detected supplier (`receipts.setSupplier`), so the
 * persistence + re-mapping decision stays with the caller.
 *
 * WHY a client-side filter rather than a `?q` request: the suppliers endpoint
 * (`GET /api/suppliers/`) has no search parameter and the directory is small (a
 * handful of vendors), so we fetch the active list once on open and filter it in
 * memory. That keeps the interaction instant and avoids inventing a backend
 * query the contract does not define. If the directory ever grows large, swap
 * the in-memory filter for a debounced `?q` call without changing this API.
 *
 * Built on the kit {@link Sheet} (Radix Dialog) primitive, so we inherit a real
 * focus trap, Esc-to-dismiss, scroll-lock, the portal, and the slide-up
 * animation for free.
 */
import { useEffect, useMemo, useState } from 'react';
import type { JSX, ReactNode } from 'react';
import { SearchX, Store } from 'lucide-react';

import { suppliers as suppliersApi } from '@/lib/api';
import { cn } from '@/lib/cn';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { Input } from '@/components/ui/Input';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import type { Supplier } from '@/types';

/** Props for {@link SupplierPickerSheet}. */
export interface SupplierPickerSheetProps {
  /** Whether the sheet is visible. */
  open: boolean;
  /** Visible sheet title (defaults to "Оберіть постачальника"). */
  title?: string;
  /** Optional context line under the title (e.g. the recognized name/ЄДРПОУ). */
  description?: ReactNode;
  /**
   * True while the caller is persisting the selection (e.g. an in-flight
   * `receipts.setSupplier`). Disables the result rows so the user can't
   * double-pick while the request is in flight.
   */
  saving?: boolean;
  /**
   * Called when the operator picks a supplier. The caller performs the actual
   * persistence and decides when to close the sheet (so it can keep the sheet
   * open and surface an error if the save fails).
   *
   * @param supplier - The chosen supplier.
   */
  onSelect: (supplier: Supplier) => void;
  /** Called to dismiss the sheet without selecting. */
  onClose: () => void;
}

/**
 * Supplier-search bottom-sheet that returns the chosen supplier.
 *
 * @param props - {@link SupplierPickerSheetProps}.
 * @returns The sheet element (the Radix portal renders nothing while closed).
 */
export function SupplierPickerSheet({
  open,
  title = 'Оберіть постачальника',
  description,
  saving = false,
  onSelect,
  onClose,
}: SupplierPickerSheetProps): JSX.Element {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<Supplier[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch the active supplier directory once each time the sheet opens. We reset
  // the query so a reopened sheet starts clean.
  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    setQuery('');
    setIsLoading(true);
    setError(null);
    (async () => {
      try {
        const data = await suppliersApi.list();
        if (!cancelled) {
          setItems(data);
        }
      } catch {
        if (!cancelled) {
          setError('Не вдалося завантажити постачальників. Спробуйте ще раз.');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  // In-memory, case-insensitive filter over name + ЄДРПОУ. Empty query shows all
  // suppliers so the operator can browse without typing.
  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase('uk');
    if (!q) {
      return items;
    }
    return items.filter(
      (s) =>
        s.name.toLocaleLowerCase('uk').includes(q) ||
        s.edrpou.toLocaleLowerCase('uk').includes(q),
    );
  }, [items, query]);

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
    >
      <SheetContent ariaLabel={title}>
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description ? (
            <SheetDescription>{description}</SheetDescription>
          ) : null}
        </SheetHeader>

        <SheetBody className="flex flex-col gap-[var(--space-3)]">
          <Input
            label="Пошук постачальника"
            labelHidden
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Пошук за назвою або ЄДРПОУ…"
            inputMode="search"
            error={error ?? undefined}
          />

          {/* Skeleton rows while the directory loads. */}
          {isLoading && (
            <ul className="flex flex-col gap-1" aria-hidden>
              {Array.from({ length: 5 }).map((_, i) => (
                <li key={i}>
                  <Skeleton height={48} className="w-full" />
                </li>
              ))}
            </ul>
          )}

          {/* No suppliers exist at all. */}
          {!isLoading && !error && items.length === 0 && (
            <EmptyState
              icon={Store}
              title="Немає постачальників"
              hint="Додайте активних постачальників у розділі адміністрування."
              className="py-[var(--space-8)]"
            />
          )}

          {/* Search filtered everything out. */}
          {!isLoading &&
            !error &&
            items.length > 0 &&
            filtered.length === 0 && (
              <EmptyState
                icon={SearchX}
                title="Нічого не знайдено"
                hint="Уточніть запит — спробуйте назву або ЄДРПОУ."
                className="py-[var(--space-8)]"
              />
            )}

          {!isLoading && filtered.length > 0 && (
            <ul className="flex flex-col gap-1">
              {filtered.map((supplier) => (
                <li key={supplier.id}>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => onSelect(supplier)}
                    className={cn(
                      'flex min-h-[var(--touch-target-min)] w-full flex-col',
                      'items-start justify-center rounded-[var(--radius-md)]',
                      'px-[var(--space-3)] py-[var(--space-2)] text-left',
                      'hover:bg-[var(--color-surface-muted)]',
                      'focus-visible:outline-none disabled:opacity-50',
                    )}
                  >
                    <span className="font-[var(--font-weight-medium)] text-[color:var(--color-text)]">
                      {supplier.name}
                    </span>
                    {supplier.edrpou ? (
                      <span className="text-[length:var(--font-size-xs)] text-[color:var(--color-text-muted)]">
                        ЄДРПОУ {supplier.edrpou}
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
