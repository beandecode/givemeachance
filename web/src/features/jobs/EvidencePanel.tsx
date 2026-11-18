import { Dot } from "@/components/ui";

type ClaimStatus = "supported" | "inferred" | "unsupported";

export interface Claim {
  text: string;
  status: ClaimStatus;
  profile_path: string;
  quote: string;
}

const STATUS_ORDER: ClaimStatus[] = ["unsupported", "inferred", "supported"];
const STATUS_LABEL: Record<ClaimStatus, string> = {
  unsupported: "Not in your profile",
  inferred: "Reasonable, not stated",
  supported: "In your profile",
};
const STATUS_TONE = { unsupported: "warn", inferred: "neutral", supported: "good" } as const;

/** The fact check's claims, ignoring anything that is not shaped like a claim (older documents have none). */
export function readClaims(evidenceMap: Record<string, unknown> | undefined): Claim[] {
  const raw = evidenceMap?.claims;
  if (!Array.isArray(raw)) return [];
  const claims: Claim[] = [];
  for (const item of raw as unknown[]) {
    if (typeof item !== "object" || item === null) continue;
    const { text, status, profile_path, quote } = item as Record<string, unknown>;
    if (typeof text !== "string" || !STATUS_ORDER.includes(status as ClaimStatus)) continue;
    claims.push({
      text,
      status: status as ClaimStatus,
      profile_path: typeof profile_path === "string" ? profile_path : "",
      quote: typeof quote === "string" ? quote : "",
    });
  }
  return claims.sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status));
}

/** What the fact check found: each claim in the document and the profile fact behind it. */
export function EvidencePanel({ evidenceMap }: { evidenceMap: Record<string, unknown> | undefined }) {
  const claims = readClaims(evidenceMap);
  if (claims.length === 0) return null;
  const unsupported = claims.filter((claim) => claim.status === "unsupported").length;

  return (
    <details className="rounded-control border border-line px-4 py-3">
      <summary className="min-h-11 cursor-pointer text-secondary font-medium">
        Fact check: {claims.length} {claims.length === 1 ? "claim" : "claims"} checked against your profile
        {unsupported > 0 ? `, ${String(unsupported)} not found` : ", all found"}
      </summary>
      <ul className="mt-3 flex flex-col gap-3">
        {claims.map((claim) => (
          <li key={`${claim.status}-${claim.text}`} className="text-secondary">
            <p>{claim.text}</p>
            <p className="mt-0.5 flex flex-wrap items-baseline gap-x-3 text-caption text-muted">
              <Dot tone={STATUS_TONE[claim.status]}>{STATUS_LABEL[claim.status]}</Dot>
              {claim.quote && <span className="italic">“{claim.quote}”</span>}
              {claim.profile_path && <span className="font-mono">{claim.profile_path}</span>}
            </p>
          </li>
        ))}
      </ul>
    </details>
  );
}
