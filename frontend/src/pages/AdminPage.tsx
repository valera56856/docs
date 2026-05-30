/**
 * AdminPage — administrative console (admin role only).
 *
 * The kit's `useAuth` does not carry the user's product role, so this page
 * fetches `GET /api/auth/me/` on mount and redirects non-admins back to the
 * suppliers screen (role gating is *also* enforced server-side — this is a UX
 * convenience, not the security boundary). While the role check is in flight we
 * show a spinner.
 *
 * Sections:
 * - Catalog sync — `POST /api/sync/catalog/` (admin-only), result via toast.
 * - Suppliers — read-only list from `GET /api/suppliers/`.
 * - Recent mappings — `GET /api/mappings/` if available; degrades gracefully to
 *   a "coming soon" note when the endpoint is not present in the backend.
 */
import { useCallback, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate } from 'react-router-dom';
import { Link2, LogOut, RefreshCw, Store } from 'lucide-react';

import {
  ApiError,
  authApi,
  catalog as catalogApi,
  mappings as mappingsApi,
  suppliers as suppliersApi,
} from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Spinner } from '@/components/ui/Spinner';
import { ThemeToggle } from '@/components/ThemeProvider';
import { useToast } from '@/components/ui/Toast';
import type { ArticleMapping, Supplier } from '@/types';

/** Top-level gate state while we resolve the caller's role. */
type GateState = 'checking' | 'allowed' | 'denied';

/**
 * Render the admin console.
 *
 * @returns The admin page element.
 */
