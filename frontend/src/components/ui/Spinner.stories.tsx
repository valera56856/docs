/**
 * Storybook stories for {@link Spinner}.
 *
 * Shows the default spinner, sizes, and a muted-color variant. Verify the spin
 * animation pauses under the OS "reduce motion" setting.
 */
import type { Meta, StoryObj } from '@storybook/react';

import { Spinner } from './Spinner';

const meta: Meta<typeof Spinner> = {
  title: 'UI/Spinner',
  component: Spinner,
  parameters: { layout: 'centered' },
  argTypes: {
    size: { control: { type: 'number', min: 12, max: 64, step: 4 } },
    label: { control: 'text' },
  },
};

export default meta;
type Story = StoryObj<typeof Spinner>;

/** Default 20px brand-blue spinner. */
export const Default: Story = {};

/** Larger, for a full-screen loading state. */
export const Large: Story = { args: { size: 48 } };

/** Muted color (e.g. inside a secondary button). */
export const Muted: Story = {
  args: { className: 'text-[color:var(--color-text-muted)]' },
};

/** Decorative (no accessible label) — when adjacent text conveys loading. */
export const Decorative: Story = { args: { label: null } };
