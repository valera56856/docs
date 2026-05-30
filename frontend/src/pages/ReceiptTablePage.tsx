/**
 * ReceiptTablePage — the heart of the app.
 *
 * Shows the recognized invoice lines for a receipt with their mapping status,
 * lets the operator:
 * - map an unmapped line to a catalog product (opens {@link MappingSheet}),
 * - edit quantity / price / SKU inline (PATCH the line),
 * and, once everything is ready, proceed to Excel generation.
 *
 * Recognition runs asynchronously on the backend (Gemini via Celery), so while
 * the receipt is `recognizing` we poll for completion.
 *
 * STUB STATUS: reads + map are wired; inline editing is sketched with a clear
 * TODO. Loading / empty / error states are all represented.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Pencil } from 'lucide-react';

import { api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { MappingSheet } from '@/components/MappingSheet';
import type { OurProduct, Receipt, ReceiptLine } from '@/types';

/** Async state for the receipt screen. */
type LoadState = 'loading' | 'ready' | 'error';

/** Poll interval (ms) while the receipt is still being recognized. */
const POLL_MS = 2500;

/**
 * Render the recognized-lines table.
 *
 * @returns The receipt table page element.
 */
export function ReceiptTablePage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [state, setState] = useState<LoadState>('loading');
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  /** The line currently being mapped (drives the bottom sheet). */
  const [activeLine, setActiveLine] = useState<ReceiptLine | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Fetch the receipt with its lines + statuses. */
  const load = useCallback(async () => {
    if (!id) return;
    try {
      const data = await api.get<Receipt>(`/receipts/${id}/`);
      setReceipt(data);
      setState('ready');
    } catch {
      setState('error');
    }
  }, [id]);

  // Initial load.
  useEffect(() => {
    void load();
  }, [load]);

  // Poll while recognition is in progress; stop once it settles.
  useEffect(() => {
    if (receipt?.status === 'recognizing') {
      pollRef.current = setTimeout(() => void load(), POLL_MS);
    }
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [receipt?.status, load]);

  /**
   * Apply the result of a successful map: update the line in place so the table
   * reflects the new product + status without a full refetch.
   *
   * @param lineId - The mapped line's id.
   * @param product - The catalog product it was mapped to.
   */
  const applyMapping = useCallback(
    (lineId: number, product: OurProduct) => {
      setReceipt((prev) =>
        prev
          ? {
              ...prev,
              lines: prev.lines.map((line) =>
                line.id === lineId
                  ? { ...line, matched_product: product, match_status: 'manual' }
                  : line,
              ),
            }
          : prev,
      );
    },
    [],
  );

  const allMapped =
    receipt?.lines.length !== 0 &&
    receipt?.lines.every((l) => l.match_status !== 'unmapped');

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-[var(--space-4)] p-[var(--space-4)]">
      <header className="flex items-center justify-between gap-2">
        <h1 className="text-[var(--font-size-xl)]">Позиції накладної</h1>
        {receipt && <StatusBadge receipt={receipt.status} />}
      </header>

      {/* TODO(ux): skeleton table rows while loading. */}
      {state === 'loading' && (
        <p className="text-[var(--color-text-muted)]">Завантаження…</p>
      )}

      {state === 'error' && (
        <div className="flex flex-col items-start gap-[var(--space-3)]">
          <p role="alert" className="text-[var(--color-danger)]">
            Не вдалося завантажити накладну.
          </p>
          <Button intent="secondary" onClick={() => void load()}>
            Спробувати ще раз
          </Button>
        </div>
      )}

      {state === 'ready' && receipt?.status === 'recognizing' && (
        <p className="text-[var(--color-text-muted)]">
          Розпізнаємо накладну… Зачекайте кілька секунд.
        </p>
      )}

      {state === 'ready' &&
        receipt &&
        receipt.status !== 'recognizing' &&
        receipt.lines.length === 0 && (
          <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-[var(--space-6)] text-center text-[var(--color-text-muted)]">
            Жодної позиції не розпізнано. Перевірте якість фото.
          </div>
        )}

      {state === 'ready' && receipt && receipt.lines.length > 0 && (
        <ul className="flex flex-col gap-2">
          {receipt.lines.map((line) => (
            <li
              key={line.id}
              className={cn(
                'flex flex-col gap-[var(--space-2)] rounded-[var(--radius-md)]',
                'border border-[var(--color-border)] bg-[var(--color-surface)]',
                'p-[var(--space-3)]',
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-[var(--font-weight-medium)]">
                    {line.recognized_name || line.recognized_sku}
                  </p>
                  <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
                    Артикул: {line.recognized_sku}
                  </p>
                </div>
                <StatusBadge match={line.match_status} />
              </div>

              {/* Mapped product (target catalog item). */}
              {line.matched_product && (
                <p className="text-[var(--font-size-sm)]">
                  →{' '}
                  <span className="font-[var(--font-weight-medium)]">
                    {line.matched_product.sku}
                  </span>{' '}
                  {line.matched_product.name}
                </p>
              )}

              <div className="flex items-center justify-between gap-2">
                {/* Quantity + price. TODO(edit): make these inline-editable
                    fields that PATCH /receipts/{id}/lines/{lineId}/. */}
                <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
                  К-сть: {line.quantity} · Ціна: {line.price ?? '—'}
                </p>
                <div className="flex gap-2">
                  <Button
                    intent="secondary"
                    size="sm"
                    onClick={() => setActiveLine(line)}
                  >
                    {line.match_status === 'unmapped'
                      ? 'Прив’язати'
                      : 'Змінити'}
                  </Button>
                  {/* TODO(edit): open an inline editor for qty/price/sku. */}
                  <Button
                    intent="ghost"
                    size="icon"
                    aria-label="Редагувати позицію"
                  >
                    <Pencil size={18} aria-hidden />
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Proceed to Excel once every line is mapped. */}
      {state === 'ready' && receipt && receipt.lines.length > 0 && (
        <Button
          size="lg"
          fullWidth
          disabled={!allMapped}
          onClick={() => navigate(`/receipt/${receipt.id}/generate`)}
        >
          {allMapped
            ? 'Далі: згенерувати Excel'
            : 'Спершу прив’яжіть усі позиції'}
        </Button>
      )}

      {/* Mapping bottom-sheet for the active line. */}
      {activeLine && receipt && (
        <MappingSheet
          open
          receiptId={receipt.id}
          lineId={activeLine.id}
          recognizedSku={activeLine.recognized_sku}
          recognizedName={activeLine.recognized_name}
          onMapped={(product) => applyMapping(activeLine.id, product)}
          onClose={() => setActiveLine(null)}
        />
      )}
    </main>
  );
}
