/**
 * Tailwind CSS configuration for the Valeraup PWA.
 *
 * The visual design system lives in CSS custom properties
 * (`src/styles/tokens.css`, the NextCRM palette navy → electric blue → cyan).
 * Components use Tailwind utility classes plus arbitrary values that read those
 * tokens, e.g. `bg-[var(--color-blue)]` / `rounded-[var(--radius-md)]`. We keep
 * the theme minimal here on purpose and let the tokens drive the look, so the
 * file can later be swapped for the real `@nextcrm/tokens` package without
 * rewriting component classes.
 *
 * @type {import('tailwindcss').Config}
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
};
