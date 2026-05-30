/**
 * Application entry point.
 *
 * Mounts the React tree into #root, loads global styles + design tokens, and
 * wraps the app in the {@link AuthProvider} so every route can read auth state
 * and call login / pin / logout. StrictMode is on to surface unsafe lifecycles
 * during development.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { AuthProvider } from '@/lib/auth';
import { App } from '@/App';

import '@/styles/tokens.css';
import '@/styles/global.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root element #root not found in index.html');
}

createRoot(container).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
