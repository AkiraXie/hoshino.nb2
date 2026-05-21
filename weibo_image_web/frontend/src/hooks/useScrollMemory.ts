import { useEffect, useRef } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

/* Disable browser's built-in scroll restoration so we have full control */
if (typeof window !== "undefined" && "scrollRestoration" in history) {
  history.scrollRestoration = "manual";
}

function keyFor(pathname: string, search: string) {
  return `scroll:${pathname}${search}`;
}

/* ── ScrollToTop ─────────────────────────────────────────────────
 * Global component – mount once inside <BrowserRouter>.
 * Scrolls to top on PUSH / REPLACE; leaves POP to useScrollMemory.
 */
export function ScrollToTop() {
  const { pathname, search } = useLocation();
  const navType = useNavigationType();

  useEffect(() => {
    if (navType !== "POP") window.scrollTo(0, 0);
  }, [pathname, search, navType]);

  return null;
}

/* ── useScrollMemory ─────────────────────────────────────────────
 * Per-page hook. Auto-saves scrollY on every scroll event (rAF-throttled),
 * and restores the position on POP navigation once `ready` is true.
 */
export function useScrollMemory(ready: boolean) {
  const { pathname, search } = useLocation();
  const navType = useNavigationType();
  const key = keyFor(pathname, search);

  // Capture restore target synchronously so the scroll listener can't race
  const targetRef = useRef(
    navType === "POP" ? Number(sessionStorage.getItem(key) || "0") : 0,
  );
  const restoredRef = useRef(false);
  const canSaveRef = useRef(navType !== "POP");

  // Reset on route change
  useEffect(() => {
    targetRef.current =
      navType === "POP" ? Number(sessionStorage.getItem(key) || "0") : 0;
    restoredRef.current = false;
    canSaveRef.current = navType !== "POP";
  }, [key, navType]);

  // Auto-save scroll position.
  // Track latest Y in a local var (synchronous = always fresh),
  // flush to sessionStorage periodically + on cleanup (before ScrollToTop fires).
  useEffect(() => {
    let latestY = Math.round(window.scrollY);
    let timer: ReturnType<typeof setInterval> | undefined;

    function onScroll() {
      if (!canSaveRef.current) return;
      latestY = Math.round(window.scrollY);
    }

    // Flush to storage every 300ms (cheap writes, avoids per-frame overhead)
    timer = setInterval(() => {
      if (canSaveRef.current) {
        sessionStorage.setItem(key, String(latestY));
      }
    }, 300);

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      clearInterval(timer);
      // Flush the *exact* latest value synchronously on unmount,
      // BEFORE ScrollToTop's effect fires scrollTo(0,0).
      if (canSaveRef.current) {
        sessionStorage.setItem(key, String(latestY));
      }
    };
  }, [key]);

  // Restore on POP once content is ready
  useEffect(() => {
    if (restoredRef.current || navType !== "POP" || !ready) return;
    restoredRef.current = true;

    const targetY = targetRef.current;
    if (targetY <= 0) {
      canSaveRef.current = true;
      return;
    }

    let rafId: number;
    let observer: MutationObserver | null = null;
    let done = false;

    function tryScroll(): boolean {
      if (done) return true;
      const maxScroll =
        document.documentElement.scrollHeight - window.innerHeight;
      if (maxScroll >= targetY) {
        window.scrollTo(0, targetY);
        finish();
        return true;
      }
      return false;
    }

    function finish() {
      done = true;
      cancelAnimationFrame(rafId);
      observer?.disconnect();
      // Let the scroll land, then allow saving again
      requestAnimationFrame(() => {
        canSaveRef.current = true;
      });
    }

    // Try immediately
    if (tryScroll()) return;

    // MutationObserver: triggers as soon as new children render
    observer = new MutationObserver(() => tryScroll());
    observer.observe(document.body, { childList: true, subtree: true });

    // rAF polling fallback (~3 s at 60 fps)
    let attempts = 0;
    function poll() {
      if (done) return;
      if (tryScroll()) return;
      if (++attempts < 180) {
        rafId = requestAnimationFrame(poll);
      } else {
        window.scrollTo(0, targetY);
        finish();
      }
    }
    rafId = requestAnimationFrame(poll);

    return () => {
      if (!done) finish();
    };
  }, [key, navType, ready]);
}

export const useScrollRestore = useScrollMemory;