export function AdminPage(): JSX.Element {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { toast } = useToast();

  const [gate, setGate] = useState<GateState>('checking');
  const [isSyncing, setIsSyncing] = useState(false);
  const [supplierList, setSupplierList] = useState<Supplier[]>([]);
  const [mappingList, setMappingList] = useState<ArticleMapping[]>([]);
  /** Whether the mappings endpoint exists in this backend. */
  const [mappingsAvailable, setMappingsAvailable] = useState(true);

  // Resolve the role first; only load admin data once allowed.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await authApi.me();
        if (cancelled) return;
        if (me.role !== 'admin') {
          setGate('denied');
          return;
        }
        setGate('allowed');
      } catch {
        if (!cancelled) {
          setGate('denied');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Redirect denied users away (kept out of render to avoid a flash of content).
  useEffect(() => {
    if (gate === 'denied') {
      navigate('/suppliers', { replace: true });
    }
  }, [gate, navigate]);

  // Load the read-only sections once the admin is confirmed.
  useEffect(() => {
    if (gate !== 'allowed') return;
    let cancelled = false;
    (async () => {
      try {
        const list = await suppliersApi.list();
        if (!cancelled) setSupplierList(list);
      } catch {
        /* non-fatal: the section just stays empty */
      }
      try {
        const list = await mappingsApi.list();
        if (!cancelled) setMappingList(list);
      } catch (error) {
        // A 404 means the backend has no mappings list yet — degrade gracefully.
        if (!cancelled && error instanceof ApiError && error.status === 404) {
          setMappingsAvailable(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [gate]);

  /** Kick off a catalog sync; the actual work happens in a Celery task. */
  const triggerSync = useCallback(async () => {
    setIsSyncing(true);
    try {
      const result = await catalogApi.sync();
      toast({
        variant: 'success',
        title: 'Синхронізацію запущено',
        description: result.detail,
      });
    } catch (error) {
      const forbidden = error instanceof ApiError && error.status === 403;
      toast({
        variant: 'error',
        title: 'Не вдалося запустити синхронізацію',
        description: forbidden
          ? 'Бракує прав адміністратора.'
          : 'Спробуйте ще раз.',
      });
    } finally {
      setIsSyncing(false);
    }
  }, [toast]);

  if (gate !== 'allowed') {
    return (
      <div className="flex min-h-[60dvh] items-center justify-center">
        <Spinner size={32} label="Перевірка прав…" />
      </div>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-[var(--space-5)] p-[var(--space-4)]">
      <header className="flex items-center justify-between gap-2">
        <h1 className="text-[var(--font-size-xl)]">Адміністрування</h1>
        <ThemeToggle />
      </header>

      {/* Catalog sync */}
      <Card variant="solid" className="flex flex-col gap-[var(--space-3)]">
        <h2 className="flex items-center gap-2 text-[var(--font-size-lg)]">
          <RefreshCw size={20} aria-hidden className="text-[var(--color-blue)]" />
          Синхронізація каталогу
        </h2>
        <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
          Оновити кеш товарів із SalesDrive (YML). Виконується у фоні.
        </p>
        <Button fullWidth disabled={isSyncing} onClick={() => void triggerSync()}>
          {isSyncing ? (
            <>
              <Spinner size={18} label={null} /> Запуск…
            </>
          ) : (
            <>
              <RefreshCw size={18} aria-hidden /> Синхронізувати
            </>
          )}
        </Button>
      </Card>

      {/* Suppliers */}
      <section className="flex flex-col gap-[var(--space-2)]">
        <h2 className="flex items-center gap-2 text-[var(--font-size-lg)]">
          <Store size={20} aria-hidden className="text-[var(--color-blue)]" />
          Постачальники
        </h2>
        {supplierList.length === 0 ? (
          <EmptyState
            icon={Store}
            title="Немає постачальників"
            hint="Активні постачальники зʼявляться тут після додавання."
            className="py-[var(--space-6)]"
          />
        ) : (
          <ul className="flex flex-col gap-1">
            {supplierList.map((supplier) => (
              <Card
                as="li"
                variant="solid"
                key={supplier.id}
                className="flex items-center gap-[var(--space-2)] py-[var(--space-3)]"
              >
                <Store
                  size={16}
                  aria-hidden
                  className="shrink-0 text-[var(--color-text-muted)]"
                />
                <span className="font-[var(--font-weight-medium)]">
                  {supplier.name}
                </span>
              </Card>
            ))}
          </ul>
        )}
      </section>

      {/* Recent mappings */}
      <section className="flex flex-col gap-[var(--space-2)]">
        <h2 className="flex items-center gap-2 text-[var(--font-size-lg)]">
          <Link2 size={20} aria-hidden className="text-[var(--color-blue)]" />
          Останні відповідності
        </h2>
        {!mappingsAvailable ? (
          <EmptyState
            icon={Link2}
            title="Перегляд відповідностей — скоро"
            hint="Бекенд ще не надає список запамʼятованих відповідностей."
            className="py-[var(--space-6)]"
          />
        ) : mappingList.length === 0 ? (
          <EmptyState
            icon={Link2}
            title="Поки порожньо"
            hint="Тут зʼявляться запамʼятовані відповідності артикулів."
            className="py-[var(--space-6)]"
          />
        ) : (
          <ul className="flex flex-col gap-1">
            {mappingList.slice(0, 20).map((mapping) => (
              <Card
                as="li"
                variant="solid"
                key={mapping.id}
                className="flex flex-col gap-[2px] py-[var(--space-3)]"
              >
                <span className="text-[var(--font-size-sm)] font-[var(--font-weight-medium)]">
                  {mapping.supplier_sku}
                  {mapping.our_product ? ` → ${mapping.our_product.sku}` : ''}
                </span>
                <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
                  {mapping.our_product?.name ?? 'Без товару'} · використано{' '}
                  {mapping.times_used}×
                </span>
              </Card>
            ))}
          </ul>
        )}
      </section>

      <div className="mt-auto flex flex-col gap-2">
        <Button intent="secondary" onClick={() => navigate('/suppliers')}>
          До постачальників
        </Button>
        <Button intent="ghost" onClick={() => void logout()}>
          <LogOut size={18} aria-hidden /> Вийти
        </Button>
      </div>
    </main>
  );
}
