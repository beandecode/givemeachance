import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { client, unwrap } from "@/api/client";
import { Button } from "@/components/ui";

import { INTRO_POINTS, markTourSeen, tourSteps } from "./tourSteps";

const GAP = 12; // between the spotlight and the card
const EDGE = 8; // kept free at the window edges
const PAD = 6; // the spotlight is this much larger than its element
const APPLIED = new Set(["ready", "submitted", "interview", "offer"]);

function px(value: number): string {
  return `${String(Math.round(value))}px`;
}

/**
 * First-visit tour of the sample workspace: an intro, then a spotlight that glides from screen to screen with a
 * short note at each stop. A native modal <dialog> keeps focus inside and makes the page behind inert.
 */
export function Tour({ live, onClose }: { live: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const titleId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const spot = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const next = useRef<HTMLButtonElement>(null);
  const [index, setIndex] = useState(-1); // -1 is the intro

  // A sample job that has a match report and documents, for the two stops on the job page.
  const jobs = useQuery({
    queryKey: ["tour", "jobs"],
    queryFn: () => unwrap(client.GET("/api/v1/jobs", { params: { query: { sort: "score", limit: 50 } } })),
    staleTime: Infinity,
  });
  const jobId = useMemo(() => {
    const items = jobs.data?.items ?? [];
    return (items.find((job) => APPLIED.has(job.application_status)) ?? items[0])?.id ?? null;
  }, [jobs.data]);
  const steps = useMemo(() => tourSteps(jobId, live), [jobId, live]);
  const step = index >= 0 ? steps[index] : undefined;
  const target = step?.target ?? null;
  const last = index === steps.length - 1;

  useEffect(() => {
    const node = dialog.current;
    if (node && !node.open) node.showModal();
  }, []);

  function finish() {
    markTourSeen();
    onClose();
  }

  function go(to: number) {
    const destination = steps[to];
    if (!destination) return;
    void navigate(destination.path);
    setIndex(to);
  }

  // Keep the spotlight on the element and the card next to it while the page loads, scrolls or resizes.
  useEffect(() => {
    next.current?.focus();
    let scrolled = false;
    let frame = 0;

    function place() {
      const spotNode = spot.current;
      const cardNode = card.current;
      if (!spotNode || !cardNode) return;
      const width = window.innerWidth;
      const height = window.innerHeight;
      const cardBox = cardNode.getBoundingClientRect();
      const phone = width < 640;
      const element = target ? document.querySelector(target) : null;

      if (!element) {
        // Nothing to point at (intro, last card, or the page is still loading): dim everything, centre the card.
        spotNode.classList.add("tour-spot-off");
        spotNode.style.setProperty("top", px(height / 2));
        spotNode.style.setProperty("left", px(width / 2));
        spotNode.style.setProperty("width", "0px");
        spotNode.style.setProperty("height", "0px");
        cardNode.style.setProperty("top", px(Math.max(EDGE, (height - cardBox.height) / 2)));
        cardNode.style.setProperty("left", px(Math.max(EDGE, (width - cardBox.width) / 2)));
        return;
      }
      if (!scrolled) {
        scrolled = true;
        const box = element.getBoundingClientRect();
        // Tall blocks start below the header; short ones sit in the middle (higher on phones, above the card).
        const anchor = box.height > height * 0.5 ? 150 : height * (phone ? 0.35 : 0.5) - box.height / 2;
        window.scrollTo({ top: Math.max(0, window.scrollY + box.top - anchor) });
      }
      const box = element.getBoundingClientRect();
      const floor = phone ? height - cardBox.height - EDGE - GAP : height - EDGE;
      const top = Math.max(EDGE, box.top - PAD);
      const bottom = Math.min(floor, box.bottom + PAD);
      const left = Math.max(EDGE, box.left - PAD);
      const right = Math.min(width - EDGE, box.right + PAD);
      spotNode.classList.toggle("tour-spot-off", bottom - top < 24 || right - left < 24);
      spotNode.style.setProperty("top", px(top));
      spotNode.style.setProperty("left", px(left));
      spotNode.style.setProperty("width", px(Math.max(0, right - left)));
      spotNode.style.setProperty("height", px(Math.max(0, bottom - top)));

      if (phone) {
        cardNode.style.setProperty("top", px(height - cardBox.height - EDGE));
        cardNode.style.setProperty("left", px((width - cardBox.width) / 2));
        return;
      }
      // Below the element when it fits, else above, else beside it, else over its lower corner.
      const clampX = (x: number) => Math.min(Math.max(EDGE, x), width - cardBox.width - EDGE);
      const clampY = (y: number) => Math.min(Math.max(EDGE, y), height - cardBox.height - EDGE);
      let cardTop = bottom + GAP;
      let cardLeft = clampX(left);
      if (cardTop + cardBox.height > height - EDGE) {
        if (top - GAP - cardBox.height >= EDGE) {
          cardTop = top - GAP - cardBox.height;
        } else if (right + GAP + cardBox.width <= width - EDGE) {
          cardTop = clampY(top);
          cardLeft = right + GAP;
        } else if (left - GAP - cardBox.width >= EDGE) {
          cardTop = clampY(top);
          cardLeft = left - GAP - cardBox.width;
        } else {
          cardTop = height - cardBox.height - EDGE * 2;
          cardLeft = clampX(right - cardBox.width - EDGE);
        }
      }
      cardNode.style.setProperty("top", px(cardTop));
      cardNode.style.setProperty("left", px(cardLeft));
    }

    function schedule() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
    }
    place();
    const timer = window.setInterval(place, 250); // lazy pages and loading states change the layout
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    return () => {
      window.clearInterval(timer);
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
    };
  }, [index, target]);

  return (
    <dialog
      ref={dialog}
      className="tour"
      aria-labelledby={titleId}
      onClose={finish}
      onKeyDown={(event) => {
        if (event.key === "ArrowRight" && !last) go(index + 1);
        if (event.key === "ArrowLeft" && index > 0) go(index - 1);
      }}
    >
      <div ref={spot} aria-hidden className="tour-spot tour-spot-off" />
      <div ref={card} className="tour-card glass rounded-card text-ink shadow-pop">
        <div key={index} className="tour-in glass-plate flex flex-col gap-3 rounded-[inherit] p-5">
          {step ? (
            <>
              <p className="font-mono text-caption text-muted">
                {String(index + 1)} of {String(steps.length)}
              </p>
              <h2 id={titleId} className="font-display text-heading">
                {step.title}
              </h2>
              <p className="text-secondary">{step.body}</p>
            </>
          ) : (
            <>
              <h2 id={titleId} className="font-display text-heading">
                Welcome to GivemeaChance
              </h2>
              <p className="text-secondary">
                A job-search assistant that tells you which jobs are worth your time, and why.
              </p>
              <ul className="tour-stagger flex flex-col gap-2 text-secondary">
                {INTRO_POINTS.map((point) => (
                  <li key={point} className="flex items-start gap-2">
                    <span aria-hidden className="mt-1.5 size-2 shrink-0 rounded-full bg-brand" />
                    {point}
                  </li>
                ))}
              </ul>
              <p className="text-caption text-muted">Seven stops, about a minute.</p>
            </>
          )}
          <div className="mt-1 flex items-center gap-2">
            {step && (
              <div aria-hidden className="flex gap-1.5">
                {steps.map((item, position) => (
                  <span
                    key={item.title}
                    className={clsx(
                      "h-1.5 rounded-full transition-all duration-(--duration-slow) ease-(--ease-calm)",
                      position === index ? "w-5 bg-brand" : "w-1.5 bg-line-strong",
                    )}
                  />
                ))}
              </div>
            )}
            <div className="ml-auto flex gap-2">
              {step ? (
                <>
                  {index > 0 && (
                    <Button variant="ghost" size="sm" onClick={() => go(index - 1)}>
                      Back
                    </Button>
                  )}
                  {!last && (
                    <Button variant="ghost" size="sm" onClick={finish}>
                      Skip
                    </Button>
                  )}
                  <Button
                    ref={next}
                    variant="primary"
                    size="sm"
                    onClick={() => (last ? finish() : go(index + 1))}
                  >
                    {last ? "Done" : "Next"}
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="ghost" size="sm" onClick={finish}>
                    Skip
                  </Button>
                  <Button ref={next} variant="primary" size="sm" onClick={() => go(0)}>
                    Take the tour
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </dialog>
  );
}
