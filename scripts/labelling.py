"""Hand-labelled job set for measuring the match scores (roadmap phase 11).
Collecting and labelling use only the standard library; scoring uses the app's own code.

    collect   fetch real postings from the job board into a JSON file (needs ADZUNA_APP_ID / ADZUNA_APP_KEY;
              run it inside a container that loads the provider keys):
                  docker exec -i <container> python - collect < scripts/labelling.py
    serve     a local page to label them one by one; scores are never shown, so the labels are not anchored:
                  ./.venv/bin/python scripts/labelling.py serve      ->  http://127.0.0.1:5031/
              (add --host <this computer's LAN address> to label from a phone on the same network)

    score     score the same postings with the app's own evaluator for one model, into scores-<model>.json (also
              inside a container that loads the provider keys; the profile is built once from resume.txt and
              reused for every model):
                  docker exec -i <container> python - score --model <id> < scripts/labelling.py

    fulltext  fetch each posting's full description from the job board's detail page into jobs-full.json; score it
              with `score --jobs jobs-full.json` to see what the missing text costs:
                  ./.venv/bin/python scripts/labelling.py fulltext

    report    compare the scores with the labels: how often the score puts a pair in the labeller's order, with 95%
              intervals (a resampled estimate, fixed seed), and how many fitting jobs reach the swipe deck. Prints
              the README table; calls no provider, so it runs on the host:
                  ./.venv/bin/python scripts/labelling.py report [scores-<model>-jobs-full.json ...]

All files live under output_localtest/labelling/ (gitignored): the postings belong to their publishers, the
résumé is personal and the labels are the owner's own judgment.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_DIR = Path("output_localtest/labelling")
# (group, query, how many to keep). Groups spread the set: clear fits, a level above, and neighbouring fields.
# Chosen for the candidate the set is labelled for (a data scientist early in their career).
QUERIES = [
    ("target", "data scientist", 6),
    ("target", "machine learning engineer", 5),
    ("target", "data analyst", 5),
    ("target", "AI engineer", 4),
    ("target", "data engineer", 4),
    ("target", "junior data scientist", 4),
    ("level-high", "senior data scientist", 4),
    ("level-high", "staff machine learning engineer", 3),
    ("level-high", "data science manager", 3),
    ("adjacent", "backend engineer", 4),
    ("adjacent", "software developer", 3),
    ("adjacent", "devops engineer", 3),
]
DECISIONS = ("apply", "maybe", "skip")
LEVELS = ("fits", "too_senior", "too_junior", "unsure")


def _search(country: str, where: str, what: str, days: int) -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "app_id": os.environ["ADZUNA_APP_ID"],
            "app_key": os.environ["ADZUNA_APP_KEY"],
            "what": what,
            "where": where,
            "results_per_page": 20,
            "max_days_old": days,
            "content-type": "application/json",
        }
    )
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?{query}"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 (fixed https host)
        return json.load(response).get("results", [])


def collect(out: Path, country: str, where: str, days: int, seed: int) -> None:
    rng = random.Random(seed)
    jobs: dict[str, dict] = {}
    for group, what, keep in QUERIES:
        results = _search(country, where, what, days)
        rng.shuffle(results)
        added = 0
        for item in results:
            key = str(item.get("id", ""))
            if not key or key in jobs or added >= keep:
                continue
            jobs[key] = {
                "id": key,
                "group": group,
                "query": what,
                "title": str(item.get("title", "")).strip(),
                "company": str((item.get("company") or {}).get("display_name", "")).strip(),
                "location": str((item.get("location") or {}).get("display_name", "")).strip(),
                "salary_min": item.get("salary_min"),
                "salary_max": item.get("salary_max"),
                "description": str(item.get("description", "")).strip(),
                "url": str(item.get("redirect_url", "")),
                "posted": str(item.get("created", ""))[:10],
            }
            added += 1
        print(f"{what}: {len(results)} found, {added} kept", file=sys.stderr)
    ordered = list(jobs.values())
    rng.shuffle(ordered)  # the labelling order says nothing about the group
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"collected_at": datetime.now(UTC).isoformat(), "jobs": ordered}, indent=1))
    print(f"wrote {len(ordered)} postings to {out}", file=sys.stderr)


def serve(folder: Path, host: str, port: int) -> None:
    jobs_file, labels_file = folder / "jobs.json", folder / "labels.json"
    jobs = json.loads(jobs_file.read_text())["jobs"]
    page = Path(__file__).with_name("labelling.html").read_bytes()
    known = {job["id"] for job in jobs}

    def read_labels() -> dict:
        return json.loads(labels_file.read_text()) if labels_file.exists() else {}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            if self.path == "/":
                self._send(200, page, "text/html; charset=utf-8")
            elif self.path == "/data":
                self._send(200, json.dumps({"jobs": jobs, "labels": read_labels()}).encode(), "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            job_id = str(body.get("id", ""))
            decision, level = body.get("decision"), body.get("level")
            if (
                self.path != "/labels"
                or job_id not in known
                or decision not in (None, *DECISIONS)
                or level not in (None, *LEVELS)
            ):
                self._send(400, b"bad label", "text/plain")
                return
            labels = read_labels()
            labels[job_id] = {
                "decision": decision,
                "level": level,
                "note": str(body.get("note") or "")[:500],
                "labelled_at": datetime.now(UTC).isoformat(),
            }
            labels_file.write_text(json.dumps(labels, indent=1))
            self._send(200, b"{}", "application/json")

        def log_message(self, *args) -> None:  # quiet
            return

    print(f"Label {len(jobs)} postings at http://{host}:{port}/  (Ctrl+C to stop; labels in {labels_file})")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def fulltext(folder: Path, pause: float) -> None:
    """Replace each preview with the full description the app itself would read (core/job_fulltext.py)."""
    import time

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.job_fulltext import fetch_full_description

    data = json.loads((folder / "jobs.json").read_text())
    full = 0
    for job in data["jobs"]:
        job["preview"] = job["description"]
        text = fetch_full_description(job["url"], job["description"])
        if text is not None:
            job["description"] = text
            full += 1
        time.sleep(pause)
    (folder / "jobs-full.json").write_text(json.dumps(data, indent=1))
    print(f"{full} of {len(data['jobs'])} postings now have their full description", file=sys.stderr)


def score(
    folder: Path, model: str, profile_model: str, limit: int | None, pause: float, jobs_name: str = "jobs.json"
) -> None:
    """Score every posting not yet scored for `model`; safe to run again after an interruption."""
    import time

    from adapters.llm.gemini_api import GeminiApiEvaluator
    from core.evaluation_profile import evaluation_projection
    from core.profile_synthesis import _normalize_master_profile
    from core.schemas import JobRecord

    usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def adapter(name: str) -> GeminiApiEvaluator:
        llm = GeminiApiEvaluator(model_name=name, db_path=None)  # no app quota: this tool counts its own calls
        post = llm._post

        def counted(body: dict) -> object:
            usage["calls"] += 1
            payload = post(body)
            meta = payload.get("usageMetadata", {}) if isinstance(payload, dict) else {}
            usage["input_tokens"] += int(meta.get("promptTokenCount", 0))
            usage["output_tokens"] += int(meta.get("candidatesTokenCount", 0)) + int(meta.get("thoughtsTokenCount", 0))
            return payload

        llm._post = counted  # type: ignore[method-assign]
        return llm

    profile_file = folder / "profile.json"
    if not profile_file.exists():
        details = dict.fromkeys(
            ("candidate_name", "current_title", "location", "years_experience", "email", "phone"), ""
        ) | {"work_authorization": "", "target_roles": [], "preferred_locations": [], "key_skills": ""}
        bundle = {
            "resume_text": (folder / "resume.txt").read_text(),
            "extra_context": "",
            "links": [],
            "user_details": details,
        }
        raw = adapter(profile_model).synthesize_master_profile(bundle, [])
        profile = _normalize_master_profile(
            raw_profile=raw, input_bundle=bundle, attachments=[], model_name=profile_model
        )
        profile_file.write_text(json.dumps(profile, indent=1, ensure_ascii=False))
        print(f"built the profile with {profile_model}", file=sys.stderr)
    resume = evaluation_projection(json.loads(profile_file.read_text()))

    jobs = json.loads((folder / jobs_name).read_text())["jobs"]
    out = folder / f"scores-{model}{'' if jobs_name == 'jobs.json' else '-' + Path(jobs_name).stem}.json"
    saved: dict = json.loads(out.read_text()) if out.exists() else {"model": model}
    results: dict[str, dict] = saved.setdefault("results", {})
    spent: dict[str, int] = saved.setdefault("usage", {})
    llm = adapter(model)
    todo = [job for job in jobs if "score" not in results.get(job["id"], {})][:limit]
    for job in todo:
        record = JobRecord.model_validate(
            {
                "id": job["id"],
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "salary_min": int(job["salary_min"]) if job["salary_min"] else None,
                "salary_max": int(job["salary_max"]) if job["salary_max"] else None,
                "description": job["description"],
                "posted_date": job["posted"],
                "source": "adzuna",  # previews are then flagged to the scorer, as in the app
                "url": job["url"],
            }
        )
        started = time.monotonic()
        try:
            result = llm.evaluate(resume, record)
            results[job["id"]] = {
                "score": result.match_score,
                "dimensions": result.dimension_scores,
                "recommendation": result.recommendation_level,
                "confidence": result.confidence,
                "risk_flags": result.risk_flags,
                "seconds": round(time.monotonic() - started, 1),
            }
        except Exception as error:  # noqa: BLE001 (record and go on: one bad posting must not lose the run)
            results[job["id"]] = {"error": f"{type(error).__name__}: {error}"[:200]}
        for key, value in usage.items():
            spent[key] = spent.get(key, 0) + value
            usage[key] = 0
        out.write_text(json.dumps(saved, indent=1))
        time.sleep(pause)
    done = [item for item in results.values() if "score" in item]
    failed = [item["error"] for item in results.values() if "error" in item]
    seconds = sorted(item["seconds"] for item in done)
    print(
        f"{model}: {len(done)} scored, {len(failed)} failed, usage {spent}, "
        f"median {seconds[len(seconds) // 2] if seconds else '-'} s per job",
        file=sys.stderr,
    )
    for message in sorted(set(failed)):
        print(f"  failed: {message}", file=sys.stderr)


DECK_SCORE = 70  # the default swipe-deck threshold (a user setting in the app)
RESAMPLES = 2000
SEED = 7
# USD per 1M tokens (input, output including thinking), paid tier, from Google's pricing page on 2026-11-16.
# gemini-3.8-flash is an introductory rate until 2026-12-31 (1.50 and 7.50 after).
PRICES = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-4-hydrogen": (1.50, 7.50),
}


def cost_per_100(model: str, usage: dict | None, postings: int) -> float | None:
    """Dollars to score 100 postings, from the tokens the run counted; None when the price or tokens are unknown."""
    if model not in PRICES or not usage or not usage.get("input_tokens") or not postings:
        return None
    cheap, dear = PRICES[model]
    total = (usage["input_tokens"] * cheap + usage.get("output_tokens", 0) * dear) / 1_000_000
    return total / postings * 100


def pair_agreement(better: list[float], worse: list[float]) -> float:
    """Share of (better, worse) pairs the numbers put in that order; a tie counts half, 0.5 is a coin flip."""
    pairs = len(better) * len(worse)
    if not pairs:
        return float("nan")
    return sum((a > b) + 0.5 * (a == b) for a in better for b in worse) / pairs


def agreement_interval(
    better: list[float], worse: list[float], resamples: int = RESAMPLES, seed: int = SEED
) -> tuple[float, float]:
    """95% interval of `pair_agreement`, by resampling each group with replacement (the seed makes it repeatable)."""
    if not better or not worse:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    values = sorted(
        pair_agreement(rng.choices(better, k=len(better)), rng.choices(worse, k=len(worse))) for _ in range(resamples)
    )
    return values[int(0.025 * resamples)], values[int(0.975 * resamples) - 1]


def evaluate_scores(labels: dict, results: dict, deck_score: int = DECK_SCORE) -> dict:
    """The README numbers for one model: `labels` is labels.json, `results` the `results` of a scores file."""
    scored = {key: item for key, item in results.items() if "score" in item and key in labels}
    by_level = {level: [key for key in scored if labels[key].get("level") == level] for level in ("fits", "too_senior")}
    by_decision = {
        decision: [key for key in scored if labels[key].get("decision") == decision] for decision in ("apply", "skip")
    }
    seniority = {key: float(scored[key]["dimensions"]["seniority_match"]) for key in scored}
    total = {key: float(scored[key]["score"]) for key in scored}
    level = ([seniority[k] for k in by_level["fits"]], [seniority[k] for k in by_level["too_senior"]])
    decide = ([total[k] for k in by_decision["apply"]], [total[k] for k in by_decision["skip"]])
    deck = [key for key in scored if total[key] >= deck_score]
    seconds = sorted(item["seconds"] for item in scored.values() if "seconds" in item)
    return {
        "scored": len(scored),
        "level": pair_agreement(*level),
        "level_interval": agreement_interval(*level),
        "level_pairs": len(level[0]) * len(level[1]),
        "decision": pair_agreement(*decide),
        "decision_interval": agreement_interval(*decide),
        "decision_pairs": len(decide[0]) * len(decide[1]),
        "fits_in_deck": sum(key in deck for key in by_level["fits"]),
        "fits": len(by_level["fits"]),
        "deck": len(deck),
        "skips_in_deck": sum(key in deck for key in by_decision["skip"]),
        "median_seconds": seconds[len(seconds) // 2] if seconds else None,
    }


def states_years(text: str) -> bool:
    """Whether a posting names the years of experience it asks for (the same reading the app shows on a job)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.posting_years import years_asked

    return years_asked(text or "") is not None


