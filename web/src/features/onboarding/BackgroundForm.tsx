import { FileText, Paperclip, X } from "lucide-react";
import { useRef, useState } from "react";

import type { Schemas } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { useConfig } from "@/api/queries";
import { Alert, Button, Field, Input, Textarea } from "@/components/ui";
import { useStartTask } from "@/features/jobs/useStartTask";
import { ProgressBar } from "@/features/tasks/TaskTray";
import { useLatestTask } from "@/features/tasks/TaskProvider";
import { isTerminal, taskStageLabel } from "@/features/tasks/taskCopy";

import { SampleResumes } from "./SampleResumes";

type Attachment = Schemas["Attachment"];
const ACCEPT = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
  "image/webp",
] as const;
const MB = 1024 * 1024;

function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = typeof reader.result === "string" ? reader.result : "";
      resolve(url.split(",", 2)[1] ?? "");
    };
    reader.onerror = () => reject(reader.error ?? new Error("could not read file"));
    reader.readAsDataURL(file);
  });
}

const splitCommas = (value: string) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

/** Step 1: résumé text and/or files plus a few facts → the AI builds a profile draft. */
export function BackgroundForm({ onStarted }: { onStarted?: () => void }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [extra, setExtra] = useState("");
  const [details, setDetails] = useState({
    candidate_name: "",
    current_title: "",
    location: "",
    years_experience: "",
    email: "",
    phone: "",
    target_roles: "",
    preferred_locations: "",
  });
  const running = useLatestTask((task) => task.task_type === "synthesize_profile" && !isTerminal(task));
  const config = useConfig();
  const demo = config.data?.demo_mode === true || config.data?.guest === true;

  const start = useStartTask(async () => {
    const attachments: Attachment[] = await Promise.all(
      files.map(async (file) => ({
        name: file.name.slice(0, 200),
        mime_type: file.type as Attachment["mime_type"],
        data_base64: await readBase64(file),
      })),
    );
    return unwrap(
      client.POST("/api/v1/profile/synthesize", {
        body: {
          resume_text: resumeText,
          extra_context: extra,
          links: [],
          attachments,
          user_details: {
            ...details,
            target_roles: splitCommas(details.target_roles),
            preferred_locations: splitCommas(details.preferred_locations),
            key_skills: "",
            work_authorization: "",
          },
        },
      }),
    );
  });

  const addFiles = (picked: FileList | null) => {
    if (!picked) return;
    const next = [...files, ...Array.from(picked)];
    const wrongType = next.find((file) => !(ACCEPT as readonly string[]).includes(file.type));
    const tooBig = next.find((file) => file.size > 10 * MB);
    const total = next.reduce((sum, file) => sum + file.size, 0);
    if (wrongType) setFileError(`${wrongType.name}: only PDF, Word (.docx), PNG, JPEG or WebP files.`);
    else if (tooBig) setFileError(`${tooBig.name} is larger than 10 MB.`);
    else if (total > 30 * MB) setFileError("Files can be 30 MB in total.");
    else if (next.length > 10) setFileError("Up to 10 files.");
    else {
      setFileError(null);
      setFiles(next);
    }
    if (fileInput.current) fileInput.current.value = "";
  };

  const bind = (field: keyof typeof details) => ({
    value: details[field],
    onChange: (event: { target: { value: string } }) =>
      setDetails((current) => ({ ...current, [field]: event.target.value })),
  });

  if (running) {
    return (
      <div className="flex flex-col gap-3 py-6" aria-live="polite">
        <p className="text-subheading font-medium">Building your profile…</p>
        <ProgressBar task={running} />
        <p className="text-secondary text-muted">
          {taskStageLabel(running)}. This usually takes under a minute.
        </p>
      </div>
    );
  }

  if (demo) return <SampleResumes live={config.data?.guest === true} onStarted={onStarted} />;

  const canSubmit = resumeText.trim().length > 0 || files.length > 0;
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        start.mutate(undefined, { onSuccess: () => onStarted?.() });
      }}
      className="flex flex-col gap-5"
    >
      <Field label="Paste your résumé" hint="Plain text is fine. Or attach files below, or both.">
        {(id, hint) => (
          <Textarea
            id={id}
            aria-describedby={hint}
            rows={10}
            maxLength={100000}
            value={resumeText}
            onChange={(event) => setResumeText(event.target.value)}
          />
        )}
      </Field>

      <div className="flex flex-col gap-2">
        <span className="text-secondary font-medium">Files</span>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept={ACCEPT.join(",")}
          className="sr-only"
          id="resume-files"
          onChange={(event) => addFiles(event.target.files)}
        />
        <label
          htmlFor="resume-files"
          className="flex min-h-14 cursor-pointer items-center justify-center gap-2 rounded-control bg-subtle px-4 py-5 text-secondary text-muted hover:text-ink"
        >
          <Paperclip className="size-4" aria-hidden />
          Attach your résumé (PDF or Word) or screenshots (up to 10 MB each)
        </label>
        {files.length > 0 && (
          <ul className="flex flex-col gap-1">
            {files.map((file, index) => (
              <li key={`${file.name}-${String(index)}`} className="flex items-center gap-2 text-secondary">
                <FileText className="size-4 text-muted" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{file.name}</span>
                <span className="text-caption text-muted">{(file.size / MB).toFixed(1)} MB</span>
                <button
                  type="button"
                  className="-m-2 inline-flex size-11 items-center justify-center rounded-full text-faint hover:text-bad"
                  aria-label={`Remove ${file.name}`}
                  onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}
                >
                  <X className="size-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {fileError && <Alert tone="bad">{fileError}</Alert>}
      </div>

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-3 text-secondary font-medium">
          A few facts (optional, they help accuracy)
        </legend>
        <Field label="Full name">
          {(id) => <Input id={id} autoComplete="name" {...bind("candidate_name")} />}
        </Field>
        <Field label="Current title">{(id) => <Input id={id} {...bind("current_title")} />}</Field>
        <Field label="Location">{(id) => <Input id={id} {...bind("location")} />}</Field>
        <Field label="Years of experience">{(id) => <Input id={id} {...bind("years_experience")} />}</Field>
        <Field label="Email">
          {(id) => <Input id={id} type="email" autoComplete="email" {...bind("email")} />}
        </Field>
        <Field label="Phone">
          {(id) => <Input id={id} type="tel" autoComplete="tel" {...bind("phone")} />}
        </Field>
        <Field label="Roles you want" hint="Comma-separated">
          {(id, hint) => <Input id={id} aria-describedby={hint} {...bind("target_roles")} />}
        </Field>
        <Field label="Where you want to work" hint="Comma-separated">
          {(id, hint) => <Input id={id} aria-describedby={hint} {...bind("preferred_locations")} />}
        </Field>
      </fieldset>

      <Field label="Anything else?" hint="Projects, achievements or context your résumé doesn't show.">
        {(id, hint) => (
          <Textarea
            id={id}
            aria-describedby={hint}
            rows={3}
            maxLength={20000}
            value={extra}
            onChange={(event) => setExtra(event.target.value)}
          />
        )}
      </Field>

      <div className="flex justify-end">
        <Button type="submit" variant="primary" busy={start.isPending} disabled={!canSubmit}>
          Build my profile
        </Button>
      </div>
    </form>
  );
}
