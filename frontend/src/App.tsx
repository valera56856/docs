/**
 * Root application component.
 *
 * Composes the app-wide providers around the data router, outermost first:
 *
 * 1. {@link ThemeProvider} — sets `data-theme` on `<html>` and exposes the
 *    light/dark toggle, so every page (and the kit components) reskin from one
 *    source of truth.
 * 2. {@link ToastProvider} + {@link Toaster} — a single toast surface any page
 *    can fire into via `useToast`, surviving route changes.
 *
 * `AuthProvider` is mounted one level up in `main.tsx`, so by the time {@link
 * App} renders every route can already read auth state via {@link useAuth}.
 */
import { RouterProvider } from 'react-router-dom';
import type { JSX } from 'react';

import { router } from '@/router';
import { ThemeProvider } from '@/components/ThemeProvider';
import { ToastProvider } from '@/components/ui/Toast';
import { Toaster } from '@/components/ui/Toaster';

/**
 * Render the routed application wrapped in theme + toast providers.
 *
 * @returns The provider tree bound to the app's route table.
 */
export function App(): JSX.Element {
  return (
    <ThemeProvider>
      <ToastProvider>
        <RouterProvider router={router} />
        {/* One toast stack for the whole app; portals to <body>. */}
        <Toaster />
      </ToastProvider>
    </ThemeProvider>
  );
}
