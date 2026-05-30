/**
 * Root application component.
 *
 * Thin shell that hands rendering to the data router. `AuthProvider` is mounted
 * one level up in `main.tsx`, so by the time {@link App} renders, every route
 * can read auth state via {@link useAuth}.
 */
import { RouterProvider } from 'react-router-dom';
import type { JSX } from 'react';

import { router } from '@/router';

/**
 * Render the routed application.
 *
 * @returns The {@link RouterProvider} bound to the app's route table.
 */
export function App(): JSX.Element {
  return <RouterProvider router={router} />;
}
