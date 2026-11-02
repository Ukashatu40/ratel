# RatelDesk customer-care runbook

**Audience:** Ratelplus customer care staff ("agents" in this document).
**Prerequisite:** You are on the office network or connected to the Ratelplus VPN.
**URL:** Ask your supervisor for the current RatelDesk URL (it changes per environment: lab, pilot, production).
**Owner of this runbook:** @ml-lawarn (module owner). **Backup:** @capitanaserdel.

If you get stuck on any step, do not improvise. Follow the "When something goes wrong" section below, or contact the people listed at the end.

**Demo mode note:** during the demo, RatelDesk can run against the mock API (`VITE_USE_MOCK=true`) or the real RatelBSS API. Either way the buttons, screens, states and rules in this runbook are the same for you. Only the backend changes. When the pilot switches to real mode, this runbook is unchanged.

---

## 1. Signing in and out

### Sign in
1. Open the RatelDesk URL in Chrome, Edge, or Firefox.
2. Enter your Ratelplus staff email and password.
3. Click **Sign in to RatelDesk**.
4. You land on the Dashboard.

**Note:** if sign-in fails, refresh the page and try again. If it keeps failing, check with your supervisor — the reason may be that your account is disabled or that the backend is unavailable.

### Sign out
Click your name in the top-right corner of any screen, then click **Sign out**.

### Two roles
- **Agent** (shown as "Customer Care") — can sell SIMs, view lines, top up, suspend/reinstate/terminate lines, look up voucher state, view wallet and ledger, view reports.
- **Admin** (shown as "Super Admin") — everything an agent can do, plus staff and audit management, plus KYC decisions.

If your role is not what you expect, ask your supervisor. Roles are set by the backend, not by you.

---

## 2. The four journeys

The PRD (PRODUCT_RULES.md) names four demo journeys. This section is written in the order a customer care agent would follow them.

### 2.1 Buy and activate a new line

*Use when a customer walks in to buy a new SIM.*

**Before you start:** the customer's KYC must be verified. If they are not yet a customer, register them first and wait for KYC verification (a separate compliance process).

1. Click **Sell SIM** in the sidebar. The wizard opens on step 1 of 4: **Customer & KYC**.
2. In **Find the customer**, search by name, phone number or email. Results appear as you type.
3. Click the customer's name in the results.
   - **If KYC is verified (green):** the summary on the right shows the customer. Continue to step 4.
   - **If KYC is pending (amber):** the wizard shows "A line cannot be activated until KYC is verified." You cannot continue. Tell the customer their verification is in progress.
   - **If KYC is rejected (red) or the customer is blocked:** the **Continue** button stays disabled. Do not proceed. See "When something goes wrong" for escalation.
4. Click **Continue** to move to step 2: **SIM & Number**.
5. Pick a **SIM** and a **number** from the available lists. Quarantined numbers are not shown.
6. Click **Continue** to move to step 3: **Choose Plan**.
7. Pick a plan. The **Order summary** on the right updates with the price, VAT (7.5%), and total.
8. Click **Continue to review**.
9. On step 4, review the **Order summary**: SIM ICCID, Number, Plan, VAT, Total. Confirm with the customer.
10. Click **Create line**.

**What happens next — three steps, in this order:**
1. **The customer pays.** You are taken to the **Collect payment** screen. The customer tops up the line's wallet on RatelPay with a prepaid card. You cannot credit the wallet from RatelDesk — that is a RatelPay action.
2. **You buy the plan.** Once the wallet is topped up, click to buy the plan. The plan price (VAT included) is taken from the wallet. This is recorded in the ledger as two entries: the plan purchase and the VAT.
3. **You activate the line.** RatelBSS asks RatelLink to switch the SIM on. **The line becomes active on the network when the phone next attaches** (typically within 5 minutes, but can be longer). Tell the customer to switch the phone off and on, or wait for the next attach.

After all three steps, the line appears in **Lines** with state `active`.

### 2.2 Check a customer's line (status, data, calls, history)

*Use when a customer calls or walks in to ask about their data, calls, or account.*

1. Click **Lines** in the sidebar.
2. Search by name, phone number (MSISDN), ICCID, or IMSI.
3. Click the line to open the **Line Detail** page.
4. The four tabs are:

   - **Overview** — allowance used (ring chart), data used per day (bar chart), line profile (speeds, static IP, provisioning status, network check), and any outstanding issue (for example an out-of-data banner).
   - **Usage** — data usage in 5-minute intervals (uploaded MB, downloaded MB, rated or not yet), paginated.
   - **Calls** — recent voice calls with duration, the other party's number, QCI bearer status, and end reason.
   - **History** — every change made to this line, newest first, with who made it and why.

Read the customer the relevant tab. The **Overview** is usually enough.

**Note:** all times shown are **West Africa Time (WAT)**. The system's internal timestamps are in UTC — you never see those.

