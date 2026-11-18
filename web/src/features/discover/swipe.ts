import type { CSSProperties, PointerEvent } from "react";
import { useRef, useState } from "react";

export type Direction = "left" | "right" | "up" | "down";
export const DIRECTIONS: Direction[] = ["left", "up", "down", "right"];

/** How far (px) a drag must travel before it counts as a decision. */
export const COMMIT_DISTANCE = 96;
/** A short, fast flick also counts: at least this far and faster than FLICK_SPEED px per ms. */
const FLICK_MIN_DISTANCE = 40;
const FLICK_SPEED = 0.6;
/** From this distance the matching stamp starts to show while dragging. */
const HINT_DISTANCE = 36;

/** Dominant-axis direction of a movement, or null while it is shorter than `minDistance`. */
export function directionOf(dx: number, dy: number, minDistance = COMMIT_DISTANCE): Direction | null {
  const ax = Math.abs(dx);
  const ay = Math.abs(dy);
  if (Math.max(ax, ay) < minDistance) return null;
  if (ax >= ay) return dx > 0 ? "right" : "left";
  return dy > 0 ? "down" : "up";
}

/** The direction of a released drag: far enough, or a quick flick. */
export function releaseDirection(dx: number, dy: number, elapsedMs: number): Direction | null {
  const far = directionOf(dx, dy);
  if (far) return far;
  const distance = Math.hypot(dx, dy);
  if (distance >= FLICK_MIN_DISTANCE && distance / Math.max(elapsedMs, 1) > FLICK_SPEED) {
    return directionOf(dx, dy, FLICK_MIN_DISTANCE);
  }
  return null;
}

interface SwipeOptions {
  enabled: boolean;
  /** Mouse dragging is a setting; touch and pen always work. */
  allowMouse: boolean;
  onCommit: (direction: Direction) => void;
}

/**
 * Pointer-event drag for the deck card (no gesture library). The card follows the pointer, tilts, shows a hint of
 * the pending direction and rubber-bands back unless the release commits a decision.
 */
export function useSwipe({ enabled, allowMouse, onCommit }: SwipeOptions) {
  const origin = useRef<{ x: number; y: number; time: number } | null>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);

  function reset() {
    origin.current = null;
    setDragging(false);
    setOffset({ x: 0, y: 0 });
  }

  const handlers = {
    onPointerDown(event: PointerEvent<HTMLElement>) {
      if (!enabled) return;
      if (event.pointerType === "mouse" && (!allowMouse || event.button !== 0)) return;
      origin.current = { x: event.clientX, y: event.clientY, time: event.timeStamp };
      setDragging(true);
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    onPointerMove(event: PointerEvent<HTMLElement>) {
      const start = origin.current;
      if (!start) return;
      setOffset({ x: event.clientX - start.x, y: event.clientY - start.y });
    },
    onPointerUp(event: PointerEvent<HTMLElement>) {
      const start = origin.current;
      if (!start) return;
      const direction = releaseDirection(
        event.clientX - start.x,
        event.clientY - start.y,
        event.timeStamp - start.time,
      );
      reset();
      if (direction) onCommit(direction);
    },
    onPointerCancel: reset,
  };

  const style: CSSProperties = {
    transform: `translate(${String(offset.x)}px, ${String(offset.y)}px) rotate(${String(offset.x / 24)}deg)`,
    transition: dragging ? "none" : "transform 220ms var(--ease-calm)",
  };
  return {
    handlers,
    style,
    dragging,
    hint: dragging ? directionOf(offset.x, offset.y, HINT_DISTANCE) : null,
  };
}
