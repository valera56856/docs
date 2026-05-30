/**
 * Storybook stories for the Toast system ({@link ToastProvider} /
 * {@link useToast} / {@link Toaster}).
 *
 * The interactive story wires a real {@link ToastProvider} + {@link Toaster}
 * and fires each variant from buttons, so reviewers can see stacking,
 * auto-dismiss, and the per-variant icons/colors. A static story renders a
 * single {@link ToastItem} for visual regression of the card itself.
 */
import type { JSX } from 'react';
import type { Meta, StoryObj } from '@storybook/react';

import {
  ToastItem,
  ToastProvider,
  useToast,
  type ToastVariant,
} from './Toast';
import { Toaster } from './Toaster';
import { Button } from './Button';

const meta: Meta = {
  title: 'UI/Toast',
  parameters: { layout: 'fullscreen' },
};

export default meta;

/** Buttons inside the provider that fire one toast of each variant. */
function ToastButtons(): JSX.Element {
  const { toast } = useToast();
  const fire = (variant: ToastVariant): void => {
    const copy: Record<ToastVariant, { title: string; description: string }> = {
      success: { title: 'Excel згенеровано', description: 'Файл готовий до завантаження.' },
      error: { title: 'Помилка завантаження', description: 'Не вдалося надіслати фото.' },
      warning: { title: 'Потрібен маппінг', description: '2 позиції не знайдено в каталозі.' },
      info: { title: 'Синхронізація', description: 'Оновлено 412 товарів.' },
    };
    toast({ variant, ...copy[variant] });
  };

  return (
    <div className="flex flex-wrap gap-[var(--space-3)] p-[var(--space-6)]">
      <Button intent="primary" onClick={() => fire('success')}>
        Success
      </Button>
      <Button intent="danger" onClick={() => fire('error')}>
        Error
      </Button>
      <Button intent="secondary" onClick={() => fire('warning')}>
        Warning
      </Button>
      <Button intent="ghost" onClick={() => fire('info')}>
        Info
      </Button>
    </div>
  );
}

/** Live, interactive toaster — click the buttons to fire toasts. */
export const Interactive: StoryObj = {
  render: () => (
    <ToastProvider>
      <ToastButtons />
      <Toaster />
    </ToastProvider>
  ),
};

/** Static render of a single toast card (no provider needed). */
export const SingleCard: StoryObj = {
  render: () => (
    <div className="max-w-sm p-[var(--space-6)]">
      <ToastItem
        toast={{
          id: 'demo',
          variant: 'success',
          title: 'Збережено',
          description: 'Відповідність запам’ятано.',
          duration: 0,
        }}
        onDismiss={() => undefined}
      />
    </div>
  ),
};
