import type { ApplicationStatus } from "@/api/client";
import { Dot } from "@/components/ui";
import { STATUS_LABELS } from "@/lib/format";

const TONES = {
  draft: "neutral",
  ready: "accent",
  submitted: "accent",
  interview: "warn",
  offer: "good",
  hired: "good",
  rejected: "bad",
  withdrawn: "neutral",
} as const;

export function StatusText({ status }: { status: ApplicationStatus }) {
  return <Dot tone={TONES[status]}>{STATUS_LABELS[status]}</Dot>;
}
