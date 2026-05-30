/**
 * AdminPage — administrative actions (admin role only).
 *
 * For the skeleton this covers the most important admin action: triggering a
 * SalesDrive catalog sync via `POST /api/sync/catalog/` (enqueues a Celery
 * task that re-imports the YML offers into our OurProduct cache).
 *
 * Future sections (stubbed with TODOs): supplier management and a mappings
 * browser (review / edit remembered ArticleMappings).
 *
 * NOTE: role gating is also enforced server-side; the UI hint here is a
 * convenience, not a security boundary.
 */
import { useCallback, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate } from 'react-router-dom';
import { Link2, RefreshCw, Store } from 'lucide-react';

import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { Button } from '@/components/ui/Button';

/** Result of a catalog-sync attempt, for inline feedback. */
type SyncState =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'done' }
  | { kind: 'error' };

/**
 * Render the admin screen.
 *
 * @returns The admin page element.
 */
export function AdminPage(): JSX.Element {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [sync, setSync] = useState<SyncState>({ kind: 'idle' });

  /** Kick off a catalog sync; the actual work happens in a Celery task. */
  const triggerSync = useCallback(async () => {
    setSync({ kind: 'running' });
    try {
      await api.post('/sync/catalog/');
      setSync({ kind: 'done' });
    } catch {
      // TODO(ux): a 403 here means the user isn't an admin — show that hint.
      setSync({ kind: 'error' });
    }
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-[var(--space-5)] p-[var(--space-4)]">
      <h1 className="text-[var(--font-size-xl)]">Адміністрування</h1>

      {/* Catalog sync */}
      <section className="flex flex-col gap-[var(--space-3)] rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-[var(--space-4)]">
        <h2 className="flex items-center gap-2 text-[var(--font-size-lg)]">
          <RefreshCw size={20} aria-hidden className="text-[var(--color-blue)]" />
          Синхронізація каталогу
        </h2>
        <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
          Оновити кеш товарів із SalesDrive (YML). Виконується у фоні.
        </p>
        <Button
          fullWidth
          disabled={sync.kind === 'running'}
          onClick={() => void triggerSync()}
        >
          {sync.kind === 'running' ? 'Запуск…' : 'Запустити синхронізацію'}
        </Button>
        {sync.kind === 'done' && (
          <p className="text-[var(--font-size-sm)] text-[var(--color-success)]">
            Синхронізацію поставлено в чергу.
          </p>
        )}
        {sync.kind === 'error' && (
          <p
            role="alert"
            className="text-[var(--font-size-sm)] text-[var(--color-danger)]"
          >
            Не вдалося запустити. Можливо, бракує прав адміністратора.
          </p>
        )}
      </section>

      {/* TODO(feature): supplier management section. */}
      <section className="flex items-center gap-[var(--space-3)] rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-[var(--space-4)] text-[var(--color-text-muted)]">
        <Store size={20} aria-hidden />
        <p className="text-[var(--font-size-sm)]">
          Керування постачальниками — скоро.
        </p>
      </section>

      {/* TODO(feature): mappings browser (review/edit ArticleMappings). */}
      <section className="flex items-center gap-[var(--space-3)] rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-[var(--space-4)] text-[var(--color-text-muted)]">
        <Link2 size={20} aria-hidden />
        <p className="text-[var(--font-size-sm)]">
          Перегляд відповідностей артикулів — скоро.
        </p>
      </section>

      <div className="mt-auto flex flex-col gap-2">
        <Button intent="secondary" onClick={() => navigate('/suppliers')}>
          ← До постачальників
        </Button>
        <Button intent="ghost" onClick={() => void logout()}>
          Вийти
        </Button>
      </div>
    </main>
  );
}
