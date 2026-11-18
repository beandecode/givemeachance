import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";

import { server } from "./server";
import { installMatchMedia, resetViewport } from "./viewport";

installMatchMedia();

// jsdom has no native modal dialog.
HTMLDialogElement.prototype.showModal = function showModal() {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function close() {
  this.removeAttribute("open");
  this.dispatchEvent(new Event("close"));
};

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
// Tests start as a returning visitor: the first-visit tour stays closed unless a test clears this.
beforeEach(() => window.localStorage.setItem("gmc.tour.v2", "done"));
afterEach(() => {
  cleanup();
  resetViewport();
  server.resetHandlers();
});
afterAll(() => server.close());
