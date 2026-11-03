# RatelDesk customer-care runbook

**Audience:** Ratelplus customer care staff ("agents" in this document).
**Prerequisite:** RatelDesk answers only to the addresses the network team allows (the office network and the VPN). If it shows "403" or does not open, you are not on an allowed network: ask your supervisor how to reach it.
**URL:** Ask your supervisor for the current RatelDesk URL (it changes per environment: lab, pilot, production).
**Owner of this runbook:** @ml-lawarn (module owner). **Backup:** @capitanaserdel.

If you get stuck on any step, do not improvise. Follow the "When something goes wrong" section below, or contact the people listed at the end.

**What this version has.** This runbook describes RatelDesk running against the real RatelBSS API. It is **not** the same as the practice (mock-data) build:

- **Not in the menu:** Stock & Vouchers, Reports, and Staff & Audit. Their jobs are done by the operations team with command-line tools. If you cannot find a screen this runbook does not mention, that is why.
- **Plans & Bundles is read-only:** you can see the plans on sale; you cannot create or change one.
- **The Calls tab says "not available yet"**, and the line profile shows "Not available yet" for the static address, provisioning and network check. They are being built.
- **Dashboard and wallet numbers have no "this week" trend lines.**

If your RatelDesk shows a screen or a button this runbook does not, tell your supervisor: you may be on the practice build.

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
- **Agent** (shown as "Customer Care") — can register customers, sell SIMs, view customers, lines, plans, the wallet and ledger, and suspend or reinstate a line. An agent **cannot** decide a customer's KYC and **cannot** terminate a line.
- **Admin** (shown as "Super Admin") — everything an agent can do, plus **KYC decisions** (approve or reject) and **terminating** a line.

If your role is not what you expect, ask your supervisor. Roles are set by the backend, not by you.

---

## 2. The four journeys

The PRD (PRODUCT_RULES.md) names four demo journeys. This section is written in the order a customer care agent would follow them.

### 2.1 Buy and activate a new line

*Use when a customer walks in to buy a new SIM.*

**Before you start:** the customer's KYC must be verified. A new customer starts with KYC **pending**, and **only an admin can approve it** (in **Customers**, open the customer, check the details, **Approve**). If you are an agent, register the customer and ask an admin to approve before you continue.

1. Click **Sell SIM** in the sidebar. The wizard opens on step 1 of 4: **Customer & KYC**.
2. In **Find the customer**, search by name, phone number or email. Results appear as you type.
3. Click the customer's name in the results.
   - **If KYC is verified (green):** the customer's card shows on the page. Go on to step 4.
   - **If KYC is pending (amber):** you can move on to choosing a SIM, but from the plan step the wizard shows "A line cannot be activated until KYC is verified." and the button stays disabled. Ask an admin to approve the customer in **Customers**.
   - **If KYC is rejected (red) or the customer is blocked:** the button stays disabled. Do not proceed. See "When something goes wrong" for escalation.
4. Click **Continue** to move to step 2: **SIM & Number**.
5. Pick a **SIM** and a **number** from the lists. Only SIMs in stock and numbers that are available are listed. If a list is empty, see "When something goes wrong".
6. Click **Continue** to move to step 3: **Choose Plan**.
7. Pick a plan. The **Order summary** on the right shows the price. **VAT is already inside the price**, so the total is the price.
8. Click **Continue to review**.
9. On step 4, review the **Order summary**: SIM ICCID, number, plan and total (VAT included). Confirm with the customer.
10. Click **Create line**.

**What happens next — three steps, in this order:**
1. **The customer pays.** You are taken to the **Collect payment and activate** screen. It shows the RatelPay address and the line's number. The customer opens that address on their phone and tops up the number with a prepaid card. You cannot credit the wallet from RatelDesk — that is a RatelPay action. The screen shows the wallet balance and refreshes it every few seconds; **Refresh balance** checks at once.
2. **You buy the plan.** The **Buy plan** button is enabled once the wallet covers the plan's price. The price (VAT included) is taken from the wallet, once; pressing it twice does not charge twice. The ledger records two entries: the plan purchase and the VAT.
3. **You activate the line.** The **Activate line** button is enabled after the purchase. RatelBSS asks RatelLink to switch the SIM on. If it is refused, the screen shows the reason; you can press the button again and the line is not activated twice. **The line works on the network when the phone next attaches.** Tell the customer to switch the phone off and on, or wait for the next attach.

You do not have to finish in one sitting. If the page is closed after **Create line**, find the line in **Lines** (state "Awaiting activation") and open it: the same payment and activation steps are at the top of its page.

After all three steps, the line appears in **Lines** with state `active`.

### 2.2 Check a customer's line (status, data, calls, history)

*Use when a customer calls or walks in to ask about their data, calls, or account.*

1. Click **Lines** in the sidebar.
2. Search by name, phone number (MSISDN), ICCID, or IMSI.
3. Click the line to open the **Line Detail** page.
4. The four tabs are:

   - **Overview** — data used (ring chart, **an estimate from the usage records since the plan started**), data used per day (bar chart), the line profile (speeds; the static address, provisioning status and network check say "Not available yet"), and any outstanding issue (for example an out-of-data banner).
   - **Usage** — the last 24 hours of data usage in 5-minute intervals (uploaded MB, downloaded MB, rated or not yet), newest first. **Show older** loads more.
   - **Calls** — shows "Call history is not available yet". It will list calls once the call records are connected.
   - **History** — every change made to this line, newest first, with who made it and why.

