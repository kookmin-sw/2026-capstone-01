import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.krip.app',
  appName: 'Krip',
  webDir: 'dist',
  server: {
    androidScheme: 'https'
  }
};

export default config;
