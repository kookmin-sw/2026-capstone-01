import type { NavigateFunction } from "react-router-dom";

const LAST_TAB_KEY = "krip:last-tab";

/**
 * AppShell에서 탭 루트 경로를 방문할 때마다 호출해 마지막 탭을 기록한다.
 */
export function recordLastTab(tabPath: string): void {
  sessionStorage.setItem(LAST_TAB_KEY, tabPath);
}

/**
 * 뒤로가기: 마지막으로 방문한 탭으로 이동한다.
 * 기록이 없으면 fallbackPath로 이동한다.
 */
export function navigateBackOrFallback(
  navigate: NavigateFunction,
  fallbackPath: string
): void {
  const lastTab = sessionStorage.getItem(LAST_TAB_KEY);
  navigate(lastTab ?? fallbackPath, { replace: true });
}
