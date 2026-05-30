/**
 * ReceiptTablePage — the heart of the app.
 *
 * Shows the recognized invoice lines for a receipt and lets the operator:
 * - map an unmapped line to a catalog product (opens {@link MappingSheet}),
 * - edit quantity / price inline (PATCH the line on commit),
 * and, once the receipt is `ready`, proceed to Excel generation.
 *
 * Recognition runs asynchronously on the backend (Gemini via Celery), so while
 * the receipt is `recognizing` we poll every {@link POLL_MS} and show skeleton
 * rows. Editing or mapping a line refetches the receipt so its derived status
 * (needs_mapping ↔ ready) stays in lock-step with the server.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { FileSpreadsheet, Link2, RotateCcw } from 'lucide-react';

import { receipts as receiptsApi, lines as linesApi } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { Spinner } from '@/components/ui/Spinner';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ThemeToggle } from '@/components/ThemeProvider';
import { useToast } from '@/components/ui/Toast';
import { MappingSheet } from '@/components/MappingSheet';
import { EditableField } from '@/pages/_receipt/EditableField';
import type { LinePatch, OurProduct, Receipt, ReceiptLine } from '@/types';

/** Async state for the receipt screen. */
type LoadState = 'loading' | 'ready' | 'error';

/** Poll interval (ms) while the receipt is still being recognized. */
const POLL_MS = 2000;

/**
 * Render the recognized-lines table.
 *
 * @returns The receipt table page element.
 */
