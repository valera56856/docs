/**
 * Application route table.
 *
 * Routes mirror the Valeraup user flow (suppliers → camera → table → mapping →
 * generate):
 *   /                       -> Login (email/password or fast PIN)
 *   /suppliers              -> pick a supplier; tap creates a draft receipt
 *   /receipt/:id/camera     -> capture + upload invoice photos, then recognize
 *   /receipt/:id            -> recognized lines + inline edit + mapping table
 *   /receipt/:id/generate   -> generate + download the .xlsx receipt
 *   /admin                  -> catalog sync, suppliers, mappings (admin only)
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
    children: [
      { path: '/suppliers', element: <SuppliersPage /> },
      { path: '/receipt/:id/camera', element: <CameraPage /> },
      { path: '/receipt/:id', element: <ReceiptTablePage /> },
      { path: '/receipt/:id/generate', element: <GeneratePage /> },
      { path: '/admin', element: <AdminPage /> },
    ],
  },
  // Unknown paths fall back to the login / home route.
  { path: '*', element: <Navigate to="/" replace /> },
];

/** The configured browser router used by {@link App}. */
export const router = createBrowserRouter(routes);
