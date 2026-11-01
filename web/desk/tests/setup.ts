import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

// Tests must always use the mock data. `.env.local` is git-ignored and
// absent in CI, so we set the flag here rather than relying on the file.
beforeAll(() => {
  vi.stubEnv("VITE_USE_MOCK", "true");
});

afterAll(() => {
  vi.unstubAllEnvs();
});

afterEach(() => {
  cleanup();
});
// jsdom has no modal <dialog>: open and close it by the attribute, which is what the page relies on.
HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
