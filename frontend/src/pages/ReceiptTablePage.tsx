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
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-[var(--space-4)] p-[var(--space-4)] md:max-w-screen-lg md:gap-[var(--space-6)] md:px-[var(--space-6)] md:py-[var(--space-8)] xl:max-w-screen-xl">
      <header className="flex items-center justify-between gap-2">
        <div className="flex flex-col gap-[var(--space-1)]">
          <h1 className="text-[length:var(--font-size-xl)] md:text-[length:var(--font-size-2xl)]">
            Позиції накладної
          </h1>
          <p className="hidden text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)] md:block">
            Перевірте розпізнані рядки, прив’яжіть товари та згенеруйте Excel.
          </p>
        </div>
        <div className="flex items-center gap-[var(--space-2)]">
          {receipt && <StatusBadge receipt={receipt.status} />}
          {/* AppShell supplies the toggle on desktop. */}
          <span className="lg:hidden">
            <ThemeToggle />
          </span>
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
        <>
          {/* MOBILE: stacked line cards (unchanged) — the polished phone view. */}
          <ul className="flex flex-col gap-[var(--space-3)] md:hidden">
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

          {/* DESKTOP (md+): a real table with aligned tabular numbers. The
              editable cells reuse {@link EditableField} (label hidden — the
              column header names it) and the mapped catalog SKU sits under the
              recognized name so the supplier→catalog link stays visible. */}
          <div className="hidden overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-sm)] md:block">
            <table className="w-full border-collapse text-left text-[length:var(--font-size-sm)]">
              <thead>
                <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] text-[length:var(--font-size-xs)] uppercase tracking-[0.03em] text-[color:var(--color-text-muted)]">
                  <th scope="col" className="px-[var(--space-4)] py-[var(--space-3)] font-[var(--font-weight-semibold)]">
                    Артикул постачальника
                  </th>
                  <th scope="col" className="px-[var(--space-4)] py-[var(--space-3)] font-[var(--font-weight-semibold)]">
                    Назва
                  </th>
                  <th scope="col" className="px-[var(--space-4)] py-[var(--space-3)] text-right font-[var(--font-weight-semibold)]">
                    К-ть
                  </th>
                  <th scope="col" className="px-[var(--space-4)] py-[var(--space-3)] text-right font-[var(--font-weight-semibold)]">
                    Ціна
                  </th>
                  <th scope="col" className="px-[var(--space-4)] py-[var(--space-3)] font-[var(--font-weight-semibold)]">
                    Статус
                  </th>
                  <th scope="col" className="px-[var(--space-4)] py-[var(--space-3)] text-right font-[var(--font-weight-semibold)]">
                    Дія
                  </th>
                </tr>
              </thead>
              <tbody>
                {receipt.lines.map((line) => (
                  <tr
                    key={line.id}
                    className="border-b border-[var(--color-border)] align-top transition-colors duration-150 last:border-b-0 hover:bg-[var(--color-surface-muted)]"
                  >
                    {/* Supplier SKU. */}
                    <td className="whitespace-nowrap px-[var(--space-4)] py-[var(--space-3)] font-[var(--font-weight-medium)] tabular-nums text-[color:var(--color-text)]">
                      {line.recognized_sku || '—'}
                    </td>

                    {/* Recognized name + the mapped catalog product beneath it. */}
                    <td className="px-[var(--space-4)] py-[var(--space-3)]">
                      <div className="max-w-[28rem]">
                        <p className="font-[var(--font-weight-medium)] text-[color:var(--color-text)]">
                          {line.recognized_name || '—'}
                        </p>
                        {line.matched_product && (
                          <p className="mt-[2px] flex items-baseline gap-[var(--space-1)] text-[length:var(--font-size-xs)] text-[color:var(--color-text-muted)]">
                            <span aria-hidden className="font-[var(--font-weight-semibold)] text-[color:var(--color-blue)]">
                              →
                            </span>
                            <span className="font-[var(--font-weight-semibold)] text-[color:var(--color-text)]">
                              {line.matched_product.sku}
                            </span>
                            <span className="truncate">{line.matched_product.name}</span>
                          </p>
                        )}
                      </div>
                    </td>

                    {/* Quantity (editable). */}
                    <td className="px-[var(--space-4)] py-[var(--space-3)] text-right">
                      <EditableField
                        label="Кількість"
                        labelHidden
                        value={line.quantity ?? ''}
                        inputMode="decimal"
                        className="ml-auto w-[6rem]"
                        onCommit={(v) => commitEdit(line, 'quantity', v)}
                      />
                    </td>

                    {/* Price (editable). */}
                    <td className="px-[var(--space-4)] py-[var(--space-3)] text-right">
                      <EditableField
                        label="Ціна"
                        labelHidden
                        value={line.price ?? ''}
                        placeholder="—"
                        inputMode="decimal"
                        className="ml-auto w-[6rem]"
                        onCommit={(v) => commitEdit(line, 'price', v)}
                      />
                    </td>

                    {/* Status badge. */}
                    <td className="px-[var(--space-4)] py-[var(--space-3)]">
                      <StatusBadge match={line.match_status} />
                    </td>

                    {/* Map / change action. */}
                    <td className="px-[var(--space-4)] py-[var(--space-3)] text-right">
                      <Button
                        intent={line.match_status === 'unmapped' ? 'primary' : 'secondary'}
                        size="sm"
                        onClick={() => setActiveLine(line)}
                      >
                        <Link2 size={16} aria-hidden />
                        {line.match_status === 'unmapped' ? 'Прив’язати' : 'Змінити'}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Proceed to Excel once the receipt is ready. Full-width on mobile;
          a right-aligned action well on desktop so it doesn't stretch across
          the wide table. */}
      {state === 'ready' && receipt && !isRecognizing && receipt.lines.length > 0 && (
        <div className="md:flex md:items-center md:justify-end md:gap-[var(--space-4)] md:border-t md:border-[var(--color-border)] md:pt-[var(--space-5)]">
          {!isReady && (
            <p className="hidden text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)] md:block">
              Прив’яжіть усі позиції, щоб згенерувати файл.
            </p>
          )}
          <Button
            size="lg"
            fullWidth
            disabled={!isReady}
            onClick={() => navigate(`/receipt/${receiptId}/generate`)}
            className="md:w-auto"
          >
            <FileSpreadsheet size={20} aria-hidden />
            {isReady ? 'Згенерувати Excel' : 'Спершу прив’яжіть усі позиції'}
          </Button>
        </div>
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
