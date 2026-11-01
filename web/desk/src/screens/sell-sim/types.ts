import type { LineState } from "../dashboard/types";

export type KycStatus = "pending" | "verified" | "rejected";

export interface Customer {
  id: string;
  name: string;
  phone: string;
  email: string;
  // TODO(PRD): allowed id_type values are open (decision 3). Demo value: "NIN" only.
  idType: "NIN";
  idNumber: string; // empty when the customer came from a list: the list carries neither the NIN nor the address
  // TODO(PRD): address format is open (decision 3). Demo value: free text.
  address: string;
  kycStatus: KycStatus;
  blocked: boolean; // separate from KYC status
}
export type NewCustomer = Omit<Customer, "id" | "kycStatus" | "blocked">;

// BSS holds ICCID, IMSI and batch only. SIM secret keys (Ki/OPc) never reach this app.
export interface FreeSim { iccid: string; imsi: string; batch: string }

export interface Plan {
  planId: string;
  name: string;
  priceKobo: number;
  validityDays: number;
  dataBytes: number;
  speedUlMbps: number;
  speedDlMbps: number;
  onExhaustion: "slow" | "stop";
  slowUlMbps: number;
  slowDlMbps: number;
}

export interface CreateLineRequest { customerId: string; iccid: string; msisdn: string; planId: string }

// A line as the sale sees it. `lineId` is the API's integer id; the line page is still reached by IMSI.
export interface CreatedLine { lineId: number; imsi: string; msisdn: string; planId: string; state: LineState; expiresAt: number | null } // expiresAt: Unix seconds, UTC
export interface Wallet { balanceKobo: number; ledgerSumKobo: number }
// Whole kobo. priceKobo is what the wallet is debited and already includes the VAT.
export interface Purchase { priceKobo: number; netKobo: number; vatKobo: number; balanceKobo: number; validTo: number | null; replayed: boolean }
