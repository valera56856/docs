/**
 * Storybook stories for {@link EmptyState}.
 *
 * Covers the three real uses: an empty supplier list, a no-results search, and
 * an error/recovery surface with a retry action button.
 */
import type { Meta, StoryObj } from '@storybook/react';
import { Inbox, SearchX, WifiOff } from 'lucide-react';

import { EmptyState } from './EmptyState';
import { Button } from './Button';

const meta: Meta<typeof EmptyState> = {
  title: 'UI/EmptyState',
  component: EmptyState,
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj<typeof EmptyState>;

/** Empty list (no suppliers yet). */
export const NoData: Story = {
  args: {
    icon: Inbox,
    title: 'Постачальників ще немає',
    hint: 'Додайте постачальника в адмін-панелі, щоб почати приймати накладні.',
  },
};

/** Search with no results. */
export const NoResults: Story = {
  args: {
    icon: SearchX,
    title: 'Нічого не знайдено',
    hint: 'Спробуйте інший артикул або частину назви.',
  },
};

/** Error/recovery state with a retry action. */
export const WithAction: Story = {
  args: {
    icon: WifiOff,
    title: 'Не вдалося завантажити',
    hint: 'Перевірте з’єднання та спробуйте ще раз.',
    action: <Button intent="secondary">Спробувати ще раз</Button>,
  },
};
