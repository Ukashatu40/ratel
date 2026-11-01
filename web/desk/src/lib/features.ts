// Screens whose operations the contract does not have yet (stock and voucher batches, reports, staff and audit) work on
// mock data only. In mock mode they are all offered; against the real API they are not, because every call they make
// would answer 404. When an operation lands, the screen is mapped like the others and its entry here is removed.
// The jobs they stand for are done with the command-line tools on bss-app for now (deploy/bss-app/README.md).
export const isMockMode = (): boolean => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";

// Path -> why it is not offered. TODO(contract) for each.
export const NOT_YET_IN_API: Record<string, string> = {
  "/inventory": "SIM import and voucher batches have no operations in the API yet. Use staff_cli and voucher_cli on bss-app.",
  "/finance/reports": "Reports have no operations in the API yet. The side-by-side with the network's counters waits for a decision on how the network's total reaches the app.",
  "/admin/audit": "Staff accounts and the audit trail have no operations in the API yet. Use staff_cli on bss-app; a line's History tab shows who changed it.",
};

export const screenOffered = (path: string): boolean => isMockMode() || !(path in NOT_YET_IN_API);
