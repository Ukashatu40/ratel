import * as mock from "./mock";
import * as real from "./realApi";
import type { CareKind, CarePayload, LinesPage, LinesQuery } from "./types";

// With VITE_USE_MOCK=true these return fixture data. Otherwise they call the API (realApi.ts, contract.ts).
const isMock = () => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";

export const getLines = (query: LinesQuery): Promise<LinesPage> => (isMock() ? mock.mockGetLines(query) : real.getLines(query));

export const careAction = (kind: CareKind, lineId: number, payload: CarePayload, idempotencyKey: string): Promise<void> =>
  isMock() ? mock.mockCareAction(kind, lineId, payload) : real.careAction(kind, lineId, payload, idempotencyKey);
