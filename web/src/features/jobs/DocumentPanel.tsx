import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import Markdown from "react-markdown";

import type { DocumentKind, Schemas } from "@/api/client";
import { client, exportUrl, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys } from "@/api/queries";
import {
  Alert,
  Button,
  buttonClass,
  ErrorNote,
  Meta,
  InlineSelect,
  Spinner,
  Textarea,
} from "@/components/ui";
import { useToast } from "@/components/Toaster";
import { ProgressBar } from "@/features/tasks/TaskTray";
import { taskStageLabel } from "@/features/tasks/taskCopy";
import { formatDate } from "@/lib/format";

import { EvidencePanel } from "./EvidencePanel";
import { DOCUMENT_NAMES, useGenerateDocument } from "./useGenerateDocument";

/** Problems the app found in the generated text (placeholders, invented numbers), kept in the evidence map. */
export function documentWarnings(evidenceMap: Record<string, unknown> | undefined): string[] {
  const warnings = evidenceMap?.warnings;
  return Array.isArray(warnings) ? warnings.filter((item): item is string => typeof item === "string") : [];
}

export function DocumentPreview({ markdown }: { markdown: string }) {
  return (
    <div className="doc-preview">
      <Markdown disallowedElements={["img"]} unwrapDisallowed>
        {markdown}
      </Markdown>
    </div>
  );
}

interface PanelProps {
  jobId: number;
  kind: DocumentKind;
  latest: Schemas["DocumentSummary"] | null;
  canGenerate: boolean;
  /** The page offers the first write action itself (sticky bar or side column), so the panel does not repeat it. */
  externalAction?: boolean;
}

/** One document for one job: generate, switch versions, preview, edit into a new version, export. */
export function DocumentPanel({ jobId, kind, latest, canGenerate, externalAction = false }: PanelProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const name = DOCUMENT_NAMES[kind];
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const { running, generate } = useGenerateDocument(jobId, kind);

  const versions = useQuery({
    queryKey: keys.jobDocuments(jobId),
    queryFn: () =>
      unwrap(client.GET("/api/v1/jobs/{job_id}/documents", { params: { path: { job_id: jobId } } })),
    enabled: latest !== null,
  });
  const list = versions.data?.[kind] ?? [];
  const documentId = selectedId ?? latest?.id ?? null;

  const document = useQuery({
    queryKey: keys.document(kind, documentId ?? 0),
    queryFn: () =>
      unwrap(
        client.GET("/api/v1/documents/{kind}/{document_id}", {
          params: { path: { kind, document_id: documentId ?? 0 } },
        }),
      ),
    enabled: documentId !== null,
    staleTime: Infinity, // versions never change; edits create new ones
  });

  const save = useMutation({
    mutationFn: (content_md: string) =>
      unwrap(
        client.PUT("/api/v1/documents/{kind}/{document_id}", {
          params: { path: { kind, document_id: documentId ?? 0 } },
          body: { content_md },
        }),
      ),
    onSuccess: async (saved) => {
      queryClient.setQueryData(keys.document(kind, saved.id), saved);
      await queryClient.invalidateQueries({ queryKey: keys.job(jobId) });
      setSelectedId(saved.id);
      setEditing(null);
      toast({ tone: "success", title: `Saved as version ${String(saved.version)}` });
    },
  });

  if (running) {
    return (
      <div className="flex flex-col gap-3 py-8" aria-live="polite">
        <p className="font-medium">Writing your {name}…</p>
        <ProgressBar task={running} />
        <p className="text-secondary text-muted">
          {taskStageLabel(running)}. You can leave this page; we'll let you know.
        </p>
      </div>
    );
  }

  if (!latest) {
    return (
      <div className="flex flex-col items-start gap-3 py-6">
        <p className="text-secondary text-muted">
          {kind === "resume"
            ? "A résumé tailored to this job, using only facts from your approved profile."
            : "A cover letter for this job, grounded in your profile and the match analysis."}
        </p>
        {!externalAction && (
          <Button
            variant="primary"
            busy={generate.isPending}
            disabled={!canGenerate}
            onClick={() => generate.mutate()}
          >
            Write my {name}
          </Button>
        )}
        {!canGenerate && <p className="text-caption text-muted">Score this job first.</p>}
      </div>
    );
  }

  const current = document.data;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <InlineSelect
          aria-label={`${name} version`}
          value={String(documentId)}
          onChange={(event) => {
            setSelectedId(Number(event.target.value));
            setEditing(null);
          }}
        >
          {(list.length > 0
            ? list
            : [
                {
                  id: latest.id,
                  version: latest.version,
                  origin: latest.origin,
                  created_at: latest.created_at,
                },
              ]
          ).map((version) => (
            <option key={version.id} value={version.id}>
              Version {version.version} · {version.origin === "edited" ? "edited" : "generated"} ·{" "}
              {formatDate(version.created_at)}
            </option>
          ))}
        </InlineSelect>
        {current?.origin === "edited" && <Meta>Edited by you</Meta>}
        <div className="ml-auto flex flex-wrap gap-2">
          {editing === null ? (
            <>
              <Button size="sm" disabled={!current} onClick={() => current && setEditing(current.content_md)}>
                Edit
              </Button>
              <a
                className={buttonClass("secondary", "sm")}
                href={documentId ? exportUrl(kind, documentId, "pdf") : undefined}
                download
              >
                <Download className="size-4" aria-hidden />
                PDF
              </a>
              <a
                className={buttonClass("secondary", "sm")}
                href={documentId ? exportUrl(kind, documentId, "docx") : undefined}
                download
              >
                <Download className="size-4" aria-hidden />
                Word
              </a>
              <Button size="sm" variant="ghost" busy={generate.isPending} onClick={() => generate.mutate()}>
                Write again
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                variant="primary"
                busy={save.isPending}
                disabled={!editing.trim() || editing === current?.content_md}
                onClick={() => save.mutate(editing)}
              >
                Save as new version
              </Button>
            </>
          )}
        </div>
      </div>

      {save.error && <ErrorNote {...describeError(save.error)} />}
      {document.isPending && <Spinner />}
      {document.isError && <ErrorNote {...describeError(document.error)} />}
      {current && editing === null && documentWarnings(current.evidence_map).length > 0 && (
        <Alert tone="warn" title="Check this before you send it">
          <ul className="list-disc pl-5">
            {documentWarnings(current.evidence_map).map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Alert>
      )}
      {current && editing === null && <EvidencePanel evidenceMap={current.evidence_map} />}
      {current &&
        (editing === null ? (
          <div className="rounded-control border border-line bg-surface px-5 py-6 sm:px-10 sm:py-8">
            <DocumentPreview markdown={current.content_md} />
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <Textarea
              aria-label={`Edit ${name} (Markdown)`}
              className="min-h-[28rem] font-mono text-caption"
              spellCheck
              value={editing}
              maxLength={50000}
              onChange={(event) => setEditing(event.target.value)}
            />
            <div
              className="hidden max-h-[40rem] overflow-y-auto rounded-control border border-line bg-surface px-5 py-5 lg:block"
              aria-label="Preview"
            >
              <DocumentPreview markdown={editing} />
            </div>
          </div>
        ))}
    </div>
  );
}
