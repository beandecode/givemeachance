import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { clsx } from "clsx";
import { BriefcaseBusiness, KanbanSquare, Layers, LogOut, Settings, UserRound } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys, useConfig, useSession } from "@/api/queries";
import { Dot } from "@/components/ui";
import { JourneyBar } from "@/features/journey/JourneyBar";
import { TaskTray } from "@/features/tasks/TaskTray";
import { Tour } from "@/features/tour/Tour";
import { tourSeen } from "@/features/tour/tourSteps";

import { BottomDockContext } from "./BottomDock";
import { useGlassLevel } from "./useGlassLevel";

const NAV = [
  { to: "/discover", label: "Discover", icon: Layers },
  { to: "/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { to: "/applications", label: "Applications", icon: KanbanSquare },
  { to: "/profile", label: "Profile", icon: UserRound },
  { to: "/settings", label: "Settings", icon: Settings },
];

const BANNER_LINK = "min-h-11 px-2 font-medium text-accent underline underline-offset-4";
const BANNER_BUTTON =
  "min-h-11 rounded-full bg-brand px-4 font-display text-secondary font-semibold tracking-wide text-on-brand uppercase disabled:opacity-60";

/** Phone tabs in order; the active one is found by the first segment of the path (/jobs/12 is still "jobs"). */
const TABS = NAV.filter(({ to }) => to !== "/settings");
// Written out so Tailwind sees every class (no inline style, which the CSP does not allow).
const INDICATOR_X = ["translate-x-0", "translate-x-full", "translate-x-[200%]", "translate-x-[300%]"];

function navClass({ isActive }: { isActive: boolean }) {
  return clsx(
    "flex h-10 items-center rounded-full px-4 font-display text-secondary font-semibold tracking-wide uppercase",
    "whitespace-nowrap transition-colors duration-(--duration-quick) ease-(--ease-calm)",
    isActive ? "bg-brand text-on-brand glow-yellow" : "text-muted hover:text-ink",
  );
}

export function AppShell() {
  useGlassLevel();
  const session = useSession();
  const config = useConfig();
  const queryClient = useQueryClient();
  const demo = config.data?.demo_mode === true;
  const live = config.data?.demo_live === true;
  const guest = config.data?.guest === true;
  // The tour opens by itself on a visitor's first look at the sample workspace; the banner can start it again.
  const [tour, setTour] = useState<"auto" | "open" | "closed">("auto");
  const touring = tour === "open" || (tour === "auto" && demo && !tourSeen());
  const navigate = useNavigate();
  const [dockSlot, setDockSlot] = useState<HTMLElement | null>(null);
  const dock = useRef<HTMLDivElement>(null);
  // The dock (page bar + tab bar) is fixed to the bottom; pages and sticky bars read its height from --dock-h.
  useEffect(() => {
    const node = dock.current;
    const root = document.documentElement;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() =>
      root.style.setProperty("--dock-h", `${String(node.offsetHeight)}px`),
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      root.style.removeProperty("--dock-h");
    };
  }, []);
  // Pages that fill the window (the Discover deck) also need the height of the demo banner above the header.
  const banner = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = banner.current;
    const root = document.documentElement;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (node.offsetHeight > 0) root.style.setProperty("--banner-h", `${String(node.offsetHeight)}px`);
      else root.style.removeProperty("--banner-h");
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
      root.style.removeProperty("--banner-h");
    };
  }, []);
  // The board uses the whole window up to 1600 px; every other page keeps a reading width.
  const pathname = useLocation().pathname;
  const width = pathname.startsWith("/applications") ? "max-w-[100rem]" : "max-w-6xl";
  const section = pathname.split("/")[1] ?? "";
  const activeTab = TABS.findIndex(({ to }) => to === `/${section}`);

  // The page rises in when the section changes (not on first load); the tab indicator only starts sliding after the
  // first paint, so it does not glide in from the left.
  const [route, setRoute] = useState({ section, animate: false });
  if (route.section !== section) setRoute({ section, animate: route.section !== "" });
  const [slides, setSlides] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setSlides(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const signOut = useMutation({
    mutationFn: () => unwrap(client.DELETE("/api/v1/session")),
    onSettled: () => {
      queryClient.clear();
      queryClient.setQueryData(keys.session, { user: null });
      void navigate("/login", { replace: true });
    },
  });

  // Live demo: a visitor moves between the read-only sample workspace and a guest workspace of their own.
  const switchWorkspace = useMutation({
    mutationFn: (to: "guest" | "sample") =>
      to === "guest" ? unwrap(client.POST("/api/v1/demo/guest")) : unwrap(client.DELETE("/api/v1/session")),
    onSuccess: () => {
      queryClient.clear();
      void navigate("/discover", { replace: true });
    },
  });

  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-surface focus:px-4 focus:py-3"
      >
        Skip to content
      </a>
      <div ref={banner}>
        {demo && (
          <div
            role="status"
            className="glass-plate flex flex-wrap items-center justify-center gap-x-3 gap-y-2 px-5 py-3 text-center text-secondary text-ink"
          >
            <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-warn" />
            <span>
              Read-only demo with sample data.
              <span className="hidden sm:inline">
                {" "}
                Browse freely; changes are turned off.
                {live && " Or try it with real job search and AI."}
              </span>
            </span>
            <button type="button" className={BANNER_LINK} onClick={() => setTour("open")}>
              Take the tour
            </button>
            {live && (
              <button
                type="button"
                data-tour="try-live"
                className={BANNER_BUTTON}
                disabled={switchWorkspace.isPending}
                onClick={() => switchWorkspace.mutate("guest")}
              >
                Try it live
              </button>
            )}
          </div>
        )}
        {guest && (
          <div
            role="status"
            className="glass-plate flex flex-wrap items-center justify-center gap-x-3 gap-y-2 px-5 py-3 text-center text-secondary text-ink"
          >
            <span>
              Live demo on a sample profile
              <span className="hidden sm:inline">: real job search and AI, within a small daily budget</span>.
              This workspace is deleted after 24 hours.
            </span>
            <button
              type="button"
              className={BANNER_BUTTON}
              disabled={switchWorkspace.isPending}
              onClick={() => switchWorkspace.mutate("sample")}
            >
              Back to the sample workspace
            </button>
          </div>
        )}
        {switchWorkspace.isError && (
          <p role="alert" className="px-5 py-2 text-center text-secondary text-danger">
            {describeError(switchWorkspace.error).message}
          </p>
        )}
      </div>
      <header className="glass-ctl sticky top-0 z-30 rounded-none border-x-0 border-t-0">
        <div className={clsx("mx-auto flex h-16 items-center gap-3 px-5 md:px-8", width)}>
          <NavLink
            to="/discover"
            aria-label="GivemeaChance, discover"
            className="shrink-0 font-display text-subheading tracking-wide uppercase md:text-heading md:tracking-wider"
          >
            GivemeaChance
          </NavLink>
          <nav aria-label="Main" className="hidden flex-1 items-center gap-2 pl-6 lg:flex">
            {NAV.map(({ to, label }) => (
              <NavLink key={to} to={to} className={navClass}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            {config.data?.llm_provider === "mock" && !demo && (
              <Dot
                tone="warn"
                className="hidden sm:inline-flex"
                title="Matching and job search use built-in sample data"
              >
                Sample data mode
              </Dot>
            )}
            <TaskTray />
            {!demo && !guest && (
              <span className="hidden px-2 text-secondary text-muted lg:inline">
                {session.data?.user?.username}
              </span>
            )}
            <NavLink
              to="/settings"
              aria-label="Settings"
              title="Settings"
              className="flex size-11 items-center justify-center rounded-full text-muted hover:text-ink lg:hidden"
            >
              <Settings className="size-4" aria-hidden />
            </NavLink>
            {!demo && !guest && (
              <button
                type="button"
                onClick={() => signOut.mutate()}
                className="flex size-11 items-center justify-center rounded-full text-muted hover:bg-subtle hover:text-ink"
                aria-label="Sign out"
                title="Sign out"
              >
                <LogOut className="size-4" aria-hidden />
              </button>
            )}
          </div>
        </div>
      </header>
      {touring && <Tour live={live} onClose={() => setTour("closed")} />}
      <JourneyBar />
      <BottomDockContext.Provider value={dockSlot}>
        <main
          id="main"
          className={clsx(
            "mx-auto px-5 pt-4 pb-[calc(var(--dock-h,5.5rem)+1.5rem)] md:px-8 md:pt-8 lg:pb-16",
            width,
          )}
        >
          <div key={section} className={route.animate ? "route-enter" : undefined}>
            <Outlet />
          </div>
        </main>
        <div
          ref={dock}
          id="bottom-dock"
          className="glass glass-plate fixed inset-x-0 bottom-0 z-30 rounded-t-sheet pb-[env(safe-area-inset-bottom)] lg:hidden"
        >
          <div ref={setDockSlot} />
          <nav aria-label="Main" className="relative grid grid-cols-4">
            {/* One yellow pill slides to the active tab instead of each tab having its own. */}
            <span
              aria-hidden
              className={clsx(
                "pointer-events-none absolute top-2 left-0 flex w-1/4 justify-center",
                INDICATOR_X[Math.max(activeTab, 0)],
                activeTab < 0 && "opacity-0",
                slides &&
                  "transition-[transform,opacity] duration-(--duration-slow) ease-(--ease-calm) motion-reduce:transition-none",
              )}
            >
              <span className="glow-yellow h-8 w-14 rounded-full bg-brand" />
            </span>
            {TABS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  clsx(
                    "relative flex h-[4.25rem] flex-col items-center justify-center gap-0.5 font-display text-caption font-semibold tracking-wide uppercase",
                    isActive ? "text-ink" : "text-muted",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={clsx(
                        "flex h-8 w-14 items-center justify-center rounded-full transition-colors duration-(--duration-base)",
                        isActive && "text-on-brand",
                      )}
                    >
                      <Icon className={clsx("size-5", isActive && "tab-pop")} strokeWidth={2} aria-hidden />
                    </span>
                    {label}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </div>
      </BottomDockContext.Provider>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between md:mb-8">
      <div>
        <h1 className="font-display text-title tracking-wide uppercase md:text-[2.25rem]">{title}</h1>
        {description && <p className="mt-2 text-secondary text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
