/**
 * Storybook stories for {@link ThemeToggle} (from {@link ThemeProvider}).
 *
 * The toggle reads the theme context, so the story wraps it in a real
 * {@link ThemeProvider}. Tapping it flips `data-theme` on the document and
 * persists the choice — note this overrides the Storybook theme toolbar for the
 * session (both write the same attribute), which is the intended behavior.
 */
import type { JSX } from 'react';
import type { Meta, StoryObj } from '@storybook/react';

import { ThemeProvider, ThemeToggle, useTheme } from './ThemeProvider';

const meta: Meta<typeof ThemeToggle> = {
  title: 'Theme/ThemeToggle',
  component: ThemeToggle,
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj<typeof ThemeToggle>;

/** Small readout of the active theme next to the toggle. */
function ToggleWithReadout(): JSX.Element {
  const { theme } = useTheme();
  return (
    <div className="flex items-center gap-[var(--space-3)] rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-[var(--space-4)] text-[color:var(--color-text)]">
      <ThemeToggle />
      <span className="text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)]">
        Активна тема: <strong className="text-[color:var(--color-text)]">{theme}</strong>
      </span>
    </div>
  );
}

/** Default ghost icon toggle inside its provider. */
export const Default: Story = {
  render: () => (
    <ThemeProvider>
      <ToggleWithReadout />
    </ThemeProvider>
  ),
};

/** Bordered secondary variant (e.g. on a settings row). */
export const Secondary: Story = {
  render: () => (
    <ThemeProvider>
      <ThemeToggle intent="secondary" />
    </ThemeProvider>
  ),
};