def format_report(name: str, result: dict, usage: dict | None = None) -> str:
    low, high = result["level_interval"]
    d_low, d_high = result["decision_interval"]
    lines = [
        f"{name}: {result['scored']} labelled postings scored",
        "",
        "| Measure | Value | 95% interval |",
        "|---|---|---|",
        f"| Level: roles that fit ranked above roles that ask for more ({result['level_pairs']} pairs) | "
        f"{result['level']:.2f} | {low:.2f} to {high:.2f} |",
        f"| Apply ranked above skip ({result['decision_pairs']} pairs) | {result['decision']:.2f} | "
        f"{d_low:.2f} to {d_high:.2f} |",
        f"| Fitting roles reaching the deck (score {DECK_SCORE}+) | {result['fits_in_deck']} of {result['fits']} | |",
        f"| Roles in the deck | {result['deck']}, of which skip-labelled: {result['skips_in_deck']} | |",
    ]
    if result["median_seconds"] is not None:
        lines.append(f"| Median seconds per posting | {result['median_seconds']} | |")
    if usage and usage.get("input_tokens"):
        lines.append(f"| Tokens | {usage['input_tokens']} in, {usage.get('output_tokens', 0)} out | |")
    cost = cost_per_100(name, usage, result["scored"])
    if cost is not None:
        lines.append(f"| Cost per 100 postings | ${cost:.2f} | |")
    return "\n".join(lines)


