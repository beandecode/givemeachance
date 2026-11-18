import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId } from "react";

import type { Preferences } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys, usePreferences } from "@/api/queries";
import { Button, ErrorNote, Field, Select } from "@/components/ui";
import { useToast } from "@/components/Toaster";
import type { SwipeAction } from "@/features/discover/actions";
import { ACTION_LABELS, ARROWS, DEFAULT_PREFERENCES } from "@/features/discover/actions";
import type { Direction } from "@/features/discover/swipe";

const DIRECTION_ORDER: Direction[] = ["right", "left", "up", "down"];
const DIRECTION_NAMES: Record<Direction, string> = {
  right: "Swipe right",
  left: "Swipe left",
  up: "Swipe up",
  down: "Swipe down",
};
const ACTIONS: SwipeAction[] = [
  "generate_resume",
  "generate_resume_and_cover_letter",
  "skip",
  "waitlist",
  "details",
  "none",
];
const GLASS_LEVELS: [Preferences["ui"]["glass"], string][] = [
  ["auto", "Automatic (strong in light mode, medium in dark mode)"],
  ["subtle", "Subtle"],
  ["medium", "Medium"],
  ["medium_plus", "Medium plus"],
  ["strong", "Strong"],
];

/** Give `action` to `direction`; if another direction already had it, that one takes the old action (a swap). */
export function assignAction(
  mapping: Preferences["swipe"],
  direction: Direction,
  action: SwipeAction,
): Preferences["swipe"] {
  const next = { ...mapping };
  if (action !== "none") {
    for (const other of DIRECTION_ORDER) {
      if (other !== direction && next[other] === action) next[other] = mapping[direction];
    }
  }
  next[direction] = action;
  return next;
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-3">
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 size-5 shrink-0 accent-accent"
      />
      <label htmlFor={id} className="flex flex-col">
        <span className="text-secondary font-medium">{label}</span>
        <span className="text-caption text-muted">{hint}</span>
      </label>
    </div>
  );
}

/** Settings for the Discover deck. Every change is saved at once, so the glass level can be tried live. */
export function DeckSettings() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const preferences = usePreferences();
  const save = useMutation({
    mutationFn: (next: Preferences) => unwrap(client.PUT("/api/v1/preferences", { body: next })),
    onMutate: async (next) => {
      await queryClient.cancelQueries({ queryKey: keys.preferences });
      const previous = queryClient.getQueryData<Preferences>(keys.preferences);
      queryClient.setQueryData(keys.preferences, next);
      return { previous };
    },
    onError: (error, _next, context) => {
      queryClient.setQueryData(keys.preferences, context?.previous);
      const { message, reference } = describeError(error);
      toast({ tone: "error", title: "Couldn't save the setting", description: message, reference });
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(keys.preferences, saved);
      // The deck is filtered by the threshold, so it has to load again.
      void queryClient.invalidateQueries({ queryKey: keys.jobs });
    },
  });

  if (preferences.isPending) {
    return (
      <div role="status">
        <span className="sr-only">Loading…</span>
        <div aria-hidden className="h-48 animate-pulse rounded-control glass-plate" />
      </div>
    );
  }
  if (preferences.isError) return <ErrorNote {...describeError(preferences.error)} />;

  const prefs = preferences.data;
  const change = (patch: Partial<Preferences>) => save.mutate({ ...prefs, ...patch });

  return (
    <div className="flex flex-col gap-6">
      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="sr-only">What each swipe does</legend>
        {DIRECTION_ORDER.map((direction) => (
          <Field key={direction} label={`${DIRECTION_NAMES[direction]} ${ARROWS[direction]}`}>
            {(id) => (
              <Select
                id={id}
                value={prefs.swipe[direction]}
                onChange={(event) =>
                  change({ swipe: assignAction(prefs.swipe, direction, event.target.value as SwipeAction) })
                }
              >
                {ACTIONS.map((action) => (
                  <option key={action} value={action}>
                    {ACTION_LABELS[action]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        ))}
        <p className="text-caption text-muted sm:col-span-2">
          Each action can sit on one direction only: picking one that is already used swaps the two. “Nothing”
          leaves a direction unused.
        </p>
      </fieldset>

      <Field
        label={`Minimum match score: ${String(prefs.deck.min_score)}`}
        hint="Only jobs at or above this score appear in Discover."
      >
        {(id, describedBy) => (
          <input
            id={id}
            type="range"
            min={0}
            max={100}
            step={5}
            value={prefs.deck.min_score}
            aria-describedby={describedBy}
            onChange={(event) => change({ deck: { ...prefs.deck, min_score: Number(event.target.value) } })}
            className="h-11 w-full accent-accent"
          />
        )}
      </Field>

      <div className="flex flex-col gap-4">
        <Toggle
          label="Drag cards with the mouse"
          hint="Touch swiping and the arrow keys always work."
          checked={prefs.deck.mouse_drag}
          onChange={(mouse_drag) => change({ deck: { ...prefs.deck, mouse_drag } })}
        />
        <Toggle
          label="Show buttons under the card"
          hint="When off, the same actions stay available to keyboards and screen readers."
          checked={prefs.deck.buttons}
          onChange={(buttons) => change({ deck: { ...prefs.deck, buttons } })}
        />
      </div>

      <Field
        label="Glass effect"
        hint={
          prefs.ui.glass === "strong"
            ? "Strong blurs the most and uses the most battery; older phones may feel slower."
            : "How frosted the panels look. Lower levels are lighter on slow devices."
        }
      >
        {(id, describedBy) => (
          <Select
            id={id}
            aria-describedby={describedBy}
            value={prefs.ui.glass}
            onChange={(event) => change({ ui: { glass: event.target.value as Preferences["ui"]["glass"] } })}
          >
            {GLASS_LEVELS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        )}
      </Field>

      <div>
        <Button variant="secondary" size="sm" onClick={() => save.mutate(DEFAULT_PREFERENCES)}>
          Reset to defaults
        </Button>
      </div>
    </div>
  );
}
