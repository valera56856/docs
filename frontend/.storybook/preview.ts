/**
 * Storybook preview configuration.
 *
 * Imports the design tokens and global styles so every story renders with the
 * NextCRM palette and Inter typography — components look identical in Storybook
 * and in the running app.
 */
import type { Preview } from '@storybook/react';

import '../src/styles/tokens.css';
import '../src/styles/global.css';

const preview: Preview = {
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
      ],
    },
  },
};

export default preview;
