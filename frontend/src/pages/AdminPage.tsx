/**
 * AdminPage — the «Налаштування» (Settings) hub (admin role only).
 *
 * The kit's `useAuth` does not carry the user's product role, so this page
 * fetches `GET /api/auth/me/` on mount and redirects non-admins back to the
 * suppliers screen (role gating is *also* enforced server-side — this is a UX
 * convenience, not the security boundary). While the role check is in flight we
 * show a spinner.
 *
 * Three sections, each a {@link Card}:
 *  1) SalesDrive — the DB-configurable YML URL (`GET/PUT /api/settings/salesdrive/`),
 *     a non-throwing "test connection" probe (`POST .../test/`), the existing
 *     catalog sync trigger, and a status line (last sync + cached product count).
 *  2) Постачальники — full CRUD over `GET/POST/PATCH/DELETE /api/suppliers/` via a
 *     {@link SupplierFormSheet}; delete degrades to "deactivate" on a 409.
 *  3) Маппінги — searchable/filterable list (`GET /api/mappings/`) with re-target
 *     (via {@link ProductPickerSheet} + `PATCH`) and delete.
 *
 * Each section owns its own load/empty/error/skeleton states and surfaces every
 * mutation through a Toast, so the screen is never blank and never silent.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  Link2,
  LogOut,
  Pencil,
  Plug,
  Plus,
  PowerOff,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  Store,
  Trash2,
} from 'lucide-react';

import {
  ApiError,
  authApi,
  catalog as catalogApi,
  mappings as mappingsApi,
  settings as settingsApi,
  suppliers as suppliersApi,
} from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { Skeleton } from '@/components/ui/Skeleton';
import { Spinner } from '@/components/ui/Spinner';
import { ThemeToggle } from '@/components/ThemeProvider';
import { useToast } from '@/components/ui/Toast';
import { SupplierFormSheet } from '@/components/SupplierFormSheet';
import { ProductPickerSheet } from '@/components/ProductPickerSheet';
import type {
  MappingAdmin,
  OurProduct,
  SalesDriveSettings,
  Supplier,
  SupplierInput,
} from '@/types';

/** Top-level gate state while we resolve the caller's role. */
type GateState = 'checking' | 'allowed' | 'denied';

/** Generic async load state used by the suppliers + mappings sections. */
type LoadState = 'loading' | 'ready' | 'error';

/** Debounce window (ms) for the mappings search box. */
const SEARCH_DEBOUNCE_MS = 300;

/**
 * Format an ISO timestamp for the status line, or an em-dash when null.
 *
 * @param iso - ISO timestamp string, or null when no sync has ever run.
 * @returns A localized date-time string, or "—".
 */
