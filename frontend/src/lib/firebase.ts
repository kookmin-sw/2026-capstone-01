import { initializeApp } from "firebase/app";
import { getAnalytics, isSupported, type Analytics } from "firebase/analytics";

export const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "AIzaSyCNhoADPVfV74tbb9WI9i2eJha7RY4FsyM",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "krip-a4d7d.firebaseapp.com",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "krip-a4d7d",
  storageBucket:
    import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "krip-a4d7d.firebasestorage.app",
  messagingSenderId:
    import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "149172625115",
  appId:
    import.meta.env.VITE_FIREBASE_APP_ID ||
    "1:149172625115:web:6a337f849a08826243f6fe",
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID || "G-KVHM5PW0MC",
};

export const firebaseApp = initializeApp(firebaseConfig);

export const firebaseAnalytics: Promise<Analytics | null> = isSupported()
  .then((supported) => (supported ? getAnalytics(firebaseApp) : null))
  .catch(() => null);
  
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);