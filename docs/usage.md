# Usage Guide

How to use GivemeaChance day to day. Setup and deployment: [operations.md](operations.md).

## Web app (`/app`)

The interface lives at `/app` (`http://127.0.0.1:5001/` redirects there).

- **Setup** (first sign-in): six steps. Paste or attach your résumé → check the generated profile, answer any
  questions it could not answer, approve → confirm what to search for (prefilled from your profile) → run your first
  search → pick jobs in Discover → write your first résumé. It resumes where you left off. After setup a bar under the
  header shows the next step until you have marked a job as applied; the cross hides it.
- **Discover** (home after setup): your best new matches as a deck of cards.
  - Swipe a card, press the arrow keys or use the buttons: right writes a résumé, left skips, up puts the job on the
    waitlist, down opens the full job page. `U` or Undo takes back the last decision.
  - After a skip you can tap why (too senior, wrong field, ...); when the same reason repeats, the search sheet
    suggests a change, applied only when you press Apply.
  - Only jobs at or above your score threshold appear (default 70). When the deck is empty it says why and offers the
    matching action. If three documents are already being written, a new résumé starts when a slot is free.
  - Settings → Discover deck sets the four directions, the threshold, the drag and button toggles and the glass
    effect (automatic, or a fixed level: strong glass costs battery on slow phones).
- **Search results**: when a search finishes the message says how many new jobs were found, how many were scored, and
  how many were not scored (daily AI limit reached, full description unavailable, or left for later), already saved, or
  skipped by level.
- **Full postings only**: the job board's search returns a short preview, so the app reads each posting in full from
  the job board before scoring it. When that is not possible the job waits under Not scored and its page asks you to
  paste the full description. Listings from the job board are marked "via Adzuna".
- **Jobs**: search the job board or paste a job from anywhere; filter by status, score or text; open a job. The
  All / Waitlist / Skipped / Not scored switch shows what you parked in Discover (with "Back to Discover" to return a
  job to the deck) and what has no score yet.
  - **Filters** in the search sheet drop postings before anything is scored: a minimum salary, title words to skip, remote / hybrid / on-site, and what the posting plainly says (security clearance, citizenship, no visa sponsorship). Postings that say nothing are kept, and the search result tells how many were skipped. When a search scores only the first few, the most relevant jobs (by title and your skills) go first.
  - **Search job board** is one click: your saved search settings, every new job scored. **Search options** opens a
    sheet with the search settings (keywords, location, levels, days), how many new jobs to add, and what to do with
    them: score all, score only the first few, or only add them and score later. It shows how many job-board requests
    and AI scorings the search can use and how many are left today.
  - Jobs added without a score appear under **Not scored**: score one with its **Score** button, or use the banner to
    score them all (as many as today's AI limit allows). Discover also tells how many jobs are not in the deck because
    they are unscored.
- **Job page**: five steps (score, write, check, apply, follow up) show where this job stands and the one button that
  fits; after you mark a job as applied, pick a follow-up date (the board marks it when it is due). Match score with the reasons behind it; the years of experience the posting asks for ("Asks for 5+ years") are shown next to the score on the job page, the Discover card and the job row, read from the posting text and kept apart from the score; write a tailored résumé or cover letter, switch versions,
  edit (saved as a new version — the original is kept), download PDF or Word; a Fact check list shows each claim in the document and the profile fact behind it, and a warning names anything not found there; track status and notes.
- **Applications**: a board with one column per status (drag cards or use each card's menu); on a phone, stage tabs and a "Move to" menu.
- **Profile**: edit any detail (saved as a new approved version), answer the "Fill the gaps" questions (each answer
  lands on the job or project it is about), rebuild from a new résumé, see version history.
- **Settings**: the Discover deck (swipe mapping, score threshold, toggles, glass effect), today's usage, re-score all jobs after a profile change.

Long-running work (searching, scoring, writing) runs in the background: progress shows where you started it and
in the header, and a notification appears when it finishes, even after a page reload.

## Sign in

Open `http://127.0.0.1:5001/app/` and sign in. Self-service registration is only available when the instance runs
with `REGISTRATION_MODE=open`; otherwise the owner creates accounts. Usernames are 3–32 characters
(letters, digits, `_ - .`); passwords at least 8 characters. Your profile, search settings, jobs,
documents and tasks are private to your account. After sign-in the app opens the next useful step.

A public demo instance (`DEMO_MODE`) opens straight into a sample workspace with a "Read-only demo" banner and, on a
first visit, a one-minute guided tour (restart it from the banner). You can browse jobs, match reports, documents,
the board and the résumé step with a sample résumé in four formats, but every change is refused. Where the live demo
is on, **Try it live** opens a guest workspace with a sample profile: search, scoring and writing run for real within
a small daily budget, a profile can be built from the sample résumé, and the workspace is deleted after 24 hours.

## How it fits together

1. **Build your profile** — paste or attach your résumé (PDF, Word or images, ≤ 10 MB each, 30 MB total), add links and
   context. Check the generated profile: identity, summary, target roles, skills, experience, projects, education
   and open questions. Approve it only when it is accurate; otherwise correct it (each change is a new version
   that needs approval again). Answer high-priority gaps first — they are limited to core fields: name, skills,
   experience.
2. **Set what to search for** — country code, location, keywords, days old, sort order and optional filters.
   Start broad, narrow later. Paging is fixed at 10 results × 1 page to protect API quota.
3. **Find jobs** — search the job board with your saved settings (or open Search options to choose how many jobs to add and score), or paste one job description to score it right away.
4. **Read the match** — score, recommendation, strengths, gaps and risks for each job.
5. **Write materials** — pick a job, write a tailored résumé and/or cover letter, preview, edit, export PDF or Word.
6. **Track the application** — move each role across the board (saved → ready → applied → interview → offer →
   hired, or rejected / withdrawn) with notes.

Search and re-scoring stay locked until the latest profile version is approved and its completeness is at least 70.
If only core fields are missing on an approved profile, a *force* option allows the search anyway. Generation uses
the profile version the match was evaluated with; after the profile changes, re-score before generating.

## Tips for the job search

1. Keep profile facts specific and measurable — they drive both matching and generated text.
2. Re-evaluate jobs after major profile updates.
3. Read gaps and risks before generating; generation is meant to follow a deliberate decision.
4. Broaden filters for discovery, then narrow gradually.
5. Update application status after every apply / interview / outcome so the tracker stays useful.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401` on actions | Sign in again |
| `403` / "read-only demo" | The sample workspace refuses every change; use **Try it live** or run your own instance |
| "Full description unavailable" | The job board's page could not be read; paste the posting on the job page to have it scored |
| Empty or weak search results | Loosen parameters, paste a specific JD, or retry later |
| Adzuna errors | Check `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` in `config/api-keys.env` |
| Gemini errors | Check `GEMINI_API_KEY` and `llm.model` (and `llm.document_model` / `llm.audit_model` if set) in `config/settings.yaml` |
| Generation blocked (`409`) | View the match and choose the document first; re-evaluate if the profile changed |
| Search blocked by readiness | Approve the latest profile and fill high-priority core fields |
| `429` when starting a task | Too many active tasks; wait for running ones to finish |
