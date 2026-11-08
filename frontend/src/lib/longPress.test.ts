import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { attachLongPress } from "./longPress";

function touch(type: string, x: number, y: number, target: EventTarget) {
  const t = { clientX: x, clientY: y } as Touch;
  const e = new Event(type, { bubbles: true, cancelable: true }) as TouchEvent;
  Object.defineProperty(e, "touches", { value: type === "touchend" ? [] : [t] });
  target.dispatchEvent(e);
  return e;
}

describe("attachLongPress", () => {
  let el: HTMLDivElement;
  let onScrub: Mock<(x: number, y: number) => void>;
  let onClear: Mock<() => void>;
  let detach: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    el = document.createElement("div");
    document.body.appendChild(el);
    el.getBoundingClientRect = () => ({ left: 100, top: 50 }) as DOMRect;
    onScrub = vi.fn<(x: number, y: number) => void>();
    onClear = vi.fn<() => void>();
    detach = attachLongPress(el, { onScrub, onClear }, { delay: 300, tolerance: 10 });
  });
  afterEach(() => {
    detach();
    el.remove();
    vi.useRealTimers();
  });

  it("un appui bref ne déclenche rien", () => {
    touch("touchstart", 120, 80, el);
    vi.advanceTimersByTime(100);
    touch("touchend", 120, 80, el);
    vi.advanceTimersByTime(500);
    expect(onScrub).not.toHaveBeenCalled();
  });

  it("un glissement avant le délai (défilement) annule la visée et laisse défiler", () => {
    touch("touchstart", 120, 80, el);
    const move = touch("touchmove", 120, 120, el);
    vi.advanceTimersByTime(500);
    expect(onScrub).not.toHaveBeenCalled();
    expect(move.defaultPrevented).toBe(false);
  });

  it("appui long : visée à la position du doigt, puis suit le doigt sans défiler", () => {
    touch("touchstart", 120, 80, el);
    vi.advanceTimersByTime(300);
    expect(onScrub).toHaveBeenLastCalledWith(20, 30);
    const move = touch("touchmove", 160, 85, el);
    expect(move.defaultPrevented).toBe(true);
    expect(onScrub).toHaveBeenLastCalledWith(60, 35);
  });

  it("l'infobulle reste au relâchement et s'efface au toucher suivant", () => {
    touch("touchstart", 120, 80, el);
    vi.advanceTimersByTime(300);
    touch("touchend", 120, 80, el);
    expect(onClear).not.toHaveBeenCalled();
    touch("touchstart", 10, 10, document.body);
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
