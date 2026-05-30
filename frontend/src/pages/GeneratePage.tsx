/**
 * GeneratePage — produce and download the .xlsx receipt for manual import into
 * SalesDrive (Склад -> Надходження -> Імпорт).
 *
 * Calls `POST /api/receipts/{id}/generate-xlsx/`, which returns an `xlsx_url`.
 * We then offer a prominent download and remind the operator of the manual
 * import step (there is no direct SalesDrive API — see docs/INTEGRATIONS.md).
 *
 * STUB STATUS: generate + download wired to the api lib; reuses the receipt's
 * existing `xlsx_url` if the file was already generated (status `xlsx_ready`).
 */
import { useCallback, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Download, FileSpreadsheet, Info } from 'lucide-react';

import { api } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import type { Receipt } from '@/types';

/** Async state for the generate flow. */
type GenState = 'loading' | 'idle' | 'generating' | 'done' | 'error';

/**
 * Render the Excel generation / download screen.
 *
 * @returns The generate page element.
 */
export function GeneratePage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [state, setState] = useState<GenState>('loading');
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [xlsxUrl, setXlsxUrl] = useState<string | null>(null);

  /** Load the receipt so we know its status and any existing xlsx_url. */
  const load = useCallback(async () => {
    if (!id) return;
    setState('loading');
    try {
      const data = await api.get<Receipt>(`/receipts/${id}/`);
      setReceipt(data);
      if (data.xlsx_url) {
        setXlsxUrl(data.xlsx_url);
        setState('done');
      } else {
        setState('idle');
      }
    } catch {
      setState('error');
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Trigger server-side Excel generation and capture the resulting URL. */
  const generate = useCallback(async () => {
    if (!id) return;
    setState('generating');
    try {
      const { xlsx_url } = await api.post<{ xlsx_url: string }>(
        `/receipts/${id}/generate-xlsx/`,
      );
      setXlsxUrl(xlsx_url);
      setState('done');
    } catch {
      setState('error');
    }
  }, [id]);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-[var(--space-5)] p-[var(--space-4)]">
      <header className="flex items-center gap-[var(--space-3)]">
        <FileSpreadsheet
          size={28}
          aria-hidden
          className="text-[var(--color-blue)]"
        />
        <div>
          <h1 className="text-[var(--font-size-xl)]">Excel-надходження</h1>
          {receipt && <StatusBadge receipt={receipt.status} />}
        </div>
      </header>

      {state === 'loading' && (
        <p className="text-[var(--color-text-muted)]">Завантаження…</p>
      )}

      {state === 'error' && (
        <div className="flex flex-col items-start gap-[var(--space-3)]">
          <p role="alert" className="text-[var(--color-danger)]">
            Сталася помилка. Спробуйте ще раз.
          </p>
          <Button intent="secondary" onClick={() => void load()}>
            Оновити
          </Button>
        </div>
      )}

      {(state === 'idle' || state === 'generating') && (
        <Button
          size="lg"
          fullWidth
          disabled={state === 'generating'}
          onClick={() => void generate()}
        >
          {state === 'generating' ? 'Генерація…' : 'Згенерувати Excel'}
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

          {/* Manual import reminder — there is no direct SalesDrive API. */}
          <aside className="flex gap-[var(--space-2)] rounded-[var(--radius-md)] bg-[var(--color-info-bg)] p-[var(--space-3)]">
            <Info
              size={18}
              aria-hidden
              className="mt-[2px] shrink-0 text-[var(--color-info)]"
            />
            <p className="text-[var(--font-size-sm)]">
              Імпортуйте файл у SalesDrive вручну:{' '}
              <strong>Склад → Надходження → Імпорт</strong>. Перевірте
              кількість і собівартість перед підтвердженням.
            </p>
          </aside>
        </div>
      )}

      <Button
        intent="ghost"
        onClick={() => navigate(`/receipt/${id}`)}
      >
        ← Назад до позицій
      </Button>
    </main>
  );
}
