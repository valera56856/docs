/**
 * Storybook main configuration.
 *
 * Uses the Vite builder so stories share the exact same module resolution,
 * aliases, and plugin pipeline as the app. Component stories live next to their
 * components as `*.stories.tsx` (e.g. src/components/ui/Button.stories.tsx).
 */
import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-essentials'],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  docs: {
    autodocs: 'tag',
  },
};

export default config;