### 2.3 Check a customer's balance and ledger

*Use when a customer asks about their balance or wants to see recent transactions. Top-ups themselves are done by the customer on RatelPay, not by you in RatelDesk.*

1. Open the line (see 2.2).
2. Click **Top-Up** in the header. You are taken to the **Wallet** screen with this line pre-selected.
3. The customer's **balance** in Naira is shown at the top of the wallet card. Below it, a badge says whether the balance **matches the ledger** (it always should — if it does not, see "When something goes wrong").
4. The **ledger** below the cards lists every entry for this line: top-ups, plan purchases, VAT, voucher redemptions, and corrections. Each row shows the entry ID, the line, the amount in both kobo and Naira (credits green, debits red), the entry type, a reference, and the time in WAT.
5. Use the tabs to filter the ledger.

**What you cannot do from RatelDesk:**
- You cannot top up a customer's wallet from RatelDesk. Top-ups happen on **RatelPay**, which the customer does themselves.
- You cannot redeem a voucher from RatelDesk. See 2.3.1 for what you *can* do with a voucher.

#### 2.3.1 Check a voucher

*Use when a customer says their voucher was not applied, or you need to confirm a card's state.*

1. Click **Stock & Vouchers** in the sidebar, then the **Vouchers** tab.
2. In **Look up a card**, enter the customer's 20-digit card number (no spaces).
3. Click **Look up**.
4. The card's state appears:
   - **on_sale** — not yet redeemed. The customer can still redeem it on RatelPay.
   - **used** — already redeemed. The card shows who redeemed it (a masked number) and when.
   - **expired** — past its expiry date.
   - **locked** — reported lost or stolen. A locked card cannot be redeemed.
   - **in_stock** — printed but not yet on sale. Not available to customers yet.
5. The panel also shows the card's Luhn check, failed attempts this hour, and its face value.

**If the customer believes a `used` or `locked` card is theirs and should still be redeemable:** escalate to your supervisor. Do not try to override the card state. If the card is `locked`, the **Lock card** button on this screen is what locked it — you cannot unlock it here.

### 2.4 Suspend, reinstate, or terminate a line

*Use for care actions: a lost phone, a customer request, non-payment, fraud, or end of contract.*

**Every care action carries a reason from a fixed list plus an optional note (max 200 characters).** The list is: `fraud`, `non_payment`, `customer_request`, `lost_sim`, `other`.

#### Suspend a line

1. Open the **Lines** page. In the row's **Actions** menu, click **Suspend** — or open the line and click **Suspend line** in the header.
2. Pick a reason from the fixed list.
3. Add a note if useful ("customer called from borrowed phone, reports stolen at 14:30 WAT"). The note is saved in the line's history.
4. Confirm.
5. The line's state becomes `suspended`. Internet and calls are cut **when the phone next attaches to the network** (typically within 5 minutes, but can be longer). Tell the customer.

**Only `active` or `out_of_data` lines can be suspended.** If the Actions menu shows Suspend greyed out, the line is in a state that cannot be suspended.

#### Reinstate a suspended line

1. Open the **Lines** page. In the row's **Actions** menu, click **Reinstate** — or open the line and click **Reinstate line** in the header.
2. Pick a reason from the same fixed list.
3. Add a note if useful.
4. Confirm.
5. The line returns to whichever state it had before suspension — `active` or `out_of_data`. Internet and calls are restored **when the phone next attaches to the network** (typically within 5 minutes, but can be longer).

**If the line was `out_of_data` before suspension**, it stays out of data after reinstate until the customer buys a bundle or a new plan.

#### Terminate a line (final)

1. Open the line (see 2.2). The **Terminate** button is on the line page, not in the Actions menu.
2. Pick a reason from the fixed list.
3. Add a note if useful.
4. Confirm. **This is final.** The SIM is retired and the line cannot be used again.

**When to terminate:** only on a supervisor's instruction — end of contract, confirmed fraud, or a customer who has specifically asked for permanent termination. Do not terminate a line as a substitute for suspension.

---

## 3. When something goes wrong

### The customer cannot be sold a SIM
- **KYC pending:** tell the customer their KYC verification is in progress. You cannot activate a line until it is verified.
- **KYC rejected:** escalate to your supervisor. Do not attempt to sell.
- **Blocked customer:** escalate to your supervisor. Do not attempt to sell. A "blocked" flag is separate from KYC status.
- **No SIMs available:** check **Stock & Vouchers** → **SIMs** → "In stock" count. If stock is exhausted, escalate to the operations team to order more.

### A blocked customer asks about an already-active line
- `blocked` is a customer flag, separate from line state. The app **does not** automatically suspend the lines of a blocked customer. If the customer asks why their line still works (or does not work), escalate to your supervisor. Do not change the line state yourself based on the customer being blocked.

