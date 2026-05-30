/**
 * AppShell — responsive chrome for the authenticated routes.
 *
 * The Valeraup PWA is mobile-first: on a phone each screen owns its own flow
 * (its own header, its own ThemeToggle), so on small viewports this shell is a
 * transparent passthrough — it renders nothing but its children, preserving the
 * polished single-column experience exactly as-is.
 *
 * On `lg+` (desktop) it adds a proper desktop top bar so the app stops looking
 * like a thin phone column floating in the middle of a wide screen:
 *   - the «Valeraup» brand mark (links to the suppliers home),
 *   - primary nav (Постачальники · Нова накладна · Налаштування[admin only]),
 *   - the {@link ThemeToggle} and a «Вийти» (logout) action.
 *
 * The bar is `hidden lg:flex`, so it never appears on mobile. Pages still render
 * their own in-page header; on desktop that header reads as a page title beneath
 * the global bar (the per-screen ThemeToggle/back affordances stay useful and do
 * not conflict — the global bar is additive chrome, not a replacement).
 *
 * WHY a layout route rather than wrapping each page: it keeps the chrome in one
 * place, guarantees every authenticated screen shares the same desktop frame,
 * and leaves the Login screen (mounted outside this subtree) untouched.
 *
 * The admin link is gated by a best-effort `GET /api/auth/me/` role check (the
 * `/admin` route enforces the real boundary server-side); on failure the link
 * simply stays hidden.
 */
import { useEffect, useState } from 'react';
import type { JSX } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { FilePlus2, LogOut, ScanLine, Settings, Store } from 'lucide-react';

import { authApi } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { cn } from '@/lib/cn';
import { Button } from '@/components/ui/Button';
import { ThemeToggle } from '@/components/ThemeProvider';

/** A single primary-nav destination shown in the desktop top bar. */
interface NavItem {
  /** Route to navigate to. */
  to: string;
  /** Visible Ukrainian label. */
  label: string;
  /** Leading icon (lucide). */
  icon: typeof Store;
  /** Treat the route as an exact match (no descendant highlighting). */
  end?: boolean;
}

/**
 * Render the authenticated-route shell: a desktop top bar (lg+) above the routed
 * page, or a transparent passthrough on mobile.
 *
 * @returns The shell element wrapping the active route via {@link Outlet}.
 */
export function AppShell(): JSX.Element {
  const navigate = useNavigate();
  const { logout } = useAuth();

  /**
   * Whether the current user is an admin — gates the «Налаштування» nav link.
   * Best-effort; on failure the link stays hidden (the route enforces the real
   * role boundary server-side).
   */
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await authApi.me();
        if (!cancelled) setIsAdmin(me.role === 'admin');
      } catch {
        /* non-fatal: the admin link simply stays hidden */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const navItems: NavItem[] = [
    { to: '/suppliers', label: 'Постачальники', icon: Store },
    { to: '/suppliers', label: 'Нова накладна', icon: FilePlus2 },
    ...(isAdmin
      ? [{ to: '/admin', label: 'Налаштування', icon: Settings }]
      : []),
  ];

  return (
    <div className="flex min-h-[100dvh] flex-col">
      {/* Desktop chrome only — hidden on mobile so the phone flow is unchanged.
          The translucent surface + blur is expressed with color-mix (Tailwind's
          slash-opacity can't derive alpha from a CSS var) so it frosts content
          scrolling beneath it; it degrades to the solid surface where
          color-mix/backdrop-filter are unsupported. */}
      <header
        className="sticky top-0 z-30 hidden border-b border-[var(--color-border)] backdrop-blur-md lg:block"
        style={{
          backgroundColor:
            'color-mix(in srgb, var(--color-surface) 85%, transparent)',
        }}
      >
        <div className="mx-auto flex h-16 w-full max-w-screen-xl items-center justify-between gap-[var(--space-6)] px-[var(--space-6)] xl:px-[var(--space-8)]">
          {/* Brand mark — returns to the suppliers home. */}
          <button
            type="button"
            onClick={() => navigate('/suppliers')}
            className="flex items-center gap-[var(--space-3)] rounded-[var(--radius-md)] focus-visible:outline-none"
            aria-label="Valeraup — на головну"
          >
            <span
              aria-hidden
              className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] text-[color:var(--color-on-accent)] shadow-[var(--shadow-accent)]"
              style={{ backgroundImage: 'var(--gradient-brand)' }}
            >
              <ScanLine size={20} strokeWidth={2.25} />
            </span>
            <span className="text-[length:var(--font-size-lg)] font-[var(--font-weight-bold)] tracking-[var(--tracking-tight)] text-[color:var(--color-text)]">
              Valeraup
            </span>
          </button>

          {/* Primary nav. */}
          <nav
            aria-label="Головна навігація"
            className="flex items-center gap-[var(--space-1)]"
          >
            {navItems.map((item) => (
              <NavLink
                key={`${item.to}-${item.label}`}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-[var(--space-2)] rounded-[var(--radius-md)]',
                    'px-[var(--space-3)] py-[var(--space-2)]',
                    'text-[length:var(--font-size-sm)] font-[var(--font-weight-semibold)]',
                    'transition-[background-color,color] duration-150 focus-visible:outline-none',
                    isActive
                      ? 'bg-[var(--color-info-bg)] text-[color:var(--color-blue)]'
                      : 'text-[color:var(--color-text-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[color:var(--color-text)]',
                  )
                }
              >
                <item.icon size={18} aria-hidden />
                {item.label}
              </NavLink>
            ))}
          </nav>

          {/* Theme + session controls. */}
          <div className="flex items-center gap-[var(--space-2)]">
            <ThemeToggle />
            <Button
              intent="secondary"
              size="sm"
              onClick={() => void logout()}
              className="gap-[var(--space-2)]"
            >
              <LogOut size={16} aria-hidden /> Вийти
            </Button>
          </div>
        </div>
      </header>

      {/* Routed page. Pages own their own max-width / padding so mobile is
          untouched; on desktop they widen via their own breakpoints. */}
      <Outlet />
    </div>
  );
}
