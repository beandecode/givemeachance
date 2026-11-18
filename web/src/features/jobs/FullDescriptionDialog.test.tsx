import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { ok, server } from "@/test/server";
import { renderRoute } from "@/test/render";

import { FullDescriptionDialog } from "./FullDescriptionDialog";

const task = {
  task_id: "tsk_1",
  task_type: "re_evaluate",
  owner_user_id: 1,
  state: "queued",
  progress_percent: 0,
  progress_stage: "queued",
  correlation_id: "req_1",
  error_code: null,
  error_message_safe: null,
  result_ref: null,
  job_id: null,
  cancel_requested: false,
  created_at_utc: "2026-10-25T00:00:00Z",
  started_at_utc: null,
  finished_at_utc: null,
};

beforeAll(() => {
  // jsdom has no native modal dialog
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute("open");
  };
});

describe("FullDescriptionDialog", () => {
  it("saves the pasted posting and then asks for the job to be scored again", async () => {
    const calls: string[] = [];
    let saved: unknown = null;
    let rerun: unknown = null;
    const onClose = vi.fn();
    server.use(
      http.put("*/api/v1/jobs/7/description", async ({ request }) => {
        calls.push("description");
        saved = await request.json();
        return ok({});
      }),
      http.post("*/api/v1/evaluations/rerun", async ({ request }) => {
        calls.push("rerun");
        rerun = await request.json();
        return ok(task, 202);
      }),
    );
    renderRoute([{ path: "/", element: <FullDescriptionDialog jobId={7} open onClose={onClose} /> }], "/");

    const posting = "Backend engineer working with Python, Flask and SQL on AWS. ".repeat(5);
    await userEvent.click(screen.getByLabelText("Job description"));
    await userEvent.paste(posting);
    await userEvent.click(screen.getByRole("button", { name: "Save and score again" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(calls).toEqual(["description", "rerun"]);
    expect((saved as { description: string }).description).toBe(posting.trim());
    expect((rerun as { job_ids: number[] }).job_ids).toEqual([7]);
  });
});
