/**
 * ThemeProvider + ThemeToggle — light/dark theming for the Valeraup PWA.
 *
 * Responsibilities:
 * - Hold the active {@link Theme} in state, seeded from {@link getInitialTheme}
 *   (persisted choice → OS `prefers-color-scheme`).
 * - Reflect it onto `<html>` via the `data-theme` attribute so the token
 *   overrides in `tokens.css` take effect for the whole tree.
 * - Persist explicit user choices to `localStorage` under
 *   {@link THEME_STORAGE_KEY}.
 * - Follow live OS scheme changes *only while the user has not made an explicit
 *   choice* (so a manual toggle is never silently overridden).
 *
 * The context object, hook, and helpers live in `@/lib/useTheme` to avoid a
 * circular import and to allow the initial theme to be resolved before mount.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { JSX, ReactNode } from 'react';
import { Moon, Sun } from 'lucide-react';

import { Button, type ButtonProps } from '@/components/ui/Button';
import {
  getInitialTheme,
  THEME_ATTRIBUTE,
  THEME_STORAGE_KEY,
  ThemeContext,
  useTheme,
  type Theme,
  type ThemeContextValue,
} from '@/lib/useTheme';

// Re-export the hook so `import { useTheme } from '@/components/ThemeProvider'`
// works for callers that expect the provider module to surface it.
export { useTheme };

/** Apply a theme to the document root. Centralized so state + initial paint use
 * the exact same DOM mutation. No-op when there is no document (SSR/tests). */
function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') {
    return;
  }
  document.documentElement.setAttribute(THEME_ATTRIBUTE, theme);
}

/** Props for {@link ThemeProvider}. */
export interface ThemeProviderProps {
  /** The subtree that should read the theme context. */
  children: ReactNode;
}

/**
 * Provide the theme context to the app and keep `<html data-theme>` in sync.
 *
 * @param props - {@link ThemeProviderProps}.
 * @returns The provider wrapping `children`.
 */
export function ThemeProvider({ children }: ThemeProviderProps): JSX.Element {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);
  // Tracks whether the user has explicitly chosen a theme this session; while
  // false we keep mirroring the OS preference.
  const userChoseRef = useRef<boolean>(false);

  // Reflect the active theme onto <html> on mount and whenever it changes.
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  /** Set + persist an explicit theme choice. */
  const setTheme = useCallback((next: Theme) => {
    userChoseRef.current = true;
    setThemeState(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Persisting is best-effort; the in-memory theme still applies.
    }
  }, []);

  /** Toggle between light and dark (treated as an explicit choice). */
  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  }, [theme, setTheme]);

  // Follow OS scheme changes until the user makes an explicit choice. After
  // that, their preference is authoritative and we stop listening to the OS.
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (event: MediaQueryListEvent): void => {
      if (userChoseRef.current) {
        return;
      }
      setThemeState(event.matches ? 'dark' : 'light');
    };
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/** Props for {@link ThemeToggle}. Inherits Button styling props (minus the ones
 * the toggle controls itself), so it can be sized/placed like any other button. */
export type ThemeToggleProps = Omit<ButtonProps, 'children' | 'onClick' | 'asChild'>;

/**
 * A single-tap button that flips the theme. Shows a Sun in dark mode (tap → go
 * light) and a Moon in light mode (tap → go dark), with an accessible label
 * reflecting the *action*, not the current state.
 *
 * Defaults to the `ghost` icon variant so it sits unobtrusively in a header.
 *
 * @param props - {@link ThemeToggleProps} (any Button prop except children /
 *   onClick / asChild).
 * @returns The rendered toggle button.
 */
export function ThemeToggle({
  intent = 'ghost',
  size = 'icon',
  ...props
}: ThemeToggleProps): JSX.Element {
  const { theme, toggleTheme } = useTheme();
  const goingDark = theme === 'light';

  return (
    <Button
      intent={intent}
      size={size}
      onClick={toggleTheme}
      aria-label={goingDark ? 'Темна тема' : 'Світла тема'}
      title={goingDark ? 'Темна тема' : 'Світла тема'}
      {...props}
    >
      {goingDark ? (
        <Moon size={20} aria-hidden />
      ) : (
        <Sun size={20} aria-hidden />
      )}
    </Button>
  );
}
