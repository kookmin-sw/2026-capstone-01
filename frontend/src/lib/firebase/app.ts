import { initializeApp } from "firebase/app";
import { getAnalytics, isSupported, type Analytics } from "firebase/analytics";

export const firebaseConfig = {
  apiKey: requireFirebaseEnvironmentValue("VITE_FIREBASE_API_KEY"),
  authDomain: requireFirebaseEnvironmentValue("VITE_FIREBASE_AUTH_DOMAIN"),
  projectId: requireFirebaseEnvironmentValue("VITE_FIREBASE_PROJECT_ID"),
  storageBucket: requireFirebaseEnvironmentValue("VITE_FIREBASE_STORAGE_BUCKET"),
  messagingSenderId: requireFirebaseEnvironmentValue("VITE_FIREBASE_MESSAGING_SENDER_ID"),
  appId: requireFirebaseEnvironmentValue("VITE_FIREBASE_APP_ID"),
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
};

function requireFirebaseEnvironmentValue(key: keyof ImportMetaEnv): string {
  const value = import.meta.env[key]?.trim();
  if (!value) {
    throw new Error(`Missing required Firebase environment variable: ${key}`);
  }
  return value;
}

export const firebaseApp = initializeApp(firebaseConfig);

export const firebaseAnalytics: Promise<Analytics | null> = isSupported()
  .then((supported) => (supported ? getAnalytics(firebaseApp) : null))
  .catch(() => null);
