/**
 * Storybook stories for {@link Skeleton}.
 *
 * Shows single blocks, a circle, and a realistic receipt-line-card placeholder
 * — the exact shape the ReceiptTable shows while `status === 'recognizing'`.
 */
import type { Meta, StoryObj } from '@storybook/react';

import { Skeleton } from './Skeleton';

const meta: Meta<typeof Skeleton> = {
  title: 'UI/Skeleton',
  component: Skeleton,
  parameters: { layout: 'padded' },
  argTypes: {
    width: { control: 'text' },
    height: { control: 'text' },
    circle: { control: 'boolean' },
  },
};

export default meta;
type Story = StoryObj<typeof Skeleton>;

/** A single line placeholder. */
export const Line: Story = { args: { width: 240, height: 16 } };

/** A circular placeholder (thumbnail/avatar). */
export const Circle: Story = { args: { width: 48, height: 48, circle: true } };

/** A composed card placeholder mirroring a receipt line card. */
export const ReceiptLineCard: Story = {
  render: () => (
    <div className="flex flex-col gap-[var(--space-3)] rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-[var(--space-4)]">
      <Skeleton width="40%" height={14} />
      <Skeleton width="80%" height={18} />
      <div className="flex gap-[var(--space-3)]">
        <Skeleton width={80} height={40} />
        <Skeleton width={80} height={40} />
      </div>
    </div>
  ),
};

/** A list of placeholder rows (suppliers loading). */
export const List: Story = {
  render: () => (
    <div className="flex flex-col gap-[var(--space-3)]">
      {Array.from({ length: 4 }, (_, i) => (
        <div
          key={i}
          className="flex items-center gap-[var(--space-3)] rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-[var(--space-4)]"
        >
          <Skeleton width={40} height={40} circle />
          <Skeleton width="60%" height={16} />
        </div>
      ))}
    </div>
  ),
};
