import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type { Schemas } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys } from "@/api/queries";
import { Button, ErrorNote, Field, Input, Select } from "@/components/ui";
import { useToast } from "@/components/Toaster";

type Params = Schemas["AdzunaSearchParams"];
type Config = Schemas["JobSearchConfig"];
type Level = Config["target_levels"][number];
type WorkMode = Config["work_modes"][number];
type Knockout = Config["knockouts"][number];

const WORK_MODES: [WorkMode, string][] = [
  ["remote", "Remote"],
  ["hybrid", "Hybrid"],
  ["onsite", "On-site"],
];

const KNOCKOUTS: [Knockout, string][] = [
  ["security_clearance", "Needs a security clearance"],
  ["citizenship_required", "Needs citizenship"],
  ["no_sponsorship", "Offers no visa sponsorship"],
];

const LEVELS: [Level, string][] = [
  ["junior", "Junior"],
  ["mid", "Mid-level"],
  ["senior", "Senior"],
  ["staff_plus", "Staff and principal"],
  ["management", "Management"],
];

const COUNTRIES: [string, string][] = [
  ["au", "Australia"],
  ["at", "Austria"],
  ["be", "Belgium"],
  ["br", "Brazil"],
  ["ca", "Canada"],
  ["fr", "France"],
  ["de", "Germany"],
  ["in", "India"],
  ["it", "Italy"],
  ["mx", "Mexico"],
  ["nl", "Netherlands"],
  ["nz", "New Zealand"],
  ["pl", "Poland"],
  ["sg", "Singapore"],
  ["za", "South Africa"],
  ["es", "Spain"],
  ["ch", "Switzerland"],
  ["gb", "United Kingdom"],
  ["us", "United States"],
];

interface Draft {
  keywords: string;
  location: string;
  country: string;
  days_old: string;
  salary_min: string;
  sort_by: Params["sort_by"];
  hours: "" | "full_time" | "part_time";
  contract: "" | "permanent" | "contract";
  what_exclude: string;
  exclude_title_words: string;
}

function toDraft(params: Params): Draft {
  return {
    keywords: params.keywords.join(", "),
    location: params.location,
    country: params.country,
    days_old: String(params.days_old),
    salary_min: params.salary_min ? String(params.salary_min) : "",
    sort_by: params.sort_by,
    hours: params.full_time ? "full_time" : params.part_time ? "part_time" : "",
    contract: params.permanent ? "permanent" : params.contract ? "contract" : "",
    what_exclude: params.what_exclude ?? "",
    exclude_title_words: "",
  };
}

function fromDraft(base: Params, draft: Draft): Params {
  return {
    ...base,
    keywords: draft.keywords
      .split(",")
      .map((word) => word.trim())
      .filter(Boolean),
    location: draft.location.trim(),
    country: draft.country,
    days_old: Math.min(365, Math.max(1, Number(draft.days_old) || 14)),
    salary_min: draft.salary_min ? Math.max(0, Number(draft.salary_min)) : null,
    sort_by: draft.sort_by,
    full_time: draft.hours ? draft.hours === "full_time" : null,
    part_time: draft.hours ? draft.hours === "part_time" : null,
    permanent: draft.contract ? draft.contract === "permanent" : null,
    contract: draft.contract ? draft.contract === "contract" : null,
    what_exclude: draft.what_exclude.trim() || null,
  };
}

interface FormProps {
  initial: Config;
  submitLabel?: string;
  onSaved?: () => void;
  /** Embedded use (the search sheet): the caller owns saving and the submit button, which targets `formId`. */
  formId?: string;
  onSubmitConfig?: (config: Config) => unknown;
  /** Called with the config as it is edited, e.g. to estimate a search's cost. */
  onConfigChange?: (config: Config) => void;
}

