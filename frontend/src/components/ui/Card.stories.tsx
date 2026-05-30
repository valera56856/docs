/**
 * Storybook stories for {@link Card}.
 *
 * Shows the `glass` (frosted) and `solid` treatments, the interactive
 * (tappable row) affordance, and a realistic supplier-row composition. Switch
 * the theme toolbar to light/dark to confirm the glass tokens adapt — the
 * frosted blur is most visible over the patterned backdrop in the GlassOnImage
 * story.
 */
import type { Meta, StoryObj } from '@storybook/react';
import { ChevronRight, Truck } from 'lucide-react';

import { Card } from './Card';
import { StatusBadge } from './StatusBadge';

const meta: Meta<typeof Card> = {
  title: 'UI/Card',
  component: Card,
  parameters: { layout: 'padded' },
  argTypes: {
    variant: { control: 'inline-radio', options: ['glass', 'solid'] },
    interactive: { control: 'boolean' },
  },
};

export default meta;
type Story = StoryObj<typeof Card>;

/** Default frosted-glass surface. */
export const Glass: Story = {
  args: {
    variant: 'glass',
    children: (
      <div className="flex flex-col gap-1">
        <h3 className="text-[length:var(--font-size-lg)] font-[var(--font-weight-semibold)]">
          Накладна #128
        </h3>
        <p className="text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)]">
          Liquid Glass — напівпрозора поверхня з розмиттям фону.
        </p>
      </div>
    ),
  },
};

/** Flat opaque surface for dense lists. */
export const Solid: Story = {
  args: {
    variant: 'solid',
    children: (
      <div className="flex flex-col gap-1">
        <h3 className="text-[length:var(--font-size-lg)] font-[var(--font-weight-semibold)]">
          Solid surface
        </h3>
        <p className="text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)]">
          Без розмиття — для щільних списків.
        </p>
      </div>
    ),
  },
};

/** A whole card as a tap target (supplier row pattern). */
export const InteractiveRow: Story = {
  args: {
    interactive: true,
    children: (
      <div className="flex items-center gap-[var(--space-3)]">
        <span
          aria-hidden
          className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-info-bg)] text-[color:var(--color-info)]"
        >
          <Truck size={20} aria-hidden />
        </span>
        <span className="flex-1 font-[var(--font-weight-medium)]">
          ТОВ «Постачальник»
        </span>
        <StatusBadge receipt="ready" />
        <ChevronRight size={20} aria-hidden className="text-[color:var(--color-text-muted)]" />
      </div>
    ),
  },
};

/** The frosted glass over a colorful backdrop, where the blur is obvious. */
export const GlassOnImage: Story = {
  render: (args) => (
    <div
      style={{
        background:
          'radial-gradient(circle at 20% 20%, #2563EB 0%, transparent 40%), radial-gradient(circle at 80% 60%, #06B6D4 0%, transparent 45%), #0A1A3F',
        padding: '2rem',
        borderRadius: 'var(--radius-lg)',
      }}
    >
      <Card {...args}>
        <h3 className="text-[length:var(--font-size-lg)] font-[var(--font-weight-semibold)]">
          Frosted glass
        </h3>
        <p className="text-[length:var(--font-size-sm)] text-[color:var(--color-text-muted)]">
          backdrop-filter blur + accent gradient.
        </p>
      </Card>
    </div>
  ),
  args: { variant: 'glass' },
};
