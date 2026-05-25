import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import "./PageFlip.css";

/**
 * Props:
 *  pages:        Array<{ id, imageUrl, text }>
 *  index:        current page index (controlled)
 *  onIndexChange(nextIndex, direction): called when a flip commits
 *  onFlipStart(direction) / onFlipEnd(direction):  hooks for TTS pause/resume
 *  renderPage(page, { isActive }): how to render a single page's contents
 */
export default function PageFlip({
  pages,
  index,
  onIndexChange,
  onFlipStart,
  onFlipEnd,
  renderPage,
}) {
  const [drag, setDrag] = useState(null); // { dir: -1|1, progress: 0..1, animating }
  const reduceMotion = usePrefersReducedMotion();
  const liveRef = useRef(null);
  const rootRef = useRef(null);

  const canPrev = index > 0;
  const canNext = index < pages.length - 1;

  // Preload neighbours so the reveal is never blank.
  useEffect(() => {
    [index - 1, index + 1].forEach((i) => {
      const p = pages[i];
      if (p?.imageUrl) {
        const img = new Image();
        img.src = p.imageUrl;
      }
    });
  }, [index, pages]);

  // Announce page changes to AT.
  useEffect(() => {
    if (liveRef.current) {
      liveRef.current.textContent = `Page ${index + 1} of ${pages.length}`;
    }
  }, [index, pages.length]);

  const commit = useCallback(
    (dir) => {
      const target = index + dir;
      if (target < 0 || target >= pages.length) return;
      onFlipStart?.(dir);
      if (reduceMotion) {
        onIndexChange(target, dir);
        onFlipEnd?.(dir);
        return;
      }
      setDrag({ dir, progress: 1, animating: true });
      window.setTimeout(() => {
        setDrag(null);
        onIndexChange(target, dir);
        onFlipEnd?.(dir);
        rootRef.current?.querySelector(".pf-page.is-active")?.focus?.();
      }, 520);
    },
    [index, pages.length, onIndexChange, onFlipStart, onFlipEnd, reduceMotion]
  );

  const go = useCallback(
    (dir) => {
      if (dir > 0 && canNext) commit(1);
      if (dir < 0 && canPrev) commit(-1);
    },
    [commit, canNext, canPrev]
  );

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
    };
    const el = rootRef.current;
    el?.addEventListener("keydown", onKey);
    return () => el?.removeEventListener("keydown", onKey);
  }, [go]);

  const dragState = useRef(null);
  const onPointerDown = (e) => {
    if (reduceMotion) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    dragState.current = { startX: e.clientX, width: rootRef.current.clientWidth, dir: 0 };
    rootRef.current.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    const s = dragState.current;
    if (!s) return;
    const dx = e.clientX - s.startX;
    if (Math.abs(dx) < 6) return;
    const dir = dx < 0 ? 1 : -1;
    if ((dir > 0 && !canNext) || (dir < 0 && !canPrev)) return;
    const progress = Math.min(1, Math.abs(dx) / s.width);
    s.dir = dir;
    setDrag({ dir, progress, animating: false });
  };
  const onPointerUp = () => {
    const s = dragState.current;
    dragState.current = null;
    if (!s || !s.dir) { setDrag(null); return; }
    const cur = drag?.progress ?? 0;
    if (cur > 0.4) commit(s.dir);
    else {
      setDrag({ dir: s.dir, progress: 0, animating: true });
      window.setTimeout(() => setDrag(null), 280);
    }
  };

  const current = pages[index];
  const neighbour = pages[index + (drag?.dir ?? 1)] ?? pages[index];

  const angle = drag ? drag.progress * 180 * drag.dir * -1 : 0;
  const flipStyle = {
    transform: `rotateY(${angle}deg)`,
    transition: drag?.animating ? "transform 520ms cubic-bezier(.22,.61,.36,1)" : drag ? "none" : "transform 280ms ease",
  };

  return (
    <div
      ref={rootRef}
      className={`pf-root ${reduceMotion ? "pf-reduced" : ""}`}
      tabIndex={0}
      role="region"
      aria-roledescription="storybook"
      aria-label="Story pages"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div ref={liveRef} className="pf-sr" aria-live="polite" aria-atomic="true" />

      <div className="pf-stage">
        <div className="pf-page pf-underlay" aria-hidden="true">
          {renderPage(neighbour, { isActive: false })}
        </div>

        <div
          className={`pf-page pf-active is-active ${drag ? "pf-flipping" : ""}`}
          style={flipStyle}
          tabIndex={-1}
          aria-label={`Page ${index + 1} of ${pages.length}`}
        >
          {renderPage(current, { isActive: true })}
          <div className="pf-shadow" style={{ opacity: drag ? 0.35 * drag.progress : 0 }} />
        </div>
      </div>

      <button
        className="pf-nav pf-prev"
        onClick={() => go(-1)}
        disabled={!canPrev}
        aria-label="Previous page"
      >‹</button>
      <button
        className="pf-nav pf-next"
        onClick={() => go(1)}
        disabled={!canNext}
        aria-label="Next page"
      >›</button>
    </div>
  );
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
  useLayoutEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = (e) => setReduced(e.matches);
    mq.addEventListener?.("change", handler);
    return () => mq.removeEventListener?.("change", handler);
  }, []);
  return reduced;
}
