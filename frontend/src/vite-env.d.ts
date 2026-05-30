/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

/**
 * Typed access to the environment variables Vite inlines at build time.
 *
 * Only variables prefixed with `VITE_` are exposed to client code. Keep this in
 * sync with frontend/.env.example.
 */
interface ImportMetaEnv {
  /** Base URL of the Valeraup REST API, including the trailing `/api`. */
  readonly VITE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
