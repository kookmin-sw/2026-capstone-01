import { useEffect } from "react";

type ScrollLockSnapshot = {
  bodyOverflow: string;
  bodyPaddingRight: string;
  bodyPosition: string;
  bodyTop: string;
  bodyTouchAction: string;
  bodyWidth: string;
  htmlOverflow: string;
  scrollY: number;
};

let activeLockCount = 0;
let snapshot: ScrollLockSnapshot | null = null;

function lockBodyScroll(): () => void {
  if (typeof document === "undefined" || typeof window === "undefined") {
    return () => undefined;
  }

  activeLockCount += 1;

  if (activeLockCount === 1) {
    const { body, documentElement } = document;
    const scrollY = window.scrollY || documentElement.scrollTop || 0;
    const scrollbarWidth = window.innerWidth - documentElement.clientWidth;

    snapshot = {
      bodyOverflow: body.style.overflow,
      bodyPaddingRight: body.style.paddingRight,
      bodyPosition: body.style.position,
      bodyTop: body.style.top,
      bodyTouchAction: body.style.touchAction,
      bodyWidth: body.style.width,
      htmlOverflow: documentElement.style.overflow,
      scrollY,
    };

    documentElement.style.overflow = "hidden";
    body.style.overflow = "hidden";
    body.style.touchAction = "none";
    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.width = "100%";

    if (scrollbarWidth > 0) {
      body.style.paddingRight = `${scrollbarWidth}px`;
    }
  }

  return () => {
    activeLockCount = Math.max(0, activeLockCount - 1);
    if (activeLockCount > 0 || !snapshot) return;

    const { body, documentElement } = document;
    const restoreScrollY = snapshot.scrollY;

    documentElement.style.overflow = snapshot.htmlOverflow;
    body.style.overflow = snapshot.bodyOverflow;
    body.style.touchAction = snapshot.bodyTouchAction;
    body.style.position = snapshot.bodyPosition;
    body.style.top = snapshot.bodyTop;
    body.style.width = snapshot.bodyWidth;
    body.style.paddingRight = snapshot.bodyPaddingRight;
    snapshot = null;

    window.scrollTo(0, restoreScrollY);
  };
}

export function useBodyScrollLock(active: boolean): void {
  useEffect(() => {
    if (!active) return undefined;
    return lockBodyScroll();
  }, [active]);
}
