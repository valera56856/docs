/**
 * SuppliersPage — pick the supplier whose invoice you're about to photograph.
 *
 * Loads active suppliers from `GET /api/suppliers/`. Selecting one navigates to
 * the camera, carrying the chosen supplier id so the new receipt is created
 * against it.
 *
 * States covered (mobile-first):
 * - loading  -> skeleton list (TODO)
 * - empty    -> guidance to add a supplier
 * - error    -> retry affordance
 * - list     -> large (>=44px) tappable rows
 */
import { useCallback, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, Store } from 'lucide-react';

import { api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { Button } from '@/components/ui/Button';
import type { Supplier } from '@/types';

/** Async data state for the supplier list. */
type LoadState = 'loading' | 'ready' | 'error';

/**
 * Render the supplier picker.
 *
 * @returns The suppliers page element.
 */
export function SuppliersPage(): JSX.Element {
  const navigate = useNavigate();
  const [state, setState] = useState<LoadState>('loading');
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  /** Fetch active suppliers; sets the load state accordingly. */
  const load = useCallback(async () => {
    setState('loading');
    try {
      const data = await api.get<Supplier[]>('/suppliers/');
      setSuppliers(data);
      setState('ready');
    } catch {
      setState('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * Begin a new receipt for the selected supplier by moving to the camera.
   * The supplier id rides along in router state.
   *
   * @param supplier - The chosen supplier.
   */
  function pick(supplier: Supplier): void {
    navigate('/receipt/new', { state: { supplierId: supplier.id } });
  }

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-[var(--space-4)] p-[var(--space-4)]">
      <h1 className="text-[var(--font-size-xl)]">Оберіть постачальника</h1>

      {/* TODO(ux): skeleton rows instead of plain text while loading. */}
      {state === 'loading' && (
        <p className="text-[var(--color-text-muted)]">Завантаження…</p>
      )}

      {state === 'error' && (
        <div className="flex flex-col items-start gap-[var(--space-3)]">
          <p role="alert" className="text-[var(--color-danger)]">
            Не вдалося завантажити постачальників.
          </p>
          <Button intent="secondary" onClick={() => void load()}>
            Спробувати ще раз
          </Button>
        </div>
      )}

      {state === 'ready' && suppliers.length === 0 && (
        <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-[var(--space-6)] text-center">
          <Store
            size={28}
            aria-hidden
            className="mx-auto text-[var(--color-text-muted)]"
          />
          <p className="mt-[var(--space-2)] text-[var(--color-text-muted)]">
            Немає активних постачальників. Додайте їх у розділі адміністрування.
          </p>
        </div>
      )}

      {state === 'ready' && suppliers.length > 0 && (
        <ul className="flex flex-col gap-2">
          {suppliers.map((supplier) => (
            <li key={supplier.id}>
              <button
                type="button"
                onClick={() => pick(supplier)}
                className={cn(
                  'flex min-h-[var(--touch-target-min)] w-full items-center',
                  'justify-between gap-[var(--space-3)] rounded-[var(--radius-md)]',
                  'border border-[var(--color-border)] bg-[var(--color-surface)]',
                  'px-[var(--space-4)] py-[var(--space-3)] text-left',
                  'hover:bg-[var(--color-surface-muted)]',
                )}
              >
                <span className="flex items-center gap-[var(--space-3)]">
                  <Store
                    size={20}
                    aria-hidden
                    className="text-[var(--color-blue)]"
                  />
                  <span className="font-[var(--font-weight-medium)]">
                    {supplier.name}
                  </span>
                </span>
                <ChevronRight
                  size={20}
                  aria-hidden
                  className="text-[var(--color-text-muted)]"
                />
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
