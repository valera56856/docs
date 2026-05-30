/**
 * `cn` — class name composer.
 *
 * Combines conditional class names with {@link clsx}, then resolves Tailwind
 * utility conflicts with {@link twMerge} (e.g. `px-2 px-4` -> `px-4`). Use this
 * everywhere instead of manual string concatenation so variant + override
 * classes merge predictably.
 *
 * @example
 * cn('px-2 py-1', isActive && 'bg-blue', className)
 */
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge an arbitrary list of class values into a single deduplicated string.
 *
 * @param inputs - Strings, arrays, or conditional objects accepted by clsx.
 * @returns The merged, conflict-resolved class name string.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
