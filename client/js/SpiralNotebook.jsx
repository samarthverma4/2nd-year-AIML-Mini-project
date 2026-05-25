import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import "./SpiralNotebook.css";

/**
 * SpiralNotebook — right-bound storybook with pastel spiral coils as the hinge.
 *
 * Props:
 *   pages:          Array<{ id?, imageUrl, text, ... }>
 *   index:          current page index (controlled)
 *   onIndexChange(nextIndex, direction): commit handler
 *   onFlipStart(direction) / onFlipEnd(direction, newIndex): TTS pause/resume hooks
 *   renderPage(page, { isActive }):   how to render a page's contents
 *   rings:          how many spiral coils to draw (default 14)
 */
export default function SpiralNotebook({
  pages,
  index,
  onIndexChange,
  onFlipStart,
  onFlipEnd,
  renderPage,
  rings = 14,
}) {
  const [drag, setDrag] = useState(null); // { dir, progress, animating }
  const reduceMotion = usePrefersReducedMotion();
  const rootRef = useRef(null);
  const liveRef = useRef(null);
  const dragRef = useRef(null);
  const animTimer = useRef(null);

  const canPrev = index > 0;
  const canNext = index < pages.length - 1;

  // Preload adjacent pages so the reveal is never blank.
  useEffect(() => {
    [index - 1, index + 1].forEach((i) => {
      const p = pages[i];
      if (p?.imageUrl) { const im = new Image(); im.src = p.imageUrl; }
    });
  }, [index, pages]);

  // SR announcement.
  useEffect(() => {
    if (liveRef.current) liveRef.current.textContent = `Page ${index + 1} of ${pages.length}`;
  }, [index, pages.length]);

  const commit = useCallback((dir) => {
    const target = index + dir;
    if (target < 0 || target >= pages.length) return;
    onFlipStart?.(dir);
    if (reduceMotion) {
      onIndexChange(target, dir);
      onFlipEnd?.(dir, target);
      return;
    }
    setDrag({ dir, progress: 1, animating: true });
    clearTimeout(animTimer.current);
    animTimer.current = setTimeout(() => {
      setDrag(null);
      onIndexChange(target, dir);
      onFlipEnd?.(dir, target);
      rootRef.current?.querySelector(".sn-page.sn-active")?.focus?.({ preventScroll: true });
    }, 540);
  }, [index, pages.length, onIndexChange, onFlipStart, onFlipEnd, reduceMotion]);

  const go = useCallback((dir) => {
    if (dir > 0 && canNext) commit(1);
    else if (dir < 0 && canPrev) commit(-1);
  }, [commit, canNext, canPrev]);

  useEffect(() => {
    const onKey = (e) => {
      const t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
    };
    const el = rootRef.current;
    el?.addEventListener("keydown", onKey);
    return () => el?.removeEventListener("keydown", onKey);
  }, [go]);

  const onPointerDown = (e) => {
    if (reduceMotion) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    if (e.target.closest("button, a, input, select, textarea")) return;
    dragRef.current = { startX: e.clientX, width: rootRef.current.clientWidth || 1, dir: 0 };
    try { rootRef.current.setPointerCapture(e.pointerId); } catch (_) {}
  };
  const onPointerMove = (e) => {
    const s = dragRef.current; if (!s) return;
    const dx = e.clientX - s.startX;
    if (Math.abs(dx) < 6) return;
    const dir = dx < 0 ? 1 : -1; // drag-left = next
    if ((dir > 0 && !canNext) || (dir < 0 && !canPrev)) return;
    s.dir = dir;
    setDrag({ dir, progress: Math.min(1, Math.abs(dx) / s.width), animating: false });
  };
  const onPointerUp = () => {
    const s = dragRef.current; dragRef.current = null;
    if (!s || !s.dir) { setDrag(null); return; }
    const progress = drag?.progress ?? 0;
    if (progress > 0.4) commit(s.dir);
    else {
      setDrag({ dir: s.dir, progress: 0, animating: true });
      clearTimeout(animTimer.current);
      animTimer.current = setTimeout(() => setDrag(null), 280);
    }
  };

  const current = pages[index];
  const neighbour = pages[index + (drag?.dir ?? 1)] ?? pages[index];

  // Pages rotate around the RIGHT edge (the spiral hinge).
  // Going next = negative rotation (page swings out to the left).
  const angle = drag ? drag.progress * 180 * -drag.dir : 0;
  const flipStyle = {
    transform: `rotateY(${angle}deg)`,
    transition: drag?.animating
      ? "transform 540ms cubic-bezier(.22,.61,.36,1)"
      : drag ? "none"
      : "transform 280ms ease",
  };

  return (
    <div
      ref={rootRef}
      className={`sn-root ${reduceMotion ? "sn-reduced" : ""}`}
      tabIndex={0}
      role="region"
      aria-roledescription="storybook"
      aria-label="Spiral-bound storybook"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div ref={liveRef} className="sn-sr" aria-live="polite" aria-atomic="true" />

      <div className="sn-stage">
        <div className="sn-page sn-underlay" aria-hidden="true">
          <PageBody>{renderPage(neighbour, { isActive: false })}</PageBody>
        </div>

        <div
          className={`sn-page sn-active ${drag ? "sn-flipping" : ""}`}
          style={flipStyle}
          tabIndex={-1}
          aria-label={`Page ${index + 1} of ${pages.length}`}
        >
          <PageBody>{renderPage(current, { isActive: true })}</PageBody>
          <div className="sn-curl" style={{ opacity: drag ? 0.45 * drag.progress : 0 }} />
        </div>
      </div>

      <SpiralBinding rings={rings} />

      <button className="sn-nav sn-prev" onClick={() => go(-1)} disabled={!canPrev} aria-label="Previous page">‹</button>
      <button className="sn-nav sn-next" onClick={() => go(1)}  disabled={!canNext} aria-label="Next page">›</button>
    </div>
  );
}

