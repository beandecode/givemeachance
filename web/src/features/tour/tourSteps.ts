/** One stop of the first-visit tour: a page, the element to point at, and what to say about it. */
export interface TourStep {
  path: string;
  /** CSS selector of the element to spotlight; null shows the card in the middle of the screen. */
  target: string | null;
  title: string;
  body: string;
}

const STORAGE_KEY = "gmc.tour.v2"; // v2 added the résumé and gap-question stops

/** True once the visitor has finished or skipped the tour (or when the browser refuses storage). */
export function tourSeen(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "done";
  } catch {
    return true;
  }
}

export function markTourSeen(): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, "done");
  } catch {
    // Storage is off: the tour simply shows again next time.
  }
}

export const INTRO_POINTS = [
  "Scores every job against one profile you have reviewed",
  "Lets you decide with a swipe",
  "Writes a résumé it can back up with facts",
];

/** The stops, in order. `jobId` is a sample job that already has a match report and documents. */
export function tourSteps(jobId: number | null, live: boolean): TourStep[] {
  const job = jobId === null ? "/jobs" : `/jobs/${String(jobId)}`;
  return [
    {
      path: "/discover",
      target: '[data-tour="deck"]',
      title: "Decide in seconds",
      body: "Your best new matches arrive as a deck. Swipe right to have a résumé written, left to skip, up to keep a job for later. Arrow keys and buttons work too.",
    },
    {
      path: "/jobs",
      target: '[data-tour="jobs"]',
      title: "Every job, ranked",
      body: "Each posting is scored against your profile. The number is added up in code from five rated dimensions, so the same job always gets the same score.",
    },
    {
      path: job,
      target: '[data-tour="match"]',
      title: "Why it fits",
      body: "Strengths, gaps and risks are spelled out for each job, so you can judge the score instead of trusting it.",
    },
    {
      path: job,
      target: '[data-tour="document"]',
      title: "A résumé for this job",
      body: "Documents are written only for jobs you pick. Every claim is checked against your profile, and anything unsupported is listed. Export to PDF or Word.",
    },
    {
      path: "/applications",
      target: '[data-tour="board"]',
      title: "Track every application",
      body: "From draft to offer in one place, with a follow-up date so nothing goes quiet.",
    },
    {
      path: "/onboarding?step=background",
      target: '[data-tour="resume-input"]',
      title: "Start from any résumé",
      body: "Paste it, or attach a PDF, a Word file or screenshots. Here you can open a sample résumé in each format; in the live demo you can build a profile from it.",
    },
    {
      path: "/profile",
      target: '[data-tour="profile"]',
      title: "One reviewed profile",
      body: "The résumé becomes a structured profile that you check and approve. Scores and documents use only what is in it, so nothing is invented.",
    },
    {
      path: "/profile",
      target: '[data-tour="gaps"]',
      title: "Fill the gaps",
      body: "What is missing becomes a short question, most of all a result without a number. Each answer lands on the job or project it is about.",
    },
    live
      ? {
          path: "/discover",
          target: '[data-tour="try-live"]',
          title: "Now try it for real",
          body: "Start a guest workspace: search the real job board, get real scores and have a real résumé written for a sample profile.",
        }
      : {
          path: "/discover",
          target: null,
          title: "That is the tour",
          body: "This is a read-only sample workspace. Look around freely: nothing you open here changes anything.",
        },
  ];
}
