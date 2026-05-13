export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL || "https://back.krip.site";

function toBearerToken(value?: string): string {
  const token = value?.trim();
  if (!token) return "";
  return token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`;
}

export const AUTHORIZATION_BEARER: string =
  toBearerToken(
    import.meta.env.VITE_AUTHORIZATION_BEARER || "krip3accesss1secret2token0"
  );

export const TOUR_PLACES_AUTHORIZATION_BEARER: string =
  toBearerToken(import.meta.env.VITE_TOUR_PLACES_AUTHORIZATION_BEARER) ||
  AUTHORIZATION_BEARER;