function PageBody({ children }) {
  return (
    <>
      <div className="sn-content">{children}</div>
      <div className="sn-binding-margin" aria-hidden="true">
        <div className="sn-holes">
          {Array.from({ length: 14 }).map((_, i) => (
            <span key={i} className="sn-hole" />
          ))}
        </div>
      </div>
    </>
  );
}

/* Pastel spiral coils. Each ring is drawn as two arcs (front + back)
 * so it reads as threaded through the page punch holes. SVG keeps it
 * crisp at any size; pastel gradient + soft blur sells the Ghibli feel. */
function SpiralBinding({ rings }) {
  const H = rings * 40;
  return (
    <svg
      className="sn-spiral"
      viewBox={`0 0 60 ${H}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="sn-ring-front" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"   stopColor="#f7e0ec" />
          <stop offset="55%"  stopColor="#e6bfd5" />
          <stop offset="100%" stopColor="#c89bbb" />
        </linearGradient>
        <linearGradient id="sn-ring-highlight" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="rgba(255,255,255,.85)" />
          <stop offset="100%" stopColor="rgba(255,255,255,0)" />
        </linearGradient>
        <filter id="sn-soft" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation=".55" />
        </filter>
      </defs>

      {Array.from({ length: rings }).map((_, i) => {
        const y = (i + 0.5) * 40;
        return (
          <g key={i}>
            {/* Back of the ring — behind the page, soft and faint */}
            <path
              d={`M 22 ${y - 9} Q 50 ${y} 22 ${y + 9}`}
              fill="none"
              stroke="#b58aa7"
              strokeWidth="2.5"
              strokeLinecap="round"
              opacity=".4"
            />
            {/* Front of the ring — in front of the page */}
            <path
              d={`M 22 ${y - 9} Q 4 ${y} 22 ${y + 9}`}
              fill="none"
              stroke="url(#sn-ring-front)"
              strokeWidth="3.6"
              strokeLinecap="round"
              filter="url(#sn-soft)"
            />
            {/* Soft highlight on the front loop for gentle 3D */}
            <path
              d={`M 19 ${y - 5} Q 11 ${y - 1} 16 ${y + 3}`}
              fill="none"
              stroke="url(#sn-ring-highlight)"
              strokeWidth="1.3"
              strokeLinecap="round"
            />
          </g>
        );
      })}
    </svg>
  );
}

function usePrefersReducedMotion() {
  const [r, setR] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
  useLayoutEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const h = (e) => setR(e.matches);
    mq.addEventListener?.("change", h);
    return () => mq.removeEventListener?.("change", h);
  }, []);
  return r;
}
