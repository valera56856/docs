/**
 * ProductPickerSheet — a reusable bottom-sheet for searching the SalesDrive
 * catalog and picking a single product.
 *
 * This is the generic sibling of {@link MappingSheet}: it owns the same
 * debounced product-search UX (cancel stale requests, explicit loading / empty /
 * error states, ≥44px result rows) but is *side-effect free* — instead of
 * calling the line-map endpoint, it simply hands the chosen {@link OurProduct}
 * back to the caller via `onSelect`. That lets the admin Mappings screen reuse
 * the exact catalog-search interaction for the "Перепривʼязати" (re-target)
 * action, where the persistence call is `mappings.update(...)` rather than
 * `lines.map(...)`. {@link MappingSheet} stays as-is for the receipt flow.
 *
 * Built on the kit {@link Sheet} (Radix Dialog) primitive, so we inherit a real
 * focus trap, Esc-to-dismiss, scroll-lock, the portal, and the slide-up
 * animation for free.
 */
import { useEffect, useRef, useState } from 'react';
import type { JSX, ReactNode } from 'react';
import { PackageSearch, SearchX } from 'lucide-react';

import { products as productsApi } from '@/lib/api';
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
import type { OurProduct } from '@/types';

/** Debounce window (ms) before firing a search — matches {@link MappingSheet}. */
const SEARCH_DEBOUNCE_MS = 250;

/** Props for {@link ProductPickerSheet}. */
export interface ProductPickerSheetProps {
  /** Whether the sheet is visible. */
  open: boolean;
  /** Visible sheet title (e.g. "Перепривʼязати товар"). */
  title?: string;
  /** Optional context line under the title (e.g. the supplier SKU being re-targeted). */
  description?: ReactNode;
  /**
   * True while the caller is persisting the selection (e.g. an in-flight
   * `mappings.update`). Disables the result rows so the user can't double-pick.
   */
  saving?: boolean;
  /**
   * Called when the operator picks a product. The caller performs the actual
   * persistence and decides when to close the sheet (so it can keep the sheet
   * open and show an error if the save fails).
   *
   * @param product - The chosen catalog product.
   */
  onSelect: (product: OurProduct) => void;
  /** Called to dismiss the sheet without selecting. */
  onClose: () => void;
}

/**
 * Catalog product-search bottom-sheet that returns the chosen product.
 *
 * @param props - {@link ProductPickerSheetProps}.
 * @returns The sheet element (the Radix portal renders nothing while closed).
 */
export function ProductPickerSheet({
  open,
  title = 'Обрати товар',
  description,
  saving = false,
  onSelect,
  onClose,
}: ProductPickerSheetProps): JSX.Element {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<OurProduct[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Bumped on every search to discard out-of-order responses. */
  const searchSeq = useRef(0);

  // Reset transient state whenever the sheet (re)opens.
  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setError(null);
    }
  }, [open]);

  // Debounced search: fires SEARCH_DEBOUNCE_MS after the last keystroke and
  // ignores any response that is not the latest request (seq guard).
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setIsSearching(false);
      return;
    }
    const seq = searchSeq.current + 1;
    searchSeq.current = seq;
    setIsSearching(true);
    setError(null);

    const handle = setTimeout(async () => {
      try {
        const found = await productsApi.search(q);
        if (seq === searchSeq.current) {
          setResults(found);
        }
      } catch {
        if (seq === searchSeq.current) {
          setError('Не вдалося знайти товари. Спробуйте ще раз.');
        }
      } finally {
        if (seq === searchSeq.current) {
          setIsSearching(false);
        }
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => clearTimeout(handle);
  }, [query]);

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
            label="Пошук у каталозі"
            labelHidden
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Пошук за артикулом або назвою…"
            inputMode="search"
            error={error ?? undefined}
          />

          {/* Skeleton rows while searching. */}
          {isSearching && (
            <ul className="flex flex-col gap-1" aria-hidden>
              {Array.from({ length: 4 }).map((_, i) => (
                <li key={i}>
                  <Skeleton height={48} className="w-full" />
                </li>
              ))}
            </ul>
          )}

          {/* Empty state after a search with no hits. */}
          {!isSearching && query.trim() && results.length === 0 && !error && (
            <EmptyState
              icon={SearchX}
              title="Нічого не знайдено"
              hint="Уточніть запит — спробуйте артикул або частину назви."
              className="py-[var(--space-8)]"
            />
          )}

          {/* Idle hint before the operator types anything. */}
          {!isSearching && !query.trim() && !error && (
            <EmptyState
              icon={PackageSearch}
              title="Почніть пошук"
              hint="Введіть артикул або назву товару з нашого каталогу."
              className="py-[var(--space-8)]"
            />
          )}

          {!isSearching && results.length > 0 && (
            <ul className="flex flex-col gap-1">
              {results.map((product) => (
                <li key={product.id}>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => onSelect(product)}
                    className={cn(
                      'flex min-h-[var(--touch-target-min)] w-full flex-col',
                      'items-start justify-center rounded-[var(--radius-md)]',
                      'px-[var(--space-3)] py-[var(--space-2)] text-left',
                      'hover:bg-[var(--color-surface-muted)]',
                      'focus-visible:outline-none disabled:opacity-50',
                    )}
                  >
                    <span className="font-[var(--font-weight-medium)] text-[color:var(--color-text)]">
                      {product.name}
                    </span>
                    <span className="text-[length:var(--font-size-xs)] text-[color:var(--color-text-muted)]">
                      {product.sku}
                    </span>
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
