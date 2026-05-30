/**
 * Application route table.
 *
 * Routes mirror the Valeraup user flow (scan-first → table → mapping →
 * generate):
 *   /                       -> Login (email/password or fast PIN)
 *   /receipt/new            -> scan-first: create a supplier-less draft + camera
 *   /suppliers              -> browse/manage suppliers (legacy pick-first entry)
 *   /receipt/:id/camera     -> capture + upload invoice photos, then recognize
 *   /receipt/:id            -> recognized lines + inline edit + mapping table
 *   /receipt/:id/generate   -> generate + download the .xlsx receipt
 *   /admin                  -> catalog sync, suppliers, mappings (admin only)
 *
 * The scan-first entry (`/receipt/new`) is the primary "Нова накладна" flow: the
 * operator photographs the invoice WITHOUT picking a supplier first, and
 * recognition auto-detects the supplier from the header. {@link CameraPage}
 * creates the draft on entry when there is no `:id`, then carries the new id in
 * the URL exactly like the supplier-first path.
 *
 * Auth gating: every route except `/` is wrapped in {@link RequireAuth}, which
 * redirects unauthenticated users to the login screen. The `/admin` route adds
 * its own role check (see {@link AdminPage}), since the kit's `useAuth` does not
 * carry the role — the page fetches `/auth/me/` and redirects non-admins.
 */
import {
  createBrowserRouter,
  Navigate,
  Outlet,
  useLocation,
  type RouteObject,
} from 'react-router-dom';
import type { JSX } from 'react';

import { useAuth } from '@/lib/auth';
import { Spinner } from '@/components/ui/Spinner';
import { AppShell } from '@/components/AppShell';
import { LoginPage } from '@/pages/LoginPage';
import { SuppliersPage } from '@/pages/SuppliersPage';
import { CameraPage } from '@/pages/CameraPage';
import { ReceiptTablePage } from '@/pages/ReceiptTablePage';
import { GeneratePage } from '@/pages/GeneratePage';
import { AdminPage } from '@/pages/AdminPage';

/**
 * Route guard. Renders the protected subtree only when authenticated; otherwise
 * redirects to `/`, preserving the attempted location so we can return after
 * login.
 *
 * While the initial session-restore is in flight we render a centered spinner
 * (a branded splash) so the screen is never blank.
 *
 * @returns The child routes via {@link Outlet}, a spinner, or a redirect.
 */
function RequireAuth(): JSX.Element {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex min-h-[60dvh] items-center justify-center">
        <Spinner size={32} label="Завантаження…" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace state={{ from: location }} />;
  }

  return <Outlet />;
}

/** Declarative route configuration consumed by the data router. */
export const routes: RouteObject[] = [
  { path: '/', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    // The {@link AppShell} layout route adds the persistent desktop top bar on
    // lg+ around every authenticated screen; on mobile it is a transparent
    // passthrough, so the per-screen phone flow is unchanged. Login stays
    // outside this subtree and therefore gets no chrome.
    children: [
      {
        element: <AppShell />,
        children: [
          { path: '/suppliers', element: <SuppliersPage /> },
          // Scan-first: a supplier-less draft is created on entry; the camera
          // reuses the same component (it branches on the missing `:id`).
          { path: '/receipt/new', element: <CameraPage /> },
          { path: '/receipt/:id/camera', element: <CameraPage /> },
          { path: '/receipt/:id', element: <ReceiptTablePage /> },
          { path: '/receipt/:id/generate', element: <GeneratePage /> },
          { path: '/admin', element: <AdminPage /> },
        ],
      },
    ],
  },
  // Unknown paths fall back to the login / home route.
  { path: '*', element: <Navigate to="/" replace /> },
];

/** The configured browser router used by {@link App}. */
export const router = createBrowserRouter(routes);
