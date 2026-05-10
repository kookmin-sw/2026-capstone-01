export type AppToastVariant = "success" | "error" | "info";

export interface AppToastDetail {
  title: string;
  message?: string;
  variant?: AppToastVariant;
}

export function showAppToast(detail: AppToastDetail): void {
  window.dispatchEvent(new CustomEvent<AppToastDetail>("krip:app-toast", { detail }));
}
