/** True for a listing that really came from Adzuna (sample and pasted jobs are not credited to it). */
export function fromAdzuna(job: { source: string; url: string }): boolean {
  if (job.source !== "adzuna") return false;
  try {
    return /(^|\.)adzuna\./.test(new URL(job.url).hostname);
  } catch {
    return false;
  }
}

/** The job board's terms ask for every listing it supplies to be labelled "Adzuna", linked to its site. */
export function AdzunaCredit({ className }: { className?: string }) {
  return (
    <a
      href="https://www.adzuna.ca/"
      target="_blank"
      rel="noopener noreferrer"
      className={
        className ??
        "inline-flex min-h-11 items-center text-secondary text-muted underline-offset-4 hover:underline"
      }
    >
      Jobs by Adzuna
    </a>
  );
}
