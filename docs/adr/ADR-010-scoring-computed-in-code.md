# ADR-010: The match score is computed in code from rated dimensions

Date: 2026-10-25
Status: Accepted

## Context

The first real run (Gemini + Adzuna, a mid-level résumé) returned mostly Staff and Manager roles scored 15–65. The
model produced the total score, the recommendation and the dimension scores independently, so they could disagree
(nothing tied `total_score` to the dimensions, and `should_apply` came from the recommendation alone). The prompt gave
no scale, only "ruthless recruiter … penalize heavily", which pulls every score down and makes runs hard to compare.
Seniority was not a dimension at all, and a missing dimension was silently stored as 0.

## Decision

- The model rates five dimensions from 0 to 100 against a written scale in the prompt: `skills_match`,
  `experience_match`, `seniority_match`, `domain_match`, `location_salary_match`. It also reports `seniority_gap`
  (`role_is_more_senior | aligned | role_is_less_senior | unclear`) and `missing_must_haves`: hard gates the candidate's facts
  do not show and cannot be hired without (a licence or registration the role legally requires, a security
  clearance, a legal work requirement, a degree stated as strictly mandatory). Years of experience and skills are never
  must-haves; they are rated in the dimensions. Since `v3`: when years counted, almost every posting for a new
  graduate sat at the cap, so jobs the candidate would apply to never reached the deck (0 of 5 in a first small sample;
  on the 47-posting labelled set, 1 of 17 fitting roles reached the deck before and 7 of 17 after, with the same
  ranking of levels, see ADR-019).
- `core/scoring.py` computes everything else: the total is the weighted sum (skills 0.35, experience 0.25,
  seniority 0.20, domain 0.10, location/salary 0.10), capped at 59 when a must-have is missing; the recommendation
  comes from bands (≥85 `strong_yes`, 70–84 `yes`, 55–69 `maybe`, below `no`); `should_apply` follows it.
- A response without all five numeric dimensions is invalid output (retried once, then the evaluation fails and is
  logged), never a default.
- A seniority gap becomes a visible risk flag and each missing must-have a leading gap ("Missing requirement: …").
- The model is told to judge like a hiring manager who wants to fill the role: equivalent tools, the same work in
  another industry, and for early-career candidates projects, internships, coursework and volunteering count as
  evidence.
- Evaluations store `llm.prompt_version` (now `v3`) next to the model name; older rows keep it empty.

## Consequences

- Scores are explainable (the dimensions add up to the total) and comparable between runs; the weights are one
  place to tune.
- v1 and v2 scores can sit in the same list. They are told apart by `prompt_version`; nothing is re-scored
  automatically because every re-evaluation costs provider quota.
- The weights and bands are reasoned, not yet calibrated: they are checked against a hand-labelled set of 47
  postings (README, ADR-019) but not fitted to it.
