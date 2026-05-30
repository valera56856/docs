/**
 * Capacitor configuration.
 *
 * Wraps the built Vite SPA (`dist/`) into native iOS/Android shells so the app
 * can use the device camera and (later) biometric / secure-storage APIs that a
 * pure PWA cannot reach reliably. `cap sync` copies the web build into the
 * native projects.
 */
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'ua.nextcrm.valeraup',
  appName: 'Valeraup',
  // Vite emits the production bundle here; Capacitor packages this directory.
  webDir: 'dist',
  // NextCRM navy keeps the native splash consistent with the PWA theme color.
  backgroundColor: '#0A1A3F',
  plugins: {
    Camera: {
      // Defaults are fine; declared here so intent is explicit and discoverable.
    },
  },
};

export default config;
