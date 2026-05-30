/**
 * Storybook stories for {@link Button}.
 *
 * Documents every intent + size combination and the `asChild` pattern. These
 * stories double as a visual regression surface and as living documentation of
 * the component's API.
 */
import type { Meta, StoryObj } from '@storybook/react';
import { Camera } from 'lucide-react';

import { Button } from './Button';

const meta: Meta<typeof Button> = {
  title: 'UI/Button',
  component: Button,
  parameters: { layout: 'centered' },
  argTypes: {
    intent: {
      control: 'select',
      options: ['primary', 'secondary', 'ghost', 'danger'],
    },
    size: { control: 'select', options: ['sm', 'md', 'lg', 'icon'] },
    fullWidth: { control: 'boolean' },
    disabled: { control: 'boolean' },
  },
  args: { children: 'Зберегти', intent: 'primary', size: 'md' },
};

export default meta;
type Story = StoryObj<typeof Button>;

/** Default primary call-to-action. */
export const Primary: Story = {};

/** Low-emphasis bordered button. */
export const Secondary: Story = { args: { intent: 'secondary' } };

/** Minimal text-only button. */
export const Ghost: Story = { args: { intent: 'ghost', children: 'Скасувати' } };

/** Destructive action. */
export const Danger: Story = { args: { intent: 'danger', children: 'Видалити' } };

/** Full-width mobile CTA — the common pattern on small screens. */
export const FullWidth: Story = {
  args: { fullWidth: true, children: 'Сфотографувати накладну' },
  parameters: { layout: 'padded' },
};

/** Icon-only button (square, still 44px touch target). */
export const IconOnly: Story = {
  args: { size: 'icon', children: <Camera size={20} aria-hidden /> },
};

/** Disabled state. */
export const Disabled: Story = { args: { disabled: true } };

/**
 * `asChild` renders the styling onto a child element. Here the button styling
 * is applied to a plain anchor (would be a router `<Link/>` in the app).
 */
export const AsChildLink: Story = {
  render: (args) => (
    <Button {...args} asChild>
      <a href="#receipt/new">Нова накладна</a>
    </Button>
  ),
};
