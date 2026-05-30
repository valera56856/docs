/**
 * Storybook stories for {@link Input}.
 *
 * Documents the label, hint, error, and disabled states plus the
 * `labelHidden` variant. Stories double as a visual regression surface and
 * living API documentation; flip the theme toolbar to verify dark mode.
 */
import type { Meta, StoryObj } from '@storybook/react';

import { Input } from './Input';

const meta: Meta<typeof Input> = {
  title: 'UI/Input',
  component: Input,
  parameters: { layout: 'padded' },
  argTypes: {
    label: { control: 'text' },
    error: { control: 'text' },
    hint: { control: 'text' },
    disabled: { control: 'boolean' },
    labelHidden: { control: 'boolean' },
    placeholder: { control: 'text' },
  },
  args: {
    label: 'Артикул',
    placeholder: 'Напр. A-100',
  },
};

export default meta;
type Story = StoryObj<typeof Input>;

/** Default labelled field. */
export const Default: Story = {};

/** With helper text below the field. */
export const WithHint: Story = {
  args: { hint: 'Введіть артикул постачальника як на накладній.' },
};

/** Error state: danger border + announced message. */
export const WithError: Story = {
  args: { error: 'PIN має містити рівно 4 цифри.' },
};

/** Numeric-style field (e.g. PIN entry). */
export const Numeric: Story = {
  args: {
    label: 'PIN',
    placeholder: '••••',
    inputMode: 'numeric',
    maxLength: 4,
  },
};

/** Visually-hidden label (still read by screen readers). */
export const LabelHidden: Story = {
  args: { labelHidden: true, placeholder: 'Пошук у каталозі…' },
};

/** Disabled. */
export const Disabled: Story = { args: { disabled: true, value: 'A-100' } };
