import { ExternalLink, FileText } from "lucide-react";
import { useState } from "react";

import { client, unwrap } from "@/api/client";
import { Alert, Button, SegmentedControl } from "@/components/ui";
import { useStartTask } from "@/features/jobs/useStartTask";

type Kind = "text" | "pdf" | "docx" | "image";

const KINDS: { value: Kind; label: string; what: string }[] = [
  { value: "text", label: "Pasted text", what: "the résumé pasted as plain text" },
  { value: "pdf", label: "PDF", what: "a PDF file, read by the AI directly" },
  { value: "docx", label: "Word", what: "a Word .docx file, read as text, tables included" },
  { value: "image", label: "Screenshot", what: "a PNG screenshot, read from the image" },
];

export const sampleUrl = (kind: Kind) => `/api/v1/demo/sample-resumes/${kind}`;

/**
 * The résumé step of the public demo. Your own résumé never goes into the demo, so this explains what the real form
 * takes and lets a guest build a profile from a fictional sample in any format (ADR-018).
 */
export function SampleResumes({ live, onStarted }: { live: boolean; onStarted?: () => void }) {
  const [kind, setKind] = useState<Kind>("pdf");
  const start = useStartTask(() =>
    unwrap(client.POST("/api/v1/profile/synthesize", { body: { sample: kind } })),
  );
  const chosen = KINDS.find((item) => item.value === kind);

  return (
    <div data-tour="resume-input" className="flex flex-col gap-6">
      <section>
        <h3 className="text-subheading font-semibold">What you can give it in your own workspace</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-secondary text-muted">
          <li>Paste your résumé as text, attach it as PDF or Word, or add screenshots (up to 10 files).</li>
          <li>Add links and a few facts. What you type wins over what is read from the files.</li>
          <li>
            Nothing is invented: what is missing becomes a short question, most of all a result without a
            number. Your answer lands on the job it is about.
          </li>
        </ul>
      </section>

      <section className="flex flex-col gap-3">
        <h3 className="text-subheading font-semibold">Try it with a sample résumé</h3>
        <p className="text-secondary text-muted">
          Casey Chen is a fictional backend engineer. The same résumé comes in four formats; a few details are
          missing on purpose, such as the co-op dates and the side projects' results, so you will see the gap
          questions.
        </p>
        <SegmentedControl
          label="Sample résumé format"
          value={kind}
          onChange={setKind}
          options={KINDS.map(({ value, label }) => ({ value, label }))}
        />
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-secondary">
          <FileText className="size-4 text-muted" aria-hidden />
          <span>Builds from {chosen?.what ?? "the sample"}.</span>
          <a
            href={sampleUrl(kind)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-11 items-center gap-1 text-accent underline-offset-4 hover:underline"
          >
            Open the file
            <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </p>
      </section>

      {live ? (
        <div className="flex flex-col gap-2">
          <Button
            variant="primary"
            className="self-start"
            busy={start.isPending}
            onClick={() => start.mutate(undefined, { onSuccess: () => onStarted?.() })}
          >
            Build a profile from this résumé
          </Button>
          <p className="text-caption text-muted">
            Uses the real AI model. The new profile replaces the sample one in your guest workspace, and its
            scores then need a refresh.
          </p>
        </div>
      ) : (
        <Alert tone="accent" title="This sample workspace is read-only">
          Press Try it live at the top to start a guest workspace, then build a profile from this résumé.
        </Alert>
      )}
    </div>
  );
}