/** Edit the saved job-board search. PUT replaces the whole config, so unknown fields are carried over. */
export function SearchPreferencesForm({
  initial,
  submitLabel = "Save preferences",
  onSaved,
  formId,
  onSubmitConfig,
  onConfigChange,
}: FormProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [base, setBase] = useState(initial.adzuna);
  const [draft, setDraft] = useState(() => toDraft(initial.adzuna));
  const [levels, setLevels] = useState<Level[]>(initial.target_levels);
  const [workModes, setWorkModes] = useState<WorkMode[]>(initial.work_modes);
  const [knockouts, setKnockouts] = useState<Knockout[]>(initial.knockouts);
  const [titleWords, setTitleWords] = useState(initial.exclude_title_words.join(", "));

  const current = (params: Params): Config => ({
    adzuna: params,
    target_levels: levels,
    work_modes: workModes,
    knockouts,
    exclude_title_words: titleWords
      .split(",")
      .map((word) => word.trim())
      .filter(Boolean),
  });

  const save = useMutation({
    mutationFn: (params: Params) =>
      unwrap(client.PUT("/api/v1/search-preferences", { body: current(params) })),
    onSuccess: async (data) => {
      queryClient.setQueryData(keys.searchPreferences, data);
      await queryClient.invalidateQueries({ queryKey: keys.overview });
      toast({ tone: "success", title: "Search preferences saved" });
      onSaved?.();
    },
  });

  const suggest = useMutation({
    mutationFn: () => unwrap(client.GET("/api/v1/search-preferences/suggested")),
    onSuccess: (data) => {
      setBase(data.config.adzuna);
      setDraft(toDraft(data.config.adzuna));
      setLevels(data.config.target_levels);
      setWorkModes(data.config.work_modes);
      setKnockouts(data.config.knockouts);
      setTitleWords(data.config.exclude_title_words.join(", "));
    },
  });

  const bind = <K extends keyof Draft>(field: K) => ({
    value: draft[field],
    onChange: (event: { target: { value: string } }) =>
      setDraft((current) => ({ ...current, [field]: event.target.value as Draft[K] })),
  });

  useEffect(() => {
    onConfigChange?.(current(fromDraft(base, draft)));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `current` is rebuilt from exactly these values
  }, [base, draft, levels, workModes, knockouts, titleWords, onConfigChange]);

  const error = save.error ?? suggest.error;
  return (
    <form
      id={formId}
      onSubmit={(event) => {
        event.preventDefault();
        if (onSubmitConfig) void onSubmitConfig(current(fromDraft(base, draft)));
        else save.mutate(fromDraft(base, draft));
      }}
      className="grid gap-4 sm:grid-cols-2"
    >
      <Field label="Keywords" hint="Job titles or skills, comma-separated" className="sm:col-span-2">
        {(id, hint) => <Input id={id} aria-describedby={hint} required {...bind("keywords")} />}
      </Field>
      <Field label="Country">
        {(id) => (
          <Select id={id} {...bind("country")}>
            {COUNTRIES.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="City or region" hint="Leave empty for the whole country">
        {(id, hint) => <Input id={id} aria-describedby={hint} {...bind("location")} />}
      </Field>
      <Field label="Posted within (days)">
        {(id) => <Input id={id} type="number" min={1} max={365} inputMode="numeric" {...bind("days_old")} />}
      </Field>
      <Field label="Minimum salary" hint="Optional, yearly">
        {(id, hint) => (
          <Input
            id={id}
            aria-describedby={hint}
            type="number"
            min={0}
            inputMode="numeric"
            {...bind("salary_min")}
          />
        )}
      </Field>
      <Field label="Hours">
        {(id) => (
          <Select id={id} {...bind("hours")}>
            <option value="">Any</option>
            <option value="full_time">Full-time</option>
            <option value="part_time">Part-time</option>
          </Select>
        )}
      </Field>
      <Field label="Contract">
        {(id) => (
          <Select id={id} {...bind("contract")}>
            <option value="">Any</option>
            <option value="permanent">Permanent</option>
            <option value="contract">Contract</option>
          </Select>
        )}
      </Field>
      <Field label="Exclude words" hint="Skip postings that mention these, space-separated">
        {(id, hint) => <Input id={id} aria-describedby={hint} {...bind("what_exclude")} />}
      </Field>
      <Field label="Order results by">
        {(id) => (
          <Select id={id} {...bind("sort_by")}>
            <option value="date">Most recent</option>
            <option value="relevance">Relevance</option>
            <option value="salary">Salary</option>
          </Select>
        )}
      </Field>
      <fieldset className="sm:col-span-2">
        <legend className="mb-1 text-sm font-medium">Job levels to score</legend>
        <p className="mb-3 text-sm text-muted">
          Jobs whose title names another level are skipped before anything is scored.
        </p>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <label className="flex min-h-11 items-center gap-3 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-accent"
              checked={levels.length === 0}
              onChange={() => setLevels([])}
            />
            All levels
          </label>
          {LEVELS.map(([value, label]) => (
            <label key={value} className="flex min-h-11 items-center gap-3 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-accent"
                checked={levels.includes(value)}
                onChange={(event) =>
                  setLevels((current) =>
                    event.target.checked ? [...current, value] : current.filter((item) => item !== value),
                  )
                }
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <Field
        label="Skip titles with"
        hint="Words like sales or intern, comma-separated. Whole words only."
        className="sm:col-span-2"
      >
        {(id, hint) => (
          <Input
            id={id}
            aria-describedby={hint}
            value={titleWords}
            onChange={(e) => setTitleWords(e.target.value)}
          />
        )}
      </Field>
      <fieldset className="sm:col-span-2">
        <legend className="mb-1 text-sm font-medium">Where you will work</legend>
        <p className="mb-3 text-sm text-muted">
          Postings that name another way of working are skipped. Postings that name none are kept.
        </p>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <label className="flex min-h-11 items-center gap-3 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-accent"
              checked={workModes.length === 0}
              onChange={() => setWorkModes([])}
            />
            Any
          </label>
          {WORK_MODES.map(([value, label]) => (
            <label key={value} className="flex min-h-11 items-center gap-3 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-accent"
                checked={workModes.includes(value)}
                onChange={(event) =>
                  setWorkModes((now) =>
                    event.target.checked ? [...now, value] : now.filter((m) => m !== value),
                  )
                }
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="sm:col-span-2">
        <legend className="mb-1 text-sm font-medium">Skip postings that say</legend>
        <p className="mb-3 text-sm text-muted">
          Only what the posting plainly says. Job boards often send a short preview, so some will still get
          through.
        </p>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {KNOCKOUTS.map(([value, label]) => (
            <label key={value} className="flex min-h-11 items-center gap-3 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-accent"
                checked={knockouts.includes(value)}
                onChange={(event) =>
                  setKnockouts((now) =>
                    event.target.checked ? [...now, value] : now.filter((k) => k !== value),
                  )
                }
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      {error && (
        <div className="sm:col-span-2">
          <ErrorNote {...describeError(error)} />
        </div>
      )}
      <div className="flex flex-wrap justify-between gap-2 sm:col-span-2">
        <Button variant="ghost" busy={suggest.isPending} onClick={() => suggest.mutate()}>
          Suggest from my profile
        </Button>
        {!onSubmitConfig && (
          <Button type="submit" variant="primary" busy={save.isPending}>
            {submitLabel}
          </Button>
        )}
      </div>
    </form>
  );
}
