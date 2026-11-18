import { ApiError } from "./client";

export interface FriendlyError {
  message: string;
  reference: string | null;
}

/** Human-readable message for any thrown value, plus the support reference when the server gave one. */
export function describeError(error: unknown): FriendlyError {
  if (!(error instanceof ApiError)) {
    return { message: "Something went wrong. Please try again.", reference: null };
  }
  return { message: messageFor(error), reference: error.correlationId };
}

function messageFor(error: ApiError): string {
  if (error.status === 0) return "Can't reach the server. Check your connection and try again.";
  switch (error.code) {
    case 1001:
      return "Your session has ended. Please sign in again.";
    case 1003:
      return "That action isn't allowed.";
    case 1004:
      return error.message.includes("live demo")
        ? "This is turned off in the live demo: the sample profile and accounts can't be changed."
        : "This is a read-only demo, so changes are turned off.";
    case 1005:
      return "Too many failed sign-in attempts. Wait 15 minutes, then try again.";
    case 2002:
      if (error.details.length > 0) {
        return error.details.map((d) => `${humanizeField(d.field)}: ${d.message}`).join(" · ");
      }
      return "Some fields need attention.";
    case 2006:
      return "That upload is too large (10 MB per file, 30 MB in total).";
    case 3003:
      return "This item no longer exists.";
    case 3005:
      return "Too many tasks are running. Wait for one to finish and try again.";
    default:
      break;
  }
  if (error.status === 409 || error.status === 400) return capitalize(error.message);
  if (error.status >= 500) return "Something went wrong on our side. Please try again in a moment.";
  return capitalize(error.message || "Request failed.");
}

function humanizeField(field: string): string {
  const last = field.split(".").pop() ?? field;
  return capitalize(last.replaceAll("_", " "));
}

function capitalize(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}
