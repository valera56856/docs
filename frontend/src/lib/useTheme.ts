/**
 * useTheme — the React context hook for the app's light/dark theme.
 *
 * The provider implementation lives in {@link ../components/ThemeProvider}
 * (a `.tsx` file, since it renders JSX). This module owns the *non-JSX* parts
 * of the contract so they can be imported anywhere without pulling a component
 * into scope:
 *
 * - the {@link Theme} union and {@link ThemeContextValue} shape,
 * - the React context object ({@link ThemeContext}),
 * - the storage key + the `prefers-color-scheme` default resolver,
 * - the {@link useTheme} consumer hook.
 *
 * WHY split it out: keeping the context object and helpers here avoids a
 * circular import (ThemeProvider imports these; consumers import `useTheme`
 * without importing the provider) and lets `getInitialTheme` run before React
 * mounts to prevent a flash of the wrong theme.
 */
import { createContext, useContext } from 'react';

/** The two supported themes. There is intentionally no "system" runtime value:
 * we resolve `prefers-color-scheme` once to a concrete theme and then let the
 * user override + persist it. */
export type Theme = 'light' | 'dark';

/** Value exposed by the theme context. */
export interface ThemeContextValue {
  /** The currently applied theme. */
  theme: Theme;
  /** Switch to an explicit theme (persisted to localStorage). */
  setTheme: (theme: Theme) => void;
  /** Toggle between light and dark (persisted to localStorage). */
  toggleTheme: () => void;
}

/** localStorage key under which the user's explicit choice is persisted. */
export const THEME_STORAGE_KEY = 'valeraup.theme';

/** The DOM attribute (on `<html>`) that drives the token overrides. */
export const THEME_ATTRIBUTE = 'data-theme';

/**
 * The theme context. Default is a no-op `light` value so that a component
 * rendered outside the provider (e.g. an isolated unit test) degrades
 * gracefully instead of throwing.
 */
export const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  setTheme: () => undefined,
  toggleTheme: () => undefined,
});

/**
 * Resolve the initial theme: a previously persisted choice wins; otherwise we
 * honor the OS `prefers-color-scheme`. Safe to call before React mounts (it is
 * defensive about `window`/`localStorage` being unavailable, e.g. SSR or a
 * locked-down WebView).
 *
 * @returns The theme to apply on first paint.
 */
export function getInitialTheme(): Theme {
  if (typeof window === 'undefined') {
    return 'light';
  }
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') {
      return stored;
    }
  } catch {
    // localStorage can throw in private mode / restricted WebViews — fall back
    // to the media query below rather than crashing the app shell.
  }
  const prefersDark =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'dark' : 'light';
}

/**
 * Read the current theme and its setters from context.
 *
 * @returns The {@link ThemeContextValue} (theme + setTheme + toggleTheme).
 * @example
 * const { theme, toggleTheme } = useTheme();
 */
export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
