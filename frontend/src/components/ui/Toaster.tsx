/**
 * Toaster — the visual stack that renders the live toasts.
 *
 * Reads the toast list from {@link ./Toast.useToast} and portals the stack to a
 * fixed, safe-area-aware region. Kept separate from {@link ./Toast.ToastProvider}
 * (which owns state/timers) so the provider can be imported by non-layout code
 * without pulling in the portal.
 *
 * Mobile-first placement: bottom-center, above the home indicator, stacked
 * newest-last. The region is `pointer-events-none` so it never blocks taps
 * between toasts; individual toast cards re-enable pointer events.
 *
 * Usage (once, in App, inside the provider):
 * @example
 * <ToastProvider>
 *   <App />
 *   <Toaster />
 * </ToastProvider>
 */
import { useEffect, useState, type JSX } from 'react';
import { createPortal } from 'react-dom';

import { ToastItem, useToast } from '@/components/ui/Toast';

/** Props for {@link Toaster}. */
export interface ToasterProps {
  /**
   * Where to attach the portal. Defaults to `document.body`. Mainly useful for
   * Storybook / tests that want to scope the portal.
   */
  container?: HTMLElement | null;
}

/**
 * Render the toast stack via a portal.
 *
 * @param props - {@link ToasterProps}.
 * @returns The portalled stack, or `null` before mount / when no container.
 */
export function Toaster({ container }: ToasterProps = {}): JSX.Element | null {
  const { toasts, dismiss } = useToast();
  // Portals need a DOM target; defer to after mount so SSR/first render is safe.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return null;
  }
  const target = container ?? (typeof document !== 'undefined' ? document.body : null);
  if (!target) {
    return null;
  }

  return createPortal(
    <div
      // Fixed, centered column pinned to the bottom; clears the safe area.
      className="pointer-events-none fixed inset-x-0 bottom-0 z-[100] flex flex-col items-center gap-[var(--space-2)] px-[var(--space-4)] pb-[calc(var(--space-4)+env(safe-area-inset-bottom))]"
    >
      <div className="flex w-full max-w-sm flex-col gap-[var(--space-2)]">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </div>,
    target,
  );
}
