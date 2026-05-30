/**
 * Authentication context for the Valeraup PWA.
 *
 * Exposes {@link useAuth} with `login`, `pin`, `logout`, and the current auth
 * state. Token strategy (security-driven):
 *
 * - The short-lived ACCESS token lives only in module memory (see lib/api.ts)
 *   to limit XSS exposure.
 * - The long-lived REFRESH token is persisted via {@link secureStore}. On native
 *   (Capacitor) this MUST use Capacitor Secure Storage / Keychain so the token
 *   is encrypted at rest. On the web we fall back to localStorage — flagged as a
 *   TODO because it is less safe and acceptable only for the browser preview.
 *
 * The provider registers a refresh handler with the api wrapper so expired
 * access tokens are renewed transparently, and restores the session on mount.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type JSX,
  type ReactNode,
} from 'react';

import { authApi, setAccessToken, setRefreshHandler } from '@/lib/api';

/** Storage key for the persisted refresh token. */
const REFRESH_KEY = 'valeraup.refresh';

/**
 * Minimal secure-storage adapter.
 *
 * TODO(native): replace the web branch with Capacitor Secure Storage
 * (`@capacitor/preferences` + encryption, or a dedicated secure-storage plugin)
 * so the refresh token is stored in the OS Keychain / Keystore. localStorage is
 * a temporary fallback for the browser build only.
 */
const secureStore = {
  async get(key: string): Promise<string | null> {
    return localStorage.getItem(key);
  },
  async set(key: string, value: string): Promise<void> {
    localStorage.setItem(key, value);
  },
  async remove(key: string): Promise<void> {
    localStorage.removeItem(key);
  },
};

/** Public shape of the auth context. */
export interface AuthContextValue {
  /** Whether a user is currently authenticated (has a valid access token). */
  isAuthenticated: boolean;
  /** True while the initial session-restore is in flight. */
  isLoading: boolean;
  /** Log in with email + password. Throws {@link ApiError} on failure. */
  login: (email: string, password: string) => Promise<void>;
  /** Fast login with a 4-digit PIN. Throws {@link ApiError} on failure. */
  pin: (email: string, pin: string) => Promise<void>;
  /** Clear tokens and end the session. */
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Provider that owns auth state and token lifecycle.
 *
 * @param props.children - The app subtree that needs auth access.
 */
export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  /** Apply a fresh token pair: access -> memory, refresh -> secure storage. */
  const applyTokens = useCallback(
    async (access: string, refresh: string) => {
      setAccessToken(access);
      await secureStore.set(REFRESH_KEY, refresh);
      setIsAuthenticated(true);
    },
    [],
  );

  /** Clear all tokens and mark the user logged out. */
  const clearTokens = useCallback(async () => {
    setAccessToken(null);
    await secureStore.remove(REFRESH_KEY);
    setIsAuthenticated(false);
  }, []);

  /**
   * Attempt to refresh the access token using the stored refresh token.
   * Registered with the api wrapper so 401s self-heal. Returns the new access
   * token, or null when refresh is impossible (forcing the user to re-login).
   */
  const refresh = useCallback(async (): Promise<string | null> => {
    const storedRefresh = await secureStore.get(REFRESH_KEY);
    if (!storedRefresh) {
      await clearTokens();
      return null;
    }
    try {
      const { access } = await authApi.refresh(storedRefresh);
      setAccessToken(access);
      setIsAuthenticated(true);
      return access;
    } catch {
      await clearTokens();
      return null;
    }
  }, [clearTokens]);

  const login = useCallback(
    async (email: string, password: string) => {
      const { access, refresh: refreshToken } = await authApi.login(
        email,
        password,
      );
      await applyTokens(access, refreshToken);
    },
    [applyTokens],
  );

  const pin = useCallback(
    async (email: string, code: string) => {
      const { access, refresh: refreshToken } = await authApi.pin(email, code);
      await applyTokens(access, refreshToken);
    },
    [applyTokens],
  );

  const logout = useCallback(async () => {
    await clearTokens();
  }, [clearTokens]);

  // Wire the refresh handler into the api wrapper, and restore any session on
  // first mount by attempting a refresh from the stored token.
  useEffect(() => {
    setRefreshHandler(refresh);
    let cancelled = false;
    (async () => {
      await refresh();
      if (!cancelled) {
        setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      setRefreshHandler(null);
    };
  }, [refresh]);

  const value = useMemo<AuthContextValue>(
    () => ({ isAuthenticated, isLoading, login, pin, logout }),
    [isAuthenticated, isLoading, login, pin, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Access the auth context.
 *
 * @returns The current {@link AuthContextValue}.
 * @throws Error if used outside an {@link AuthProvider}.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an <AuthProvider>');
  }
  return ctx;
}