Read the customer the relevant tab. The **Overview** is usually enough.

**Note:** all times shown are **West Africa Time (WAT)**. The system's internal timestamps are in UTC — you never see those.

### 2.3 Check a customer's balance and ledger

*Use when a customer asks about their balance or wants to see recent transactions. Top-ups themselves are done by the customer on RatelPay, not by you in RatelDesk.*

1. Open the line (see 2.2).
2. Click **Top-Up** in the header. You are taken to the **Wallet** screen with this line pre-selected.
3. The customer's **balance** in Naira is shown at the top of the wallet card. Below it, a badge says whether the balance **matches the ledger** (it always should — if it does not, see "When something goes wrong").
4. The **ledger** below the cards lists every entry for this line: top-ups (a card payment or a voucher), plan purchases, VAT, and corrections. Each row shows the entry ID, the line, the amount in both kobo and Naira (credits green, debits red), the entry type, a reference, and the time in WAT.
5. Use the tabs to filter the ledger.

**What you cannot do from RatelDesk:**
- You cannot top up a customer's wallet from RatelDesk. Top-ups happen on **RatelPay**, which the customer does themselves.
- You cannot redeem a voucher, or look one up, from RatelDesk. See 2.3.1.

#### 2.3.1 A customer's voucher did not work

RatelDesk has no voucher lookup, and you should **never type, read out or write down a customer's card number or PIN**. If a customer says their card was refused:

1. Ask them to open the RatelPay address again and retype the 20-digit card number, the 14-digit PIN and the phone number of the line, slowly. A wrong card number, a wrong PIN and a card that was already used all get the **same** message on purpose, so it does not tell you which.
2. After 5 wrong tries on one card in an hour, RatelPay asks them to wait. Do not try to get round it.
3. If the customer is sure the card is right, escalate to your supervisor. The operations team can check the card's state.

### 2.4 Suspend, reinstate, or terminate a line

*Use for care actions: a lost phone, a customer request, non-payment, fraud, or end of contract.*

**Every care action carries a reason from a fixed list plus an optional note (max 200 characters).** The list is: `fraud`, `non_payment`, `customer_request`, `lost_sim`, `other`.

#### Suspend a line

1. Open the **Lines** page. In the row's **Actions** menu, click **Suspend** — or open the line and click **Suspend line** in the header.
2. Pick a reason from the fixed list.
3. Add a note if useful ("customer called from borrowed phone, reports stolen at 14:30 WAT"). The note is saved in the line's history.
4. Confirm.
5. The line's state becomes `suspended`. Internet and calls are cut **when the phone next attaches to the network**. Tell the customer.

**Only `active` or `out_of_data` lines can be suspended.** If the Actions menu shows Suspend greyed out, the line is in a state that cannot be suspended.

#### Reinstate a suspended line

1. Open the **Lines** page. In the row's **Actions** menu, click **Reinstate** — or open the line and click **Reinstate line** in the header.
2. Pick a reason from the same fixed list.
3. Add a note if useful.
4. Confirm.
5. The line returns to whichever state it had before suspension — `active` or `out_of_data`. Internet and calls are restored **when the phone next attaches to the network**.

**If the line was `out_of_data` before suspension**, it stays out of data after reinstate until it has a paid allowance again. Ask your supervisor how the customer gets one.

#### Terminate a line (final, admins only)

Only an admin sees the **Terminate** button. If you are an agent and a line must be terminated, ask an admin.

1. Open the line (see 2.2). The **Terminate** button is on the line page, not in the Actions menu.
2. Pick a reason from the fixed list.
3. Add a note if useful.
4. Confirm. **This is final.** The SIM is retired and the line cannot be used again.

**When to terminate:** only on a supervisor's instruction — end of contract, confirmed fraud, or a customer who has specifically asked for permanent termination. Do not terminate a line as a substitute for suspension.

---

## 3. When something goes wrong

### The customer cannot be sold a SIM
- **KYC pending:** an admin has to approve the customer in **Customers**. You cannot activate a line until it is verified.
- **KYC rejected:** escalate to your supervisor. Do not attempt to sell.
- **Blocked customer:** escalate to your supervisor. Do not attempt to sell. A "blocked" flag is separate from KYC status.
- **No SIM or number in the list:** tell your supervisor. Stock is loaded by the operations team.

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
- See 2.3.1. Do not ask for the card number or PIN.
- The customer gets the same message for every reason (wrong number, wrong PIN, used, expired, locked) on purpose.
- After 5 wrong tries on one card in an hour the customer is asked to wait. That is enforced by the system.
- If the customer insists the card is right, escalate to your supervisor.

### The payment provider fails
- **Do not manually credit the customer's wallet.** You cannot do this from RatelDesk, and you must not ask anyone to.
- The provider will retry the webhook; when it succeeds, the balance updates automatically.
- If the provider reports the payment succeeded but the balance has not updated after a few minutes, escalate to your supervisor with the transaction reference.

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

- **Reports, Stock & Vouchers, and Staff & Audit.** They are not in this version of RatelDesk. The operations and finance teams do those jobs with their own tools.
- **Plans & Bundles.** The screen is read-only. Pricing, validity, speeds and on-exhaustion rules are managed by the product team. Customer care should not change a plan.
- **Buying a bundle.** Not available yet, in RatelDesk or on RatelPay.
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