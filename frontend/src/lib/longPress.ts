/**
 * Appui long « visée » pour les graphiques tactiles.
 *
 * Un appui bref ou un glissement vertical garde le comportement normal (clic, défilement de la page).
 * Un doigt maintenu immobile `delay` ms active le mode visée : la page ne défile plus, `onScrub` est appelé
 * avec la position du doigt (relative à l'élément) au départ puis à chaque déplacement. Au relâchement
 * l'infobulle reste affichée ; `onClear` est appelé au toucher suivant (n'importe où).
 */
export interface LongPressHandlers {
  onScrub: (x: number, y: number) => void;
  onClear: () => void;
}

export interface LongPressOptions {
  delay?: number;
  /** Déplacement toléré (px) pendant l'attente avant d'abandonner (c'est un défilement). */
  tolerance?: number;
}

export function attachLongPress(el: HTMLElement, h: LongPressHandlers, opts: LongPressOptions = {}): () => void {
  const delay = opts.delay ?? 350;
  const tolerance = opts.tolerance ?? 10;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let active = false;
  let shown = false;
  let startX = 0;
  let startY = 0;
  let lastX = 0;
  let lastY = 0;

  const cancelTimer = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };
  const scrub = (cx: number, cy: number) => {
    const r = el.getBoundingClientRect();
    h.onScrub(cx - r.left, cy - r.top);
  };
  const clear = () => {
    if (!shown) return;
    shown = false;
    h.onClear();
  };

  const start = (e: TouchEvent) => {
    cancelTimer();
    clear();
    if (e.touches.length !== 1) return;
    const t = e.touches[0];
    startX = lastX = t.clientX;
    startY = lastY = t.clientY;
    timer = setTimeout(() => {
      timer = null;
      active = shown = true;
      navigator.vibrate?.(10);
      scrub(lastX, lastY);
    }, delay);
  };
  const move = (e: TouchEvent) => {
    const t = e.touches[0];
    if (!t) return;
    lastX = t.clientX;
    lastY = t.clientY;
    if (active) {
      if (e.cancelable) e.preventDefault(); // plus de défilement pendant la visée
      scrub(lastX, lastY);
    } else if (timer !== null && Math.hypot(lastX - startX, lastY - startY) > tolerance) {
      cancelTimer();
    }
  };
  const end = (e: TouchEvent) => {
    cancelTimer();
    if (active) {
      active = false;
      if (e.cancelable) e.preventDefault(); // évite les évènements souris synthétiques qui effaceraient l'infobulle
    }
  };
  const swallowMenu = (e: Event) => {
    if (active || timer !== null) e.preventDefault(); // menu contextuel du système sur appui long
  };

  el.addEventListener("touchstart", start, { passive: true });
  el.addEventListener("touchmove", move, { passive: false });
  el.addEventListener("touchend", end, { passive: false });
  el.addEventListener("touchcancel", end, { passive: false });
  el.addEventListener("contextmenu", swallowMenu);
  // toucher ailleurs : efface l'infobulle laissée affichée
  const outside = (e: TouchEvent) => {
    if (!el.contains(e.target as Node)) clear();
  };
  document.addEventListener("touchstart", outside, { passive: true });

  return () => {
    cancelTimer();
    el.removeEventListener("touchstart", start);
    el.removeEventListener("touchmove", move);
    el.removeEventListener("touchend", end);
    el.removeEventListener("touchcancel", end);
    el.removeEventListener("contextmenu", swallowMenu);
    document.removeEventListener("touchstart", outside);
  };
}
