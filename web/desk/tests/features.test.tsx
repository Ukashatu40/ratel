import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { AuthContext } from "../src/lib/authContext";
import { AppShell } from "../src/components/layout/AppShell";
import { NOT_YET_IN_API, screenOffered } from "../src/lib/features";

const realMode = () => { vi.stubEnv("MODE", "development"); vi.stubEnv("VITE_USE_MOCK", "false"); };
afterEach(() => { vi.unstubAllEnvs(); vi.stubEnv("VITE_USE_MOCK", "true"); });

const shell = () => {
  const auth = { user: { name: "Test Staff", email: "staff@example.test", role: "Super Admin" as const }, ready: true, signIn: async () => {}, signOut: async () => {} };
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter><Routes><Route element={<AppShell />}><Route index element={<p>home</p>} /></Route></Routes></MemoryRouter>
    </AuthContext.Provider>,
  );
};
const menu = () => screen.getAllByRole("link").map((l) => l.textContent).filter(Boolean);

describe("screens the API cannot serve yet", () => {
  it("are all offered on mock data", () => {
    for (const path of Object.keys(NOT_YET_IN_API)) expect(screenOffered(path)).toBe(true);
    shell();
    expect(menu()).toEqual(expect.arrayContaining(["Stock & Vouchers", "Reports", "Staff & Audit"]));
  });

  it("are left out of the menu against the real API, and the ones that work stay", () => {
    realMode();
    for (const path of Object.keys(NOT_YET_IN_API)) expect(screenOffered(path)).toBe(false);
    expect(screenOffered("/lines")).toBe(true);
    shell();
    const items = menu();
    expect(items).not.toContain("Stock & Vouchers");
    expect(items).not.toContain("Reports");
    expect(items).not.toContain("Staff & Audit");
    expect(items).toEqual(expect.arrayContaining(["Dashboard", "Sell SIM", "Lines", "Customers", "Plans & Bundles", "Wallet"]));
  });

  it("each say what to use instead", () => {
    for (const reason of Object.values(NOT_YET_IN_API)) expect(reason.length).toBeGreaterThan(40);
  });
});
