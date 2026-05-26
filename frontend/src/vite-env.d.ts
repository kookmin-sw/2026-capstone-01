/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_AUTHORIZATION_BEARER?: string;
  readonly VITE_TOUR_PLACES_AUTHORIZATION_BEARER?: string;
  readonly VITE_AUTH_IS_LOCAL?: string;
  readonly VITE_DEBUG_AUTH_LOG?: string;
  readonly VITE_DEBUG_FCM_LOG?: string;
  readonly VITE_KAKAO_JS_KEY?: string;
  readonly VITE_LEGACY_TOKEN_STORAGE_KEY?: string;
  readonly VITE_FIREBASE_API_KEY?: string;
  readonly VITE_FIREBASE_AUTH_DOMAIN?: string;
  readonly VITE_FIREBASE_PROJECT_ID?: string;
  readonly VITE_FIREBASE_STORAGE_BUCKET?: string;
  readonly VITE_FIREBASE_MESSAGING_SENDER_ID?: string;
  readonly VITE_FIREBASE_APP_ID?: string;
  readonly VITE_FIREBASE_MEASUREMENT_ID?: string;
  readonly VITE_FIREBASE_VAPID_KEY?: string;
  readonly VITE_FCM_REGISTER_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