function formatSyncedAt(iso: string | null): string {
  if (!iso) {
    return '—';
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('uk-UA');
}

/**
 * Render the settings hub.
 *
 * @returns The settings page element.
 */
export function AdminPage(): JSX.Element {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { toast } = useToast();

  const [gate, setGate] = useState<GateState>('checking');

  // Resolve the role first; only load admin data once allowed.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await authApi.me();
        if (cancelled) return;
        setGate(me.role === 'admin' ? 'allowed' : 'denied');
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
        <h1 className="flex items-center gap-2 text-[var(--font-size-xl)]">
          <Settings size={22} aria-hidden className="text-[var(--color-blue)]" />
          Налаштування
        </h1>
        <ThemeToggle />
      </header>

      <SalesDriveSection toast={toast} />
      <SuppliersSection toast={toast} />
      <MappingsSection toast={toast} />

      <div className="mt-[var(--space-2)] flex flex-col gap-2">
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

/** The `toast` function type shared by the section components. */
type ToastFn = ReturnType<typeof useToast>['toast'];

/**
 * Section 1 — SalesDrive integration: configure the YML URL, test the
 * connection without persisting, run a sync, and show the cache status line.
 *
 * @param props.toast - The shared toast dispatcher.
 * @returns The SalesDrive settings card.
 */
function SalesDriveSection({ toast }: { toast: ToastFn }): JSX.Element {
  const [state, setState] = useState<LoadState>('loading');
  const [data, setData] = useState<SalesDriveSettings | null>(null);
  const [url, setUrl] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const result = await settingsApi.getSalesDrive();
      setData(result);
      setUrl(result.salesdrive_yml_url);
      setState('ready');
    } catch {
      setState('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** Persist the edited YML URL; refresh the status line from the response. */
  const save = useCallback(async () => {
    setIsSaving(true);
    try {
      const result = await settingsApi.saveSalesDrive(url.trim());
      setData(result);
      setUrl(result.salesdrive_yml_url);
      toast({ variant: 'success', title: 'Збережено' });
    } catch (error) {
      const forbidden = error instanceof ApiError && error.status === 403;
      toast({
        variant: 'error',
        title: 'Не вдалося зберегти',
        description: forbidden
          ? 'Бракує прав адміністратора.'
          : 'Перевірте адресу та спробуйте ще раз.',
      });
    } finally {
      setIsSaving(false);
    }
  }, [url, toast]);

  /** Probe the (edited) URL without saving; the endpoint never throws on a bad URL. */
  const test = useCallback(async () => {
    setIsTesting(true);
    try {
      const result = await settingsApi.testSalesDrive(url.trim() || undefined);
      if (result.ok) {
        toast({
          variant: 'success',
          title: 'Підключення успішне',
          description: `${result.product_count ?? 0} товарів у YML.`,
        });
      } else {
        toast({
          variant: 'error',
          title: 'Підключення не вдалося',
          description: result.error ?? 'Невідома помилка.',
        });
      }
    } catch {
      toast({
        variant: 'error',
        title: 'Підключення не вдалося',
        description: 'Спробуйте ще раз.',
      });
    } finally {
      setIsTesting(false);
    }
  }, [url, toast]);

  /** Enqueue a catalog sync; the heavy work happens in a Celery task. */
  const sync = useCallback(async () => {
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
        description: forbidden ? 'Бракує прав адміністратора.' : 'Спробуйте ще раз.',
      });
    } finally {
      setIsSyncing(false);
    }
  }, [toast]);

  const busy = isSaving || isTesting || isSyncing;

  return (
    <Card variant="solid" className="flex flex-col gap-[var(--space-3)]">
      <h2 className="flex items-center gap-2 text-[var(--font-size-lg)]">
        <Plug size={20} aria-hidden className="text-[var(--color-blue)]" />
        SalesDrive
      </h2>

      {state === 'loading' ? (
        <div className="flex flex-col gap-[var(--space-2)]">
          <Skeleton height={44} className="w-full" />
          <Skeleton height={20} width="60%" />
        </div>
      ) : state === 'error' ? (
        <EmptyState
          icon={RotateCcw}
          title="Не вдалося завантажити"
          hint="Перевірте зʼєднання."
          className="py-[var(--space-6)]"
          action={
            <Button intent="secondary" onClick={() => void load()}>
              <RotateCcw size={18} aria-hidden /> Ще раз
            </Button>
          }
        />
      ) : (
        <>
          <Input
            label="YML-адреса каталогу"
            type="url"
            inputMode="url"
            value={url}
            disabled={busy}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…/export.yml"
            hint="Джерело каталогу для синхронізації. Якщо порожньо — береться зі змінної середовища."
          />

          <div className="flex flex-col gap-[var(--space-2)]">
            <Button fullWidth disabled={busy} onClick={() => void save()}>
              {isSaving ? (
                <>
                  <Spinner size={18} label={null} /> Збереження…
                </>
              ) : (
                'Зберегти'
              )}
            </Button>
            <div className="flex gap-[var(--space-2)]">
              <Button
                intent="secondary"
                fullWidth
                disabled={busy}
                onClick={() => void test()}
              >
                {isTesting ? (
                  <Spinner size={18} label={null} />
                ) : (
                  <>
                    <Plug size={18} aria-hidden /> Перевірити
                  </>
                )}
              </Button>
              <Button
                intent="secondary"
                fullWidth
                disabled={busy}
                onClick={() => void sync()}
              >
                {isSyncing ? (
                  <Spinner size={18} label={null} />
                ) : (
                  <>
                    <RefreshCw size={18} aria-hidden /> Синхронізувати
                  </>
                )}
              </Button>
            </div>
          </div>

          <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
            Останній синк: {formatSyncedAt(data?.last_synced ?? null)} · у кеші{' '}
            {data?.product_count ?? 0} товарів
          </p>
        </>
      )}
    </Card>
  );
}

/**
 * Section 2 — Suppliers CRUD. Lists every supplier (active + inactive), opens a
 * {@link SupplierFormSheet} for add/edit, and supports deactivate + delete
 * (delete degrades to a "deactivate instead" hint on a 409 ProtectedError).
 *
 * @param props.toast - The shared toast dispatcher.
 * @returns The suppliers management card.
 */
