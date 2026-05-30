/**
 * MappingSheet — bottom-sheet for mapping a recognized invoice line to one of
 * our SalesDrive catalog products.
 *
 * Flow (per the manifest "catalog search -> select -> autosave"):
 * 1. Operator opens the sheet for an unmapped (or to-be-corrected) line.
 * 2. They type into the search box; we query `GET /api/products/search/?q=`.
 * 3. Selecting a product calls
 *    `POST /api/receipts/{id}/lines/{lineId}/map/`, which both updates the line
 *    AND remembers the mapping (so the same supplier SKU auto-matches next time).
 * 4. The sheet reports the chosen product to the parent and closes.
 *
 * STUB STATUS: search + save are wired to the api/auth libs but intentionally
 * thin. Real debouncing, optimistic UI, and the full bottom-sheet animation /
 * focus-trap are left as TODOs (see inline comments).
 *
 * Accessibility: the sheet is a labelled dialog; the close affordance and every
 * result row are >=44px touch targets.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { JSX } from 'react';
import { Search, X } from 'lucide-react';

import { api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { Button } from '@/components/ui/Button';
import type { OurProduct } from '@/types';

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
 * @returns The sheet element, or `null` when closed.
 */
export function MappingSheet({
  open,
  receiptId,
  lineId,
  recognizedSku,
  recognizedName,
  onMapped,
  onClose,
}: MappingSheetProps): JSX.Element | null {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<OurProduct[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset transient state whenever the sheet (re)opens for a new line.
  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setError(null);
      // Focus the search box for fast keyboard entry.
      // TODO(a11y): add a full focus-trap while the sheet is open.
      inputRef.current?.focus();
    }
  }, [open, lineId]);

  /**
   * Search the catalog for products matching the current query.
   *
   * TODO(perf): debounce (~250ms) and cancel in-flight requests instead of
   * firing on every submit; show a skeleton list while searching.
   */
  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      return;
    }
    setIsSearching(true);
    setError(null);
    try {
      const found = await api.get<OurProduct[]>(
        `/products/search/?q=${encodeURIComponent(q)}`,
      );
      setResults(found);
    } catch {
      // TODO(ux): distinguish network vs auth errors and surface a retry.
      setError('Не вдалося знайти товари. Спробуйте ще раз.');
    } finally {
      setIsSearching(false);
    }
  }, [query]);

  /**
   * Map the line to the selected product. The backend persists the mapping
   * (manual) so subsequent recognitions auto-match this supplier SKU.
   *
   * @param product - The catalog product chosen by the operator.
   */
  const handleSelect = useCallback(
    async (product: OurProduct) => {
      setIsSaving(true);
      setError(null);
      try {
        await api.post(`/receipts/${receiptId}/lines/${lineId}/map/`, {
          our_product_id: product.id,
        });
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

  if (!open) {
    return null;
  }

  return (
    // TODO(motion): animate the backdrop + slide-up; respect reduced-motion.
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end"
      style={{ backgroundColor: 'rgba(10,26,63,0.4)' }}
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Прив’язати товар"
        className={cn(
          'flex max-h-[80dvh] flex-col rounded-t-[var(--radius-lg)]',
          'bg-[var(--color-surface)] shadow-[var(--shadow-lg)]',
        )}
        // Stop backdrop click from closing when interacting inside the sheet.
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header: context + close */}
        <header className="flex items-start justify-between gap-2 border-b border-[var(--color-border)] p-[var(--space-4)]">
          <div>
            <h2 className="text-[var(--font-size-lg)]">Прив’язати товар</h2>
            <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
              {recognizedSku}
              {recognizedName ? ` · ${recognizedName}` : ''}
            </p>
          </div>
          <Button
            intent="ghost"
            size="icon"
            aria-label="Закрити"
            onClick={onClose}
          >
            <X size={20} aria-hidden />
          </Button>
        </header>

        {/* Search row */}
        <form
          className="flex gap-2 p-[var(--space-4)]"
          onSubmit={(e) => {
            e.preventDefault();
            void runSearch();
          }}
        >
          <label className="sr-only" htmlFor="mapping-search">
            Пошук у каталозі
          </label>
          <input
            id="mapping-search"
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Пошук за артикулом або назвою…"
            className={cn(
              'min-h-[var(--touch-target-min)] flex-1 rounded-[var(--radius-md)]',
              'border border-[var(--color-border)] px-[var(--space-3)]',
            )}
          />
          <Button type="submit" size="icon" aria-label="Шукати">
            <Search size={20} aria-hidden />
          </Button>
        </form>

        {/* Results / states */}
        <div className="flex-1 overflow-y-auto px-[var(--space-4)] pb-[var(--space-6)]">
          {error && (
            <p
              role="alert"
              className="text-[var(--font-size-sm)] text-[var(--color-danger)]"
            >
              {error}
            </p>
          )}

          {/* TODO(ux): skeleton rows while `isSearching`. */}
          {isSearching && (
            <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
              Пошук…
            </p>
          )}

          {/* Empty state after a search with no hits. */}
          {!isSearching && query.trim() && results.length === 0 && !error && (
            <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
              Нічого не знайдено. Уточніть запит.
            </p>
          )}

          <ul className="flex flex-col gap-1">
            {results.map((product) => (
              <li key={product.id}>
                <button
                  type="button"
                  disabled={isSaving}
                  onClick={() => void handleSelect(product)}
                  className={cn(
                    'flex w-full flex-col items-start rounded-[var(--radius-md)]',
                    'px-[var(--space-3)] py-[var(--space-2)] text-left',
                    'hover:bg-[var(--color-surface-muted)] disabled:opacity-50',
                  )}
                >
                  <span className="font-[var(--font-weight-medium)]">
                    {product.name}
                  </span>
                  <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
                    {product.sku}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
