import type { NavigateFunction } from "react-router-dom";

/**
 * 브라우저 히스토리가 없을 때 앱 안의 안전한 위치로 되돌린다.
 */
export function navigateBackOrFallback(
  navigate: NavigateFunction,
  fallbackPath: string
): void {
  const historyState = window.history.state as { idx?: number } | null;

  if (typeof historyState?.idx === "number" && historyState.idx > 0) {
    navigate(-1);
    return;
  }

  navigate(fallbackPath, { replace: true });
}
