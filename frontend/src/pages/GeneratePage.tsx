/**
 * GeneratePage — produce and download the .xlsx receipt for manual import into
 * SalesDrive (Склад → Надходження → Імпорт).
 *
 * Calls `POST /api/receipts/{id}/generate-xlsx/`, which returns an `xlsx_url`.
 * We then offer a prominent download and a numbered, step-by-step reminder of
 * the manual import (there is no direct SalesDrive write API — see
 * docs/INTEGRATIONS.md). If the receipt was already generated (`xlsx_ready`),
 * we reuse its existing URL instead of regenerating on load.
 */
import { useCallback, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Download,
  FileSpreadsheet,
  Info,
  RotateCcw,
} from 'lucide-react';

import { receipts as receiptsApi } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { Spinner } from '@/components/ui/Spinner';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import type { Receipt } from '@/types';

/** Async state for the generate flow. */
type GenState = 'loading' | 'idle' | 'generating' | 'done' | 'error';

/** The numbered SalesDrive import steps, kept here so the copy lives in one place. */
const IMPORT_STEPS: readonly string[] = [
  'Завантажте згенерований .xlsx файл (кнопка вище).',
  'У SalesDrive відкрийте Склад → Надходження.',
  'Натисніть Імпорт і виберіть завантажений файл.',
  'Перевірте прев’ю: SKU, кількість і собівартість кожного рядка.',
  'Підтвердіть імпорт, щоб оприбуткувати надходження.',
];

/**
 * Render the Excel generation / download screen.
 *
 * @returns The generate page element.
 */
export function GeneratePage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const receiptId = Number(id);
  const navigate = useNavigate();
  const { toast } = useToast();

  const [state, setState] = useState<GenState>('loading');
  const [, setReceipt] = useState<Receipt | null>(null);
  const [receiptStatus, setReceiptStatus] = useState<Receipt['status'] | null>(
    null,
  );
  const [xlsxUrl, setXlsxUrl] = useState<string | null>(null);

  /** Load the receipt so we know its status and any existing xlsx_url. */
  const load = useCallback(async () => {
    if (!Number.isFinite(receiptId)) {
      setState('error');
      return;
    }
    setState('loading');
    try {
      const data = await receiptsApi.get(receiptId);
      setReceipt(data);
      setReceiptStatus(data.status);
      if (data.xlsx_url) {
        setXlsxUrl(data.xlsx_url);
        setState('done');
      } else {
        setState('idle');
      }
    } catch {
      setState('error');
    }
  }, [receiptId]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Trigger server-side Excel generation and capture the resulting URL. */
  const generate = useCallback(async () => {
    setState('generating');
    try {
      const result = await receiptsApi.generateXlsx(receiptId);
      setXlsxUrl(result.xlsx_url);
      setReceiptStatus(result.status);
      setState('done');
      toast({ variant: 'success', title: 'Excel-файл готовий' });
    } catch {
      setState('error');
      toast({
        variant: 'error',
        title: 'Не вдалося згенерувати Excel',
        description: 'Спробуйте ще раз.',
      });
    }
  }, [receiptId, toast]);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-[var(--space-5)] p-[var(--space-4)]">
      <header className="flex items-center gap-[var(--space-3)]">
        <FileSpreadsheet
          size={28}
          aria-hidden
          className="shrink-0 text-[color:var(--color-blue)]"
        />
        <div>
          <h1 className="text-[length:var(--font-size-xl)]">Excel-надходження</h1>
          {receiptStatus && <StatusBadge receipt={receiptStatus} />}
        </div>
      </header>

      {state === 'loading' && <Skeleton height={56} className="w-full" />}

      {state === 'error' && (
        <EmptyState
          icon={RotateCcw}
          title="Сталася помилка"
          hint="Не вдалося обробити запит."
          action={
            <Button intent="secondary" onClick={() => void load()}>
              <RotateCcw size={18} aria-hidden /> Оновити
            </Button>
          }
        />
      )}

      {(state === 'idle' || state === 'generating') && (
        <Button
          size="lg"
          fullWidth
          disabled={state === 'generating'}
          onClick={() => void generate()}
        >
          {state === 'generating' ? (
            <>
              <Spinner size={18} label={null} /> Генерація…
            </>
          ) : (
            <>
              <FileSpreadsheet size={20} aria-hidden /> Згенерувати Excel
            </>
          )}
        </Button>
      )}

      {state === 'done' && xlsxUrl && (
        <div className="flex flex-col gap-[var(--space-4)]">
          <Button asChild size="lg" fullWidth>
            {/* `download` hints the browser to save rather than navigate. */}
            <a href={xlsxUrl} download>
              <Download size={20} aria-hidden /> Завантажити .xlsx
            </a>
          </Button>

          {/* Numbered manual-import instructions — there is no SalesDrive API. */}
          <Card variant="solid" className="flex flex-col gap-[var(--space-3)]">
            <h2 className="flex items-center gap-[var(--space-2)] text-[length:var(--font-size-base)] font-[var(--font-weight-semibold)]">
              <Info size={18} aria-hidden className="text-[color:var(--color-info)]" />
              Імпорт у SalesDrive
            </h2>
            <ol className="flex list-none flex-col gap-[var(--space-2)]">
              {IMPORT_STEPS.map((step, index) => (
                <li
                  key={step}
                  className="flex items-start gap-[var(--space-2)] text-[length:var(--font-size-sm)]"
                >
                  <span
                    aria-hidden
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-full)] bg-[var(--color-info-bg)] text-[length:var(--font-size-xs)] font-[var(--font-weight-semibold)] text-[color:var(--color-info)]"
                  >
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      )}

      <Button
        intent="ghost"
        className="mt-auto"
        onClick={() => navigate(`/receipt/${receiptId}`)}
      >
        <ArrowLeft size={18} aria-hidden /> Назад до позицій
      </Button>
    </main>
  );
}
