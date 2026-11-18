import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { Button, Card, ErrorNote, Field, Input, SegmentedControl, Textarea } from "@/components/ui";
import { useToast } from "@/components/Toaster";

import type { ExperienceDraft, ProfileDraft } from "./editModel";
import { emptyExperience, fromDraft, toDraft } from "./editModel";
import type { MasterProfile } from "./profileModel";

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="px-6 py-5">
      <legend className="sr-only">{title}</legend>
      <h3 className="mb-3 text-subheading font-semibold" aria-hidden>
        {title}
      </h3>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

interface EditorProps {
  original: MasterProfile;
  onSaved: () => void;
  onCancel: () => void;
}

/** Edit the Master Profile directly. Saving creates a new, approved version; old versions are kept. */
export function ProfileEditor({ original, onSaved, onCancel }: EditorProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState<ProfileDraft>(() => toDraft(original));
  const [mode, setMode] = useState<"form" | "json">("form");
  const [json, setJson] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (master_profile: MasterProfile) =>
      unwrap(client.PATCH("/api/v1/profile", { body: { master_profile } })),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
      await queryClient.invalidateQueries({ queryKey: ["overview"] });
      toast({ tone: "success", title: "Profile saved as a new version" });
      onSaved();
    },
  });

  const bind = (field: Exclude<keyof ProfileDraft, "experiences">) => ({
    value: draft[field],
    onChange: (event: { target: { value: string } }) =>
      setDraft((current) => ({ ...current, [field]: event.target.value })),
  });

  const setExperience = (index: number, patch: Partial<ExperienceDraft>) =>
    setDraft((current) => ({
      ...current,
      experiences: current.experiences.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    }));

  const switchMode = (next: "form" | "json") => {
    if (next === "json") {
      setJson(JSON.stringify(fromDraft(original, draft), null, 2));
      setJsonError(null);
    } else {
      try {
        setDraft(toDraft(JSON.parse(json) as MasterProfile));
        setJsonError(null);
      } catch {
        setJsonError("That isn't valid JSON yet. Fix it before switching back.");
        return;
      }
    }
    setMode(next);
  };

  const onSubmit = () => {
    if (mode === "form") {
      save.mutate(fromDraft(original, draft));
      return;
    }
    try {
      const parsed: unknown = JSON.parse(json);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed))
        throw new Error("not an object");
      save.mutate(parsed as MasterProfile);
    } catch {
      setJsonError("The profile must be a valid JSON object.");
    }
  };

  const error = save.error ? describeError(save.error) : null;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      className="flex flex-col gap-4"
    >
      <div className="flex items-center justify-between gap-3">
        <SegmentedControl
          kind="tabs"
          label="Editor mode"
          value={mode}
          onChange={(value) => mode !== value && switchMode(value)}
          options={[
            { value: "form", label: "Form" },
            { value: "json", label: "Advanced (JSON)" },
          ]}
        />
      </div>

      {mode === "json" ? (
        <Card className="p-4">
          <Textarea
            aria-label="Profile JSON"
            rows={24}
            spellCheck={false}
            className="font-mono text-caption"
            value={json}
            onChange={(event) => setJson(event.target.value)}
          />
        </Card>
      ) : (
        <Card>
          <Group title="About you">
            <Field label="Full name">{(id) => <Input id={id} {...bind("name")} />}</Field>
            <Field label="Current title">{(id) => <Input id={id} {...bind("current_title")} />}</Field>
            <Field label="Location">{(id) => <Input id={id} {...bind("location")} />}</Field>
            <Field label="Years of experience">
              {(id) => <Input id={id} {...bind("years_experience")} />}
            </Field>
            <Field label="Email">{(id) => <Input id={id} type="email" {...bind("email")} />}</Field>
            <Field label="Phone">{(id) => <Input id={id} type="tel" {...bind("phone")} />}</Field>
            <Field label="Links" hint="One per line (LinkedIn, GitHub, portfolio…)" className="sm:col-span-2">
              {(id, hint) => <Textarea id={id} aria-describedby={hint} rows={2} {...bind("links")} />}
            </Field>
          </Group>
          <Group title="Summary and skills">
            <Field label="Professional summary" className="sm:col-span-2">
              {(id) => <Textarea id={id} rows={4} {...bind("summary")} />}
            </Field>
            <Field label="Career highlights" hint="One per line" className="sm:col-span-2">
              {(id, hint) => <Textarea id={id} aria-describedby={hint} rows={3} {...bind("highlights")} />}
            </Field>
            <Field label="Core skills" hint="Comma-separated" className="sm:col-span-2">
              {(id, hint) => <Input id={id} aria-describedby={hint} {...bind("core_skills")} />}
            </Field>
          </Group>
          <fieldset className="px-6 py-5">
            <legend className="sr-only">Experience</legend>
            <h3 className="mb-3 text-subheading font-semibold" aria-hidden>
              Experience
            </h3>
            <ol className="flex flex-col gap-4">
              {draft.experiences.map((experience, index) => (
                <li key={index} className="rounded-control bg-subtle p-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Title">
                      {(id) => (
                        <Input
                          id={id}
                          value={experience.title}
                          onChange={(event) => setExperience(index, { title: event.target.value })}
                        />
                      )}
                    </Field>
                    <Field label="Company">
                      {(id) => (
                        <Input
                          id={id}
                          value={experience.company}
                          onChange={(event) => setExperience(index, { company: event.target.value })}
                        />
                      )}
                    </Field>
                    <Field label="Start" hint="e.g. 2021-03">
                      {(id, hint) => (
                        <Input
                          id={id}
                          aria-describedby={hint}
                          value={experience.start_date}
                          onChange={(event) => setExperience(index, { start_date: event.target.value })}
                        />
                      )}
                    </Field>
                    <Field label="End" hint="Leave empty if current">
                      {(id, hint) => (
                        <Input
                          id={id}
                          aria-describedby={hint}
                          value={experience.end_date}
                          onChange={(event) => setExperience(index, { end_date: event.target.value })}
                        />
                      )}
                    </Field>
                    <Field label="What you did and achieved" hint="One per line" className="sm:col-span-2">
                      {(id, hint) => (
                        <Textarea
                          id={id}
                          aria-describedby={hint}
                          rows={4}
                          value={experience.highlights}
                          onChange={(event) => setExperience(index, { highlights: event.target.value })}
                        />
                      )}
                    </Field>
                    <Field
                      label="Tools, software and methods"
                      hint="Comma-separated"
                      className="sm:col-span-2"
                    >
                      {(id, hint) => (
                        <Input
                          id={id}
                          aria-describedby={hint}
                          value={experience.tech_stack}
                          onChange={(event) => setExperience(index, { tech_stack: event.target.value })}
                        />
                      )}
                    </Field>
                  </div>
                  <div className="mt-3 flex justify-end">
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<Trash2 className="size-4" aria-hidden />}
                      onClick={() =>
                        setDraft((current) => ({
                          ...current,
                          experiences: current.experiences.filter((_, i) => i !== index),
                        }))
                      }
                    >
                      Remove
                    </Button>
                  </div>
                </li>
              ))}
            </ol>
            <Button
              className="mt-4"
              size="sm"
              icon={<Plus className="size-4" aria-hidden />}
              onClick={() =>
                setDraft((current) => ({
                  ...current,
                  experiences: [...current.experiences, emptyExperience()],
                }))
              }
            >
              Add experience
            </Button>
          </fieldset>
          <Group title="Education and more">
            <Field label="Education" hint="One per line" className="sm:col-span-2">
              {(id, hint) => <Textarea id={id} aria-describedby={hint} rows={2} {...bind("education")} />}
            </Field>
            <Field label="Certifications" hint="One per line">
              {(id, hint) => (
                <Textarea id={id} aria-describedby={hint} rows={2} {...bind("certifications")} />
              )}
            </Field>
            <Field label="Languages" hint="Comma-separated">
              {(id, hint) => <Input id={id} aria-describedby={hint} {...bind("languages")} />}
            </Field>
          </Group>
          <Group title="What you're looking for">
            <Field label="Target roles" hint="Comma-separated">
              {(id, hint) => <Input id={id} aria-describedby={hint} {...bind("target_roles")} />}
            </Field>
            <Field label="Preferred locations" hint="Comma-separated">
              {(id, hint) => <Input id={id} aria-describedby={hint} {...bind("preferred_locations")} />}
            </Field>
            <Field label="Work authorization" className="sm:col-span-2">
              {(id) => <Input id={id} {...bind("work_authorization")} />}
            </Field>
          </Group>
        </Card>
      )}

      {jsonError && <ErrorNote message={jsonError} reference={null} />}
      {error && <ErrorNote {...error} />}
      <div className="sticky bottom-[calc(var(--dock-h,5rem)+0.5rem)] z-10 flex justify-end gap-2 glass glass-plate rounded-card p-3 shadow-pop lg:bottom-4">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" busy={save.isPending}>
          Save as new version
        </Button>
      </div>
    </form>
  );
}