### The line does not connect to the network
- Look at the **History** tab on the line. Did an activation happen? Who, when?
- Look at the **Overview** tab. Is the line `active`, `suspended`, `out_of_data`, `expired`, `awaiting_activation`, or `terminated`?
  - `active` — the line should be connected. If it isn't, escalate to the network team.
  - `suspended` — someone suspended it. Check the History tab for who and why.
  - `out_of_data` — the customer has used their allowance. Offer a top-up (customer does the top-up on RatelPay).
  - `expired` — their plan has ended. Offer a new plan or a top-up.
  - `awaiting_activation` — the activation was not completed. Check with the customer whether they completed the sale and the payment.
  - `terminated` — someone terminated the line. This is final. Check History for who and why, then escalate to your supervisor if the customer disputes it.

### The customer says their data is slow
- The line may be `out_of_data`. Open the line, look at the ring chart on **Overview**. If used = 100%, they have run out. Offer a top-up.
- If they still have allowance, check the **Usage** tab. If recent intervals are not "rated," the rating job hasn't processed them yet (it runs every 5 minutes). Ask them to try again in a few minutes.

### The customer says their balance does not match their ledger
- Open the line's **Wallet** (see 2.3). The badge under the balance says **"Matches the ledger"** (green) or **"Does not match the ledger"** (red).
- If it says "Does not match the ledger": **do not attempt to fix it yourself.** Take a screenshot, note the entry IDs involved, and escalate to finance. The nightly reconciliation job will flag the same mismatch automatically, but you are seeing it first.

### The customer says they were not charged correctly
- Open the line, look at **History**. Every change is audited.
- For billing questions, look at **Wallet** for the line: the balance and the ledger. Every entry has a timestamp, amount, and reference.
- If the ledger looks wrong, escalate to finance with the entry IDs. Do not adjust anything.

### A voucher will not redeem on RatelPay
- Check the card number carefully — 20 digits, no spaces.
- Look at the card in **Stock & Vouchers** → **Vouchers** (see 2.3.1). It may be `used`, `expired`, or `locked`.
- If the card is `locked` and the customer insists they have the physical card, escalate to your supervisor.
- Do not retry redemption more than 5 times per card per hour — that is a rule enforced by the system, and exceeding it locks the card for the hour.

### The payment provider fails
- **Do not manually credit the customer's wallet.** You cannot do this from RatelDesk, and you must not ask anyone to.
- The provider will retry the webhook; when it succeeds, the balance updates automatically.
- If the provider reports the payment succeeded but the balance has not updated within 5 minutes, escalate to your supervisor with the transaction reference.

### The app shows a loading state that never clears
- Refresh the page (`Ctrl+R` or `Cmd+R`).
- If the loading state persists after 30 seconds, log out and log back in.
- If it still persists, check with the network team.

---

## 4. Numbers and units

- **Money** is stored as whole kobo. It is displayed in Naira with two decimal places. ₦1,200.00 means 120,000 kobo. Do not do mental math in kobo.
- **Data** is displayed in GB (1 GB = 1,000,000,000 bytes) or MB for small amounts.
- **Time** is displayed in West Africa Time (WAT, UTC+1, no daylight saving). The internal wire format is UTC epoch seconds — you never see those.
- **Phone numbers** are displayed in the international format `+234 700 000 0000`.
- **IMSI** and **ICCID** are 15-digit and 18–20-digit identifiers, respectively.

---

## 5. Things this runbook does not cover

- **Reports.** Sales, revenue, data usage, and nightly reconciliation. Refer to the finance team's own runbook (when written).
- **Plans & Bundles.** Pricing, validity, speeds and on-exhaustion rules are managed by the product team. Customer care should not change a plan.
- **Stock & Vouchers.** Importing SIM batches and voucher batches, advancing voucher batch states, and locking cards are operations tasks. Refer to the operations runbook (when written).
- **Staff & Audit.** Staff account management is admin-only. Refer to your supervisor.
- **Bundle purchase from a line.** Bundles are bought on RatelPay by the customer.
- **Staff top-ups.** Not available in RatelDesk; top-ups happen on RatelPay.

---

## 6. Who to contact

| Question | Who |
|---|---|
| App problem (this runbook covers the symptom; the fix is theirs) | @ml-lawarn (module owner), @capitanaserdel (backup) |
| KYC policy, blocked accounts, compliance questions | Your supervisor |
| Network / connectivity (attaches, VoLTE issues) | The network team's ops channel |
| Billing, refunds, ledger reconciliation | Finance team |
| Plan pricing, product changes | Product team |
| SIM or voucher stock ordering | Operations team |

---

## 7. Followed once?

This runbook was first followed end-to-end on ____ by ____ in the ____ environment, and these changes were made as a result:

- (list)

If you have followed the runbook and it needs correction, edit this file and open a pull request. The module owner will review.