/**
 * SuppliersPage — pick the supplier whose invoice you're about to photograph.
 *
 * Loads active suppliers from `GET /api/suppliers/`. Tapping one creates a draft
 * receipt (`POST /api/receipts/`) and navigates to that receipt's camera screen,
 * carrying the new receipt id in the URL.
 *
 * States covered (mobile-first, all via the kit):
 * - loading  -> {@link Skeleton} row placeholders
 * - empty    -> {@link EmptyState} guiding the operator to admin
 * - error    -> {@link EmptyState} with a retry action + an error {@link useToast}
 * - list     -> large (>=44px) tappable {@link Card} rows
 */
import { useCallback, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, RotateCcw, Settings, Store } from 'lucide-react';

import {
  authApi,
  suppliers as suppliersApi,
  receipts as receiptsApi,
} from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { ThemeToggle } from '@/components/ThemeProvider';
import { useToast } from '@/components/ui/Toast';
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
  const { toast } = useToast();
  const [state, setState] = useState<LoadState>('loading');
  const [items, setItems] = useState<Supplier[]>([]);
  /** Id of the supplier whose receipt is being created (disables that row). */
  const [creatingId, setCreatingId] = useState<number | null>(null);
  /**
   * Whether the current user is an admin — gates the «Налаштування» gear in the
   * header. A best-effort `me()` check; on failure we simply hide the gear (the
   * /admin route enforces the real role boundary server-side anyway).
   */
  const [isAdmin, setIsAdmin] = useState(false);

  // Resolve the role once for the settings affordance (non-fatal on failure).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await authApi.me();
        if (!cancelled) setIsAdmin(me.role === 'admin');
      } catch {
        /* non-fatal: gear stays hidden */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** Fetch active suppliers; sets the load state accordingly. */
  const load = useCallback(async () => {
    setState('loading');
    try {
      const data = await suppliersApi.list();
      setItems(data);
      setState('ready');
    } catch {
      setState('error');
      toast({
        variant: 'error',
        title: 'Не вдалося завантажити постачальників',
        description: 'Перевірте зʼєднання та спробуйте ще раз.',
      });
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * Begin a new receipt for the selected supplier: create the draft, then move
   * to its camera screen. The receipt id lives in the URL from here on.
   *
   * @param supplier - The chosen supplier.
   */
  const pick = useCallback(
    async (supplier: Supplier) => {
      setCreatingId(supplier.id);
      try {
        const receipt = await receiptsApi.create(supplier.id);
        navigate(`/receipt/${receipt.id}/camera`);
      } catch {
        toast({
          variant: 'error',
          title: 'Не вдалося створити накладну',
          description: 'Спробуйте обрати постачальника ще раз.',
        });
        setCreatingId(null);
      }
    },
    [navigate, toast],
  );

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-[var(--space-4)] p-[var(--space-4)] md:max-w-screen-lg md:gap-[var(--space-6)] md:px-[var(--space-6)] md:py-[var(--space-8)] xl:max-w-screen-xl">
      <header className="flex items-center justify-between gap-2">
        <div className="flex flex-col gap-[var(--space-1)]">
          <h1 className="text-[length:var(--font-size-xl)] md:text-[length:var(--font-size-2xl)]">
            Оберіть постачальника
          </h1>
          {/* On desktop a one-line subtitle gives the wider header purpose. */}
          <p className="hidden text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)] md:block">
            Виберіть постачальника, щоб почати нову накладну.
          </p>
        </div>
        {/* The per-screen controls duplicate the desktop top bar, so hide them
            on lg+ (where AppShell supplies them) but keep them on mobile. */}
        <div className="flex items-center gap-1 lg:hidden">
          {isAdmin && (
            <Button
              intent="ghost"
              size="icon"
              aria-label="Налаштування"
              title="Налаштування"
              onClick={() => navigate('/admin')}
            >
              <Settings size={20} aria-hidden />
            </Button>
          )}
          <ThemeToggle />
        </div>
      </header>

      {state === 'loading' && (
        <ul
          className="grid grid-cols-1 gap-2 md:grid-cols-2 md:gap-[var(--space-4)] xl:grid-cols-3"
          aria-hidden
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <li key={i}>
              <Skeleton height={72} className="w-full" />
            </li>
          ))}
        </ul>
      )}

      {state === 'error' && (
        <EmptyState
          icon={RotateCcw}
          title="Помилка завантаження"
          hint="Не вдалося отримати список постачальників."
          action={
            <Button intent="secondary" onClick={() => void load()}>
              <RotateCcw size={18} aria-hidden /> Спробувати ще раз
            </Button>
          }
        />
      )}

      {state === 'ready' && items.length === 0 && (
        <EmptyState
          icon={Store}
          title="Немає постачальників"
          hint="Додайте активних постачальників у розділі адміністрування."
        />
      )}

      {state === 'ready' && items.length > 0 && (
        <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 md:gap-[var(--space-4)] xl:grid-cols-3">
          {items.map((supplier) => (
            <li key={supplier.id}>
              <Card
                as="button"
                interactive
                disabled={creatingId !== null}
                onClick={() => void pick(supplier)}
                aria-busy={creatingId === supplier.id}
                className="flex h-full min-h-[var(--touch-target-min)] items-center justify-between gap-[var(--space-3)] md:min-h-[88px] md:p-[var(--space-5)]"
              >
                <span className="flex items-center gap-[var(--space-3)]">
                  <span
                    aria-hidden
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-info-bg)] text-[color:var(--color-blue)] md:h-11 md:w-11"
                  >
                    <Store size={20} aria-hidden />
                  </span>
                  <span className="font-[var(--font-weight-medium)] md:text-[length:var(--font-size-lg)]">
                    {supplier.name}
                  </span>
                </span>
                <ChevronRight
                  size={20}
                  aria-hidden
                  className="shrink-0 text-[color:var(--color-text-muted)]"
                />
              </Card>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
