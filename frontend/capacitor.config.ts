import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.krip.app',
  appName: 'Krip',
  webDir: 'dist',
  server: {
    androidScheme: 'https'
  },
  plugins: {
    CapacitorHttp: {
      enabled: true
    },
    PushNotifications: {
      presentationOptions: []
    },
    LocalNotifications: {
      presentationOptions: ["banner", "list", "sound"]
    }
  }
};

export default config;