function SuppliersSection({ toast }: { toast: ToastFn }): JSX.Element {
  const [state, setState] = useState<LoadState>('loading');
  const [items, setItems] = useState<Supplier[]>([]);
  const [sheetOpen, setSheetOpen] = useState(false);
  /** The supplier being edited, or null when adding. */
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  /** Id of the row whose deactivate/delete is in flight (disables that row). */
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const data = await suppliersApi.list({ includeInactive: true });
      setItems(data);
      setState('ready');
    } catch {
      setState('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openAdd = useCallback(() => {
    setEditing(null);
    setSheetOpen(true);
  }, []);

  const openEdit = useCallback((supplier: Supplier) => {
    setEditing(supplier);
    setSheetOpen(true);
  }, []);

  /** Create or update from the form sheet, then refresh the list. */
  const submit = useCallback(
    async (data: SupplierInput) => {
      setIsSaving(true);
      try {
        if (editing) {
          await suppliersApi.update(editing.id, data);
          toast({ variant: 'success', title: 'Оновлено' });
        } else {
          await suppliersApi.create(data);
          toast({ variant: 'success', title: 'Додано' });
        }
        setSheetOpen(false);
        setEditing(null);
        await load();
      } catch (error) {
        const forbidden = error instanceof ApiError && error.status === 403;
        toast({
          variant: 'error',
          title: 'Не вдалося зберегти',
          description: forbidden ? 'Бракує прав адміністратора.' : 'Спробуйте ще раз.',
        });
      } finally {
        setIsSaving(false);
      }
    },
    [editing, load, toast],
  );

  /** Soft-disable a supplier (keeps history intact). */
  const deactivate = useCallback(
    async (supplier: Supplier) => {
      setBusyId(supplier.id);
      try {
        await suppliersApi.update(supplier.id, { is_active: false });
        toast({ variant: 'success', title: 'Деактивовано' });
        await load();
      } catch {
        toast({ variant: 'error', title: 'Не вдалося деактивувати' });
      } finally {
        setBusyId(null);
      }
    },
    [load, toast],
  );

  /** Hard-delete a supplier; degrade to a deactivate hint on a 409. */
  const remove = useCallback(
    async (supplier: Supplier) => {
      setBusyId(supplier.id);
      try {
        await suppliersApi.remove(supplier.id);
        toast({ variant: 'success', title: 'Видалено' });
        await load();
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          toast({
            variant: 'warning',
            title: 'Має повʼязані накладні',
            description: 'Деактивуйте замість видалення.',
          });
        } else {
          toast({ variant: 'error', title: 'Не вдалося видалити' });
        }
      } finally {
        setBusyId(null);
      }
    },
    [load, toast],
  );

  return (
    <section className="flex flex-col gap-[var(--space-2)]">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-[var(--font-size-lg)]">
          <Store size={20} aria-hidden className="text-[var(--color-blue)]" />
          Постачальники
        </h2>
        <Button size="sm" disabled={state === 'loading'} onClick={openAdd}>
          <Plus size={16} aria-hidden /> Додати
        </Button>
      </div>

      {state === 'loading' && (
        <ul className="flex flex-col gap-1" aria-hidden>
          {Array.from({ length: 3 }).map((_, i) => (
            <li key={i}>
              <Skeleton height={64} className="w-full" />
            </li>
          ))}
        </ul>
      )}

      {state === 'error' && (
        <EmptyState
          icon={RotateCcw}
          title="Помилка завантаження"
          hint="Не вдалося отримати постачальників."
          className="py-[var(--space-6)]"
          action={
            <Button intent="secondary" onClick={() => void load()}>
              <RotateCcw size={18} aria-hidden /> Ще раз
            </Button>
          }
        />
      )}

      {state === 'ready' && items.length === 0 && (
        <EmptyState
          icon={Store}
          title="Немає постачальників"
          hint="Додайте першого постачальника кнопкою «Додати»."
          className="py-[var(--space-6)]"
        />
      )}

      {state === 'ready' && items.length > 0 && (
        <ul className="flex flex-col gap-1">
          {items.map((supplier) => (
            <Card
              as="li"
              variant="solid"
              key={supplier.id}
              className="flex flex-col gap-[var(--space-2)] py-[var(--space-3)]"
            >
              <div className="flex items-center gap-[var(--space-2)]">
                <Store
                  size={16}
                  aria-hidden
                  className="shrink-0 text-[var(--color-text-muted)]"
                />
                <span className="min-w-0 flex-1 truncate font-[var(--font-weight-medium)]">
                  {supplier.name}
                </span>
                {!supplier.is_active && (
                  <span className="shrink-0 rounded-[var(--radius-full)] bg-[var(--color-warning-bg)] px-[var(--space-2)] py-[2px] text-[var(--font-size-xs)] text-[var(--color-warning)]">
                    Неактивний
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-[var(--space-2)]">
                <Button
                  size="sm"
                  intent="secondary"
                  disabled={busyId === supplier.id}
                  onClick={() => openEdit(supplier)}
                >
                  <Pencil size={16} aria-hidden /> Редагувати
                </Button>
                {supplier.is_active && (
                  <Button
                    size="sm"
                    intent="secondary"
                    disabled={busyId === supplier.id}
                    onClick={() => void deactivate(supplier)}
                  >
                    <PowerOff size={16} aria-hidden /> Деактивувати
                  </Button>
                )}
                <Button
                  size="sm"
                  intent="danger"
                  disabled={busyId === supplier.id}
                  onClick={() => void remove(supplier)}
                >
                  <Trash2 size={16} aria-hidden /> Видалити
                </Button>
              </div>
            </Card>
          ))}
        </ul>
      )}

      <SupplierFormSheet
        open={sheetOpen}
        supplier={editing}
        saving={isSaving}
        onSubmit={(data) => void submit(data)}
        onClose={() => {
          setSheetOpen(false);
          setEditing(null);
        }}
      />
    </section>
  );
}

/**
 * Section 3 — Mappings management. Debounced text search + supplier filter feed
 * `GET /api/mappings/`; each row offers re-target (via {@link ProductPickerSheet}
 * + `mappings.update`) and delete.
 *
 * @param props.toast - The shared toast dispatcher.
 * @returns The mappings management card.
 */
function MappingsSection({ toast }: { toast: ToastFn }): JSX.Element {
  const [state, setState] = useState<LoadState>('loading');
  const [items, setItems] = useState<MappingAdmin[]>([]);
  const [query, setQuery] = useState('');
  /** The active supplier filter (a supplier id), or 0 for "all". */
  const [supplierId, setSupplierId] = useState<number>(0);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  /** Id of the row whose delete is in flight (disables that row). */
  const [busyId, setBusyId] = useState<number | null>(null);
  /** The mapping currently being re-targeted (drives the picker sheet). */
  const [retargeting, setRetargeting] = useState<MappingAdmin | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  /** Bumped per request so stale list responses are discarded. */
  const loadSeq = useRef(0);

  // Load the supplier list once for the filter chips (best-effort; the filter
  // simply stays at "all" if this fails).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await suppliersApi.list({ includeInactive: true });
        if (!cancelled) setSuppliers(data);
      } catch {
        /* non-fatal: the filter just shows "all" */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** Fetch mappings for the current query + supplier filter (seq-guarded). */
  const load = useCallback(async (q: string, supplier: number) => {
    const seq = loadSeq.current + 1;
    loadSeq.current = seq;
    setState('loading');
    try {
      const data = await mappingsApi.list({
        q: q.trim() || undefined,
        supplier: supplier || undefined,
      });
      if (seq === loadSeq.current) {
        setItems(data);
        setState('ready');
      }
    } catch {
      if (seq === loadSeq.current) {
        setState('error');
      }
    }
  }, []);

  // Debounced reload whenever the query or supplier filter changes.
  useEffect(() => {
    const handle = setTimeout(() => {
      void load(query, supplierId);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [query, supplierId, load]);

  /** Re-target a mapping to a new product via the picker, then refresh the row. */
  const retarget = useCallback(
    async (product: OurProduct) => {
      if (!retargeting) return;
      setIsSaving(true);
      try {
        const updated = await mappingsApi.update(retargeting.id, {
          our_product_id: product.id,
        });
        setItems((current) =>
          current.map((m) => (m.id === updated.id ? updated : m)),
        );
        toast({ variant: 'success', title: 'Перепривʼязано' });
        setRetargeting(null);
      } catch {
        toast({ variant: 'error', title: 'Не вдалося перепривʼязати' });
      } finally {
        setIsSaving(false);
      }
    },
    [retargeting, toast],
  );

  /** Forget a mapping, then drop it from the list. */
  const remove = useCallback(
    async (mapping: MappingAdmin) => {
      setBusyId(mapping.id);
      try {
        await mappingsApi.remove(mapping.id);
        setItems((current) => current.filter((m) => m.id !== mapping.id));
        toast({ variant: 'success', title: 'Видалено' });
      } catch {
        toast({ variant: 'error', title: 'Не вдалося видалити' });
      } finally {
        setBusyId(null);
      }
    },
    [toast],
  );

  return (
    <section className="flex flex-col gap-[var(--space-2)]">
      <h2 className="flex items-center gap-2 text-[var(--font-size-lg)]">
        <Link2 size={20} aria-hidden className="text-[var(--color-blue)]" />
        Маппінги
      </h2>

      <Input
        label="Пошук маппінгів"
        labelHidden
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Артикул постачальника або наш SKU/назва…"
        inputMode="search"
      />

      {/* Supplier filter chips — a lightweight horizontal scroller. */}
      {suppliers.length > 0 && (
        <div className="-mx-[var(--space-1)] flex gap-[var(--space-1)] overflow-x-auto px-[var(--space-1)] pb-[var(--space-1)]">
          <FilterChip
            label="Усі"
            active={supplierId === 0}
            onClick={() => setSupplierId(0)}
          />
          {suppliers.map((s) => (
            <FilterChip
              key={s.id}
              label={s.name}
              active={supplierId === s.id}
              onClick={() => setSupplierId(s.id)}
            />
          ))}
        </div>
      )}

      {state === 'loading' && (
        <ul className="flex flex-col gap-1" aria-hidden>
          {Array.from({ length: 4 }).map((_, i) => (
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
          hint="Не вдалося отримати маппінги."
          className="py-[var(--space-6)]"
          action={
            <Button intent="secondary" onClick={() => void load(query, supplierId)}>
              <RotateCcw size={18} aria-hidden /> Ще раз
            </Button>
          }
        />
      )}

      {state === 'ready' && items.length === 0 && (
        <EmptyState
          icon={query.trim() ? Search : Link2}
          title={query.trim() ? 'Нічого не знайдено' : 'Поки порожньо'}
          hint={
            query.trim()
              ? 'Уточніть запит або змініть фільтр постачальника.'
              : 'Тут зʼявляться запамʼятовані відповідності артикулів.'
          }
          className="py-[var(--space-6)]"
        />
      )}

      {state === 'ready' && items.length > 0 && (
        <ul className="flex flex-col gap-1">
          {items.map((mapping) => (
            <Card
              as="li"
              variant="solid"
              key={mapping.id}
              className="flex flex-col gap-[var(--space-2)] py-[var(--space-3)]"
            >
              <div className="flex flex-col gap-[2px]">
                <span className="flex items-center gap-1 text-[var(--font-size-sm)] font-[var(--font-weight-medium)]">
                  <span className="truncate">{mapping.supplier_sku}</span>
                  <span aria-hidden className="text-[var(--color-text-muted)]">
                    →
                  </span>
                  <span className="truncate">
                    {mapping.our_product?.sku ?? '—'}
                  </span>
                </span>
                <span className="truncate text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
                  {mapping.our_product?.name ?? 'Без товару'} ·{' '}
                  {mapping.supplier.name} · {mapping.times_used}×
                </span>
              </div>

              <div className="flex flex-wrap gap-[var(--space-2)]">
                <Button
                  size="sm"
                  intent="secondary"
                  disabled={busyId === mapping.id}
                  onClick={() => setRetargeting(mapping)}
                >
                  <RefreshCw size={16} aria-hidden /> Перепривʼязати
                </Button>
                <Button
                  size="sm"
                  intent="danger"
                  disabled={busyId === mapping.id}
                  onClick={() => void remove(mapping)}
                >
                  <Trash2 size={16} aria-hidden /> Видалити
                </Button>
              </div>
            </Card>
          ))}
        </ul>
      )}

      <ProductPickerSheet
        open={retargeting !== null}
        title="Перепривʼязати товар"
        description={
          retargeting ? (
            <>
              <CheckCircle2
                size={14}
                aria-hidden
                className="mr-1 inline align-[-2px] text-[var(--color-text-muted)]"
              />
              {retargeting.supplier_sku} · {retargeting.supplier.name}
            </>
          ) : undefined
        }
        saving={isSaving}
        onSelect={(product) => void retarget(product)}
        onClose={() => setRetargeting(null)}
      />
    </section>
  );
}

/** Props for {@link FilterChip}. */
interface FilterChipProps {
  /** Visible chip label. */
  label: string;
  /** Whether this chip is the active filter. */
  active: boolean;
  /** Click handler that activates this filter. */
  onClick: () => void;
}

/**
 * A small pill-shaped toggle used for the supplier filter row.
 *
 * @param props - {@link FilterChipProps}.
 * @returns The chip button element.
 */
function FilterChip({ label, active, onClick }: FilterChipProps): JSX.Element {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={[
        'shrink-0 whitespace-nowrap rounded-[var(--radius-full)] border',
        'px-[var(--space-3)] py-[var(--space-1)] text-[var(--font-size-sm)]',
        'focus-visible:outline-none',
        active
          ? 'border-[var(--color-blue)] bg-[var(--color-blue)] text-[var(--color-text-inverse)]'
          : 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] hover:bg-[var(--color-surface-muted)]',
      ].join(' ')}
    >
      {label}
    </button>
  );
}
