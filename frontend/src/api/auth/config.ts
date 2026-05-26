export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL || "https://back.krip.site";

export function readRequiredEnv(name: keyof ImportMetaEnv): string {
  const value = import.meta.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required. Configure it before building the app.`);
  }
  return value;
}

function toBearerToken(value?: string): string {
  const token = value?.trim();
  if (!token) return "";
  return token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`;
}

export const AUTHORIZATION_BEARER: string =
  toBearerToken(import.meta.env.VITE_AUTHORIZATION_BEARER);

export function getRequiredAuthorizationBearer(): string {
  return toBearerToken(readRequiredEnv("VITE_AUTHORIZATION_BEARER"));
}

export const TOUR_PLACES_AUTHORIZATION_BEARER: string =
  toBearerToken(import.meta.env.VITE_TOUR_PLACES_AUTHORIZATION_BEARER) ||
  AUTHORIZATION_BEARER;

export function getTourPlacesAuthorizationBearer(): string {
  return (
    toBearerToken(import.meta.env.VITE_TOUR_PLACES_AUTHORIZATION_BEARER) ||
    getRequiredAuthorizationBearer()
  );
}
