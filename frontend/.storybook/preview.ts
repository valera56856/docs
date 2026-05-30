/**
 * Storybook preview configuration.
 *
 * Imports the design tokens and global styles so every story renders with the
 * NextCRM palette and Inter typography — components look identical in Storybook
 * and in the running app.
 *
 * THEME TOOLBAR: a global `theme` toolbar (light/dark) sets `data-theme` on the
 * story's `<html>` via a decorator, mirroring what `ThemeProvider` does in the
 * app. This lets every component be reviewed in both themes from one control,
 * and keeps the Storybook background in sync with the active theme.
 */
import type { Decorator, Preview } from '@storybook/react';
import { useEffect } from 'react';

import '../src/styles/tokens.css';
import '../src/styles/global.css';

/** Apply the selected theme to <html> for the duration of the story. */
const withTheme: Decorator = (Story, context) => {
  const theme = (context.globals.theme as 'light' | 'dark') ?? 'light';
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    // Keep the Storybook canvas background readable in each theme.
    document.body.style.backgroundColor =
      theme === 'dark' ? '#070d1c' : '#f8fafc';
    return () => root.removeAttribute('data-theme');
  }, [theme]);
  return Story();
};

const preview: Preview = {
  decorators: [withTheme],
  globalTypes: {
    theme: {
      description: 'Light / dark theme',
      defaultValue: 'light',
      toolbar: {
        title: 'Theme',
        icon: 'circlehollow',
        items: [
          { value: 'light', title: 'Light', icon: 'sun' },
          { value: 'dark', title: 'Dark', icon: 'moon' },
        ],
        dynamicTitle: true,
      },
    },
  },
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: 'app',
      values: [
        { name: 'app', value: '#F8FAFC' },
        { name: 'navy', value: '#0A1A3F' },
        { name: 'dark', value: '#070D1C' },
      ],
    },
  },
};

export default preview;
