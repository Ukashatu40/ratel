export type KycStatus = "pending" | "verified" | "rejected";

export interface Customer {
  id: string;
  name: string;
  phone: string;
  email: string;
  idType: "NIN";
  idNumber: string;
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

export interface ActivateRequest { customerId: string; iccid: string; msisdn: string; planId: string }
export interface ActivateResult { imsi: string; msisdn: string; planName: string; expiresAt: number } // expiresAt: Unix seconds, UTC