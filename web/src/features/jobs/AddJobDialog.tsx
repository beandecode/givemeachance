import { useState } from "react";

import { client, unwrap } from "@/api/client";
import { Dialog } from "@/components/Dialog";
import { Button, Field, Input, Textarea } from "@/components/ui";

import { useStartTask } from "./useStartTask";

const EMPTY = { title: "", company: "", location: "", url: "", description: "" };

/** Paste a job description from anywhere; it is saved and scored like a job-board result. */
export function AddJobDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form, setForm] = useState(EMPTY);
  const start = useStartTask(() =>
    unwrap(
      client.POST("/api/v1/jobs/manual", {
        body: {
          title: form.title.trim(),
          description: form.description.trim(),
          company: form.company.trim(),
          location: form.location.trim(),
          url: form.url.trim(),
        },
      }),
    ),
  );

  const set = (field: keyof typeof EMPTY) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [field]: event.target.value }));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a job"
      description="Paste a posting from any site. It will be scored against your profile."
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          start.mutate(undefined, {
            onSuccess: () => {
              setForm(EMPTY);
              onClose();
            },
          });
        }}
        className="grid gap-4 sm:grid-cols-2"
      >
        <Field label="Job title" className="sm:col-span-2">
          {(id) => <Input id={id} required maxLength={200} value={form.title} onChange={set("title")} />}
        </Field>
        <Field label="Company">
          {(id) => <Input id={id} maxLength={200} value={form.company} onChange={set("company")} />}
        </Field>
        <Field label="Location">
          {(id) => <Input id={id} maxLength={200} value={form.location} onChange={set("location")} />}
        </Field>
        <Field label="Link to the posting" hint="Optional" className="sm:col-span-2">
          {(id, hint) => (
            <Input
              id={id}
              type="url"
              aria-describedby={hint}
              maxLength={2000}
              placeholder="https://"
              value={form.url}
              onChange={set("url")}
            />
          )}
        </Field>
        <Field label="Job description" className="sm:col-span-2">
          {(id) => (
            <Textarea
              id={id}
              required
              rows={10}
              maxLength={20000}
              value={form.description}
              onChange={set("description")}
            />
          )}
        </Field>
        <div className="flex justify-end gap-2 sm:col-span-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" busy={start.isPending}>
            Add and score
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
