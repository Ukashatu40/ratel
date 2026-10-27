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