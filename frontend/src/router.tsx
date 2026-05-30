/**
 * Application route table.
 *
 * Routes mirror the Valeraup user flow:
 *   /                  -> Login (email/password or fast PIN)
 *   /suppliers         -> pick the supplier before shooting an invoice
 *   /receipt/new       -> Camera capture of the printed invoice
 *   /receipt/:id       -> recognized lines + mapping table
 *   /receipt/:id/generate -> generate + download the .xlsx receipt
 *   /admin             -> catalog sync, users, mappings (admin only)
 *
 * Auth gating: every route except `/` is wrapped in {@link RequireAuth}, which
 * redirects unauthenticated users to the login screen.
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
 * While the initial session-restore is in flight we render nothing (a top-level
 * splash/skeleton would slot in here).
 *
 * @returns The child routes via {@link Outlet}, or a redirect.
 */
function RequireAuth(): JSX.Element | null {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  // TODO(ux): replace with a branded splash skeleton during restore.
  if (isLoading) {
    return null;
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
      { path: '/receipt/new', element: <CameraPage /> },
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
