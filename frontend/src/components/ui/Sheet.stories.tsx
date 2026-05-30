/**
 * Storybook stories for {@link Sheet}.
 *
 * Demonstrates the accessible bottom-sheet: open via a trigger, a scrollable
 * body, the labelled title/description, focus trap, Esc-to-close, and the
 * slide-up animation. This is the primitive `MappingSheet` composes with.
 */
import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react';

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from './Sheet';
import { Button } from './Button';
import { Input } from './Input';

const meta: Meta<typeof Sheet> = {
  title: 'UI/Sheet',
  component: Sheet,
  parameters: { layout: 'fullscreen' },
};

export default meta;
type Story = StoryObj<typeof Sheet>;

/** Uncontrolled: a trigger opens the sheet; Radix handles focus + Esc. */
export const Default: Story = {
  render: () => (
    <div className="p-[var(--space-6)]">
      <Sheet>
        <SheetTrigger asChild>
          <Button>Відкрити лист</Button>
        </SheetTrigger>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Прив’язати товар</SheetTitle>
            <SheetDescription>A-100 · Кабель USB-C</SheetDescription>
          </SheetHeader>
          <SheetBody>
            <Input label="Пошук у каталозі" placeholder="Артикул або назва…" />
            <ul className="mt-[var(--space-4)] flex flex-col gap-[var(--space-1)]">
              {['USB-C 1м', 'USB-C 2м', 'USB-C → Lightning'].map((name) => (
                <li
                  key={name}
                  className="rounded-[var(--radius-md)] px-[var(--space-3)] py-[var(--space-3)] hover:bg-[var(--color-surface-muted)]"
                >
                  {name}
                </li>
              ))}
            </ul>
          </SheetBody>
        </SheetContent>
      </Sheet>
    </div>
  ),
};

/** Controlled open state with a long, scrollable body. */
export const Controlled: Story = {
  render: () => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const [open, setOpen] = useState(false);
    return (
      <div className="p-[var(--space-6)]">
        <Button onClick={() => setOpen(true)}>Контрольований лист</Button>
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent>
            <SheetHeader>
              <SheetTitle>Довгий список</SheetTitle>
              <SheetDescription>Тіло прокручується незалежно.</SheetDescription>
            </SheetHeader>
            <SheetBody>
              <ul className="flex flex-col gap-[var(--space-1)]">
                {Array.from({ length: 30 }, (_, i) => (
                  <li
                    key={i}
                    className="rounded-[var(--radius-md)] px-[var(--space-3)] py-[var(--space-3)] hover:bg-[var(--color-surface-muted)]"
                  >
                    Товар №{i + 1}
                  </li>
                ))}
              </ul>
            </SheetBody>
          </SheetContent>
        </Sheet>
      </div>
    );
  },
};