def report(folder: Path, files: list[Path]) -> None:
    labels = json.loads((folder / "labels.json").read_text())
    paths = files or sorted(folder.glob("scores-*-jobs-full.json"))
    if not paths:
        sys.exit(f"No scores-*-jobs-full.json files in {folder}; run `score` first")
    for path in paths:
        data = json.loads(path.read_text())
        print(format_report(data.get("model", path.stem), evaluate_scores(labels, data["results"]), data.get("usage")))
        print()
    for name in ("jobs.json", "jobs-full.json"):
        if (folder / name).exists():
            jobs = json.loads((folder / name).read_text())["jobs"]
            stating = sum(states_years(job["description"]) for job in jobs)
            print(f"Postings that state the years asked, {name}: {stating} of {len(jobs)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("collect")
    fetch.add_argument("--out", type=Path, default=DEFAULT_DIR / "jobs.json")
    fetch.add_argument("--country", default="ca")
    fetch.add_argument("--where", default="Toronto")
    fetch.add_argument("--days", type=int, default=30)
    fetch.add_argument("--seed", type=int, default=11)
    page = commands.add_parser("serve")
    page.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    # The page has no sign-in: bind it to this computer, or to its address on a home network you trust.
    page.add_argument("--host", default="127.0.0.1")
    page.add_argument("--port", type=int, default=5031)
    rate = commands.add_parser("score")
    rate.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    rate.add_argument("--model", required=True)
    rate.add_argument("--profile-model", default="gemini-2.5-flash-lite")
    rate.add_argument("--limit", type=int, default=None, help="score at most this many postings in this run")
    rate.add_argument("--pause", type=float, default=2.0, help="seconds between calls (provider rate limits)")
    rate.add_argument("--jobs", default="jobs.json", help="jobs.json (previews) or jobs-full.json (full text)")
    text = commands.add_parser("fulltext")
    text.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    text.add_argument("--pause", type=float, default=1.0)
    compare = commands.add_parser("report")
    compare.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    compare.add_argument("scores", nargs="*", type=Path, help="scores files (default: every scores-*-jobs-full.json)")
    args = parser.parse_args()
    if args.command == "collect":
        collect(args.out, args.country, args.where, args.days, args.seed)
    elif args.command == "score":
        score(args.dir, args.model, args.profile_model, args.limit, args.pause, args.jobs)
    elif args.command == "report":
        report(args.dir, args.scores)
    elif args.command == "fulltext":
        fulltext(args.dir, args.pause)
    else:
        serve(args.dir, args.host, args.port)


if __name__ == "__main__":
    main()