export function ReceiptTablePage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const receiptId = Number(id);
  const navigate = useNavigate();
  const { toast } = useToast();

  const [state, setState] = useState<LoadState>('loading');
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  /** The line currently being mapped (drives the bottom sheet). */
  const [activeLine, setActiveLine] = useState<ReceiptLine | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * Fetch the receipt with its lines + statuses.
   *
   * @param silent - When true, do not flip back to the loading state (used by
   *   the recognize poll and post-edit refreshes so the UI does not flicker).
   */
  const load = useCallback(
    async (silent = false) => {
      if (!Number.isFinite(receiptId)) {
        setState('error');
        return;
      }
      if (!silent) {
        setState('loading');
      }
      try {
        const data = await receiptsApi.get(receiptId);
        setReceipt(data);
        setState('ready');
      } catch {
        setState('error');
      }
    },
    [receiptId],
  );

  // Initial load.
  useEffect(() => {
    void load();
  }, [load]);

  // Poll while recognition is in progress; stop once it settles.
  useEffect(() => {
    if (receipt?.status === 'recognizing') {
      pollRef.current = setTimeout(() => void load(true), POLL_MS);
    }
    return () => {
      if (pollRef.current) {
        clearTimeout(pollRef.current);
      }
    };
  }, [receipt?.status, load]);

  /**
   * Commit an inline edit (quantity or price) for a line.
   *
   * Optimistically updates the field, PATCHes the server, then refetches so the
   * receipt's derived status reflects the change. On failure we refetch to undo
   * the optimistic write and toast the error.
   *
   * @param line - The line being edited.
   * @param field - Which numeric field changed.
   * @param value - The new value as a string (or empty to clear price).
   */
  const commitEdit = useCallback(
    async (
      line: ReceiptLine,
      field: 'quantity' | 'price',
      value: string,
    ): Promise<void> => {
      const trimmed = value.trim();
      // No-op if unchanged.
      if ((line[field] ?? '') === trimmed) {
        return;
      }
      // Price may be cleared (null); quantity is always a string. Build a typed
      // patch so the request shape matches the contract exactly.
      const patch: LinePatch =
        field === 'price'
          ? { price: trimmed === '' ? null : trimmed }
          : { quantity: trimmed };

      setReceipt((prev) =>
        prev
          ? {
              ...prev,
              lines: prev.lines.map((l) =>
                l.id === line.id ? { ...l, ...patch } : l,
              ),
            }
          : prev,
      );
      try {
        await linesApi.patch(receiptId, line.id, patch);
        // Re-pull so a status flip (e.g. clearing a required value) is reflected.
        await load(true);
      } catch {
        toast({
          variant: 'error',
          title: 'Не вдалося зберегти зміну',
          description: 'Перевірте формат числа та спробуйте ще раз.',
        });
        await load(true);
      }
    },
    [receiptId, load, toast],
  );

  /**
   * Apply the result of a successful map: update the line in place so the table
   * reflects the new product + status, then refetch so the receipt-level status
   * (ready vs needs_mapping) catches up.
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
                  ? {
                      ...line,
                      matched_product: product,
                      match_status: 'manual',
                    }
                  : line,
              ),
            }
          : prev,
      );
      void load(true);
    },
    [load],
  );

  const isRecognizing = receipt?.status === 'recognizing';
  const isReady = receipt?.status === 'ready' || receipt?.status === 'xlsx_ready';

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-[var(--space-4)] p-[var(--space-4)]">
      <header className="flex items-center justify-between gap-2">
        <h1 className="text-[length:var(--font-size-xl)]">Позиції накладної</h1>
        <div className="flex items-center gap-[var(--space-2)]">
          {receipt && <StatusBadge receipt={receipt.status} />}
          <ThemeToggle />
        </div>
      </header>

      {state === 'loading' && (
        <ul className="flex flex-col gap-2" aria-hidden>
          {Array.from({ length: 4 }).map((_, i) => (
            <li key={i}>
              <Skeleton height={96} className="w-full" />
            </li>
          ))}
        </ul>
      )}

      {state === 'error' && (
        <EmptyState
          icon={RotateCcw}
          title="Помилка завантаження"
          hint="Не вдалося завантажити накладну."
          action={
            <Button intent="secondary" onClick={() => void load()}>
              <RotateCcw size={18} aria-hidden /> Спробувати ще раз
            </Button>
          }
        />
      )}

      {state === 'ready' && isRecognizing && (
        <div className="flex flex-col gap-[var(--space-3)]">
          <p
            role="status"
            className="flex items-center gap-[var(--space-2)] text-[color:var(--color-text-muted)]"
          >
            <Spinner size={18} label={null} />
            Розпізнаємо накладну… Зачекайте кілька секунд.
          </p>
          <ul className="flex flex-col gap-2" aria-hidden>
            {Array.from({ length: 4 }).map((_, i) => (
              <li key={i}>
                <Skeleton height={96} className="w-full" />
              </li>
            ))}
          </ul>
        </div>
      )}

      {state === 'ready' &&
        receipt &&
        !isRecognizing &&
        receipt.lines.length === 0 && (
          <EmptyState
            icon={FileSpreadsheet}
            title="Жодної позиції"
            hint="Нічого не розпізнано. Перевірте якість фото та спробуйте знову."
            action={
              <Button
                intent="secondary"
                onClick={() => navigate(`/receipt/${receiptId}/camera`)}
              >
                Переробити фото
              </Button>
            }
          />
        )}

      {state === 'ready' && receipt && !isRecognizing && receipt.lines.length > 0 && (
        <ul className="flex flex-col gap-[var(--space-3)]">
          {receipt.lines.map((line) => (
            <Card
              as="li"
              variant="solid"
              key={line.id}
              className="flex flex-col gap-[var(--space-3)] p-[var(--space-4)]"
            >
              <div className="flex items-start justify-between gap-[var(--space-3)]">
                <div className="min-w-0">
                  <p className="truncate font-[var(--font-weight-semibold)] leading-[var(--line-height-snug)]">
                    {line.recognized_name || line.recognized_sku}
                  </p>
                  <p className="mt-[2px] text-[length:var(--font-size-xs)] text-[color:var(--color-text-muted)]">
                    Артикул: {line.recognized_sku || '—'}
                  </p>
                </div>
                <StatusBadge match={line.match_status} className="shrink-0" />
              </div>

              {/* Mapped product (target catalog item) — set off in a tinted
                  rail so the supplier→catalog link reads at a glance. */}
              {line.matched_product && (
                <p className="flex items-baseline gap-[var(--space-2)] rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--font-size-sm)]">
                  <span
                    aria-hidden
                    className="text-[color:var(--color-blue)] font-[var(--font-weight-semibold)]"
                  >
                    →
                  </span>
                  <span className="min-w-0">
                    <span className="font-[var(--font-weight-semibold)]">
                      {line.matched_product.sku}
                    </span>{' '}
                    <span className="text-[color:var(--color-text-muted)]">
                      {line.matched_product.name}
                    </span>
                  </span>
                </p>
              )}

              {/* Inline-editable quantity + price + the map action on one row,
                  so the controls read as a single, intentional toolbar. */}
              <div className="flex flex-wrap items-end justify-between gap-[var(--space-4)]">
                <div className="flex items-end gap-[var(--space-5)]">
                  <EditableField
                    label="Кількість"
                    value={line.quantity ?? ''}
                    inputMode="decimal"
                    onCommit={(v) => commitEdit(line, 'quantity', v)}
                  />
                  <EditableField
                    label="Ціна"
                    value={line.price ?? ''}
                    placeholder="—"
                    inputMode="decimal"
                    onCommit={(v) => commitEdit(line, 'price', v)}
                  />
                </div>

                <Button
                  intent={line.match_status === 'unmapped' ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => setActiveLine(line)}
                >
                  <Link2 size={16} aria-hidden />
                  {line.match_status === 'unmapped' ? 'Прив’язати' : 'Змінити'}
                </Button>
              </div>
            </Card>
          ))}
        </ul>
      )}

      {/* Proceed to Excel once the receipt is ready. */}
      {state === 'ready' && receipt && !isRecognizing && receipt.lines.length > 0 && (
        <Button
          size="lg"
          fullWidth
          disabled={!isReady}
          onClick={() => navigate(`/receipt/${receiptId}/generate`)}
        >
          <FileSpreadsheet size={20} aria-hidden />
          {isReady ? 'Згенерувати Excel' : 'Спершу прив’яжіть усі позиції'}
        </Button>
      )}

      {/* Mapping bottom-sheet for the active line. */}
      {activeLine && receipt && (
        <MappingSheet
          open={activeLine !== null}
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
