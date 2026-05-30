/**
 * MappingSheet — bottom-sheet for mapping a recognized invoice line to one of
 * our SalesDrive catalog products.
 *
 * Flow (per the manifest "catalog search → select → autosave"):
 * 1. The operator opens the sheet for an unmapped (or to-be-corrected) line.
 * 2. They type into the search box; we debounce and query
 *    `products.search(q)` (`GET /api/products/search/?q=`), cancelling stale
 *    in-flight requests so the last keystroke wins.
 * 3. Selecting a product calls `lines.map(...)`
 *    (`POST /api/receipts/{id}/lines/{lineId}/map/`), which both updates the
 *    line AND remembers the mapping (so the same supplier SKU auto-matches next
 *    time). We optimistically report the choice to the parent and close.
 *
 * Built on the kit {@link Sheet} (Radix Dialog) primitive, so we inherit a real
 * focus trap, Esc-to-dismiss, scroll-lock, the portal, and slide-up animation
 * for free; this component only owns the search + select logic and the result
 * list rendering.
 *
 * Accessibility: every result row is a ≥44px tap target; loading / empty / error
 * states are explicit (never blank); failures surface an inline alert.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { JSX } from 'react';
import { PackageSearch, SearchX } from 'lucide-react';

import { products as productsApi, lines as linesApi } from '@/lib/api';
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

/** Debounce window (ms) before firing a search — long enough to skip per-key
 * requests, short enough to feel instant on a phone keypad. */
const SEARCH_DEBOUNCE_MS = 250;

/** Props for {@link MappingSheet}. */
export interface MappingSheetProps {
  /** Whether the sheet is visible. */
  open: boolean;
  /** Receipt id (path param for the map endpoint). */
  receiptId: number;
  /** Line id being mapped (path param for the map endpoint). */
  lineId: number;
  /** The recognized supplier SKU, shown for operator context. */
  recognizedSku: string;
  /** The recognized product name, shown for operator context. */
  recognizedName?: string;
  /** Called after a successful map with the chosen product. */
  onMapped: (product: OurProduct) => void;
  /** Called to dismiss the sheet without mapping. */
  onClose: () => void;
}

/**
 * Bottom-sheet mapping control.
 *
 * @param props - {@link MappingSheetProps}.
 * @returns The sheet element (the Radix portal renders nothing while closed).
 */
export function MappingSheet({
  open,
  receiptId,
  lineId,
  recognizedSku,
  recognizedName,
  onMapped,
  onClose,
}: MappingSheetProps): JSX.Element {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<OurProduct[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Bumped on every search to discard out-of-order responses. */
  const searchSeq = useRef(0);

  // Reset transient state whenever the sheet (re)opens for a new line.
  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setError(null);
    }
  }, [open, lineId]);

  // Debounced search effect: fires SEARCH_DEBOUNCE_MS after the last keystroke,
  // and ignores any response that is not the latest request (seq guard).
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

  /**
   * Map the line to the selected product. The backend persists the mapping
   * (manual) so subsequent recognitions auto-match this supplier SKU. We report
   * the choice optimistically and close as soon as the request succeeds.
   *
   * @param product - The catalog product chosen by the operator.
   */
  const handleSelect = useCallback(
    async (product: OurProduct) => {
      setIsSaving(true);
      setError(null);
      try {
        await linesApi.map(receiptId, lineId, product.id);
        onMapped(product);
        onClose();
      } catch {
        setError('Не вдалося зберегти відповідність.');
      } finally {
        setIsSaving(false);
      }
    },
    [receiptId, lineId, onMapped, onClose],
  );

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
    >
      <SheetContent ariaLabel="Прив’язати товар">
        <SheetHeader>
          <SheetTitle>Прив’язати товар</SheetTitle>
          <SheetDescription>
            {recognizedSku}
            {recognizedName ? ` · ${recognizedName}` : ''}
          </SheetDescription>
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
                    disabled={isSaving}
                    onClick={() => void handleSelect(product)}
                    className={cn(
                      'flex min-h-[var(--touch-target-min)] w-full flex-col',
                      'items-start justify-center rounded-[var(--radius-md)]',
                      'px-[var(--space-3)] py-[var(--space-2)] text-left',
                      'hover:bg-[var(--color-surface-muted)]',
                      'focus-visible:outline-none disabled:opacity-50',
                    )}
                  >
                    <span className="font-[var(--font-weight-medium)] text-[var(--color-text)]">
                      {product.name}
                    </span>
                    <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
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
