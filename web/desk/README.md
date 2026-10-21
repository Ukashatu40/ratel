# RatelDesk dashboard + sign-in wiring (v3)

Tested: type-check, lint (0 warnings) and build pass, with Tailwind on. The sign-in flow was tested end to end
(redirect to /login, sign in, return to the page you wanted, stay signed in on reload, sign out).

## 1. Install (PowerShell, in your ratel-desk folder)
    npm install react-router @tanstack/react-query @fontsource-variable/inter

## 2. Copy the files
Copy the `src` folder from this zip INTO your src (merge, do not replace). Your SignInScreen files are not in the zip.

## 3. Change TWO lines in your src/screens/SignInScreen.tsx (the design and CSS stay exactly as they are)
    interface SignInScreenProps {
      onLoginSuccess: (email: string) => void;      // was: () => void
    }
    ...
      setTimeout(() => {
        setIsLoading(false);
        onLoginSuccess(email.trim());               // was: onLoginSuccess();
      }, 500);

## 4. Replace your src/App.tsx and src/main.tsx with the two files in `merge/`
They keep your named import `import { SignInScreen } from "./screens/SignInScreen"`.
(If your own App.tsx or main.tsx contains anything else you need, move it across.)

## 5. Fake data
Create .env.local in the project root containing:  VITE_USE_MOCK=true   then restart `npm run dev`.

## Notes
- Sign-in is a MOCK for now: any email and password work, and the name is taken from the email.
  Click the user name in the header to sign out. Real sign-in will replace src/lib/auth.tsx.
- Optional: delete src/App.css and the template images in src/assets (hero.png, react.svg, vite.svg).
- Optional: remove the font-family line in SignInScreen.css so the sign-in page uses the same Inter font as the dashboard.

# Sell SIM screen (v1)

Tested: type-check, lint (0 warnings), build, and a browser walk-through of the whole flow.

## Copy into your project (PowerShell, from the ratel-desk folder, after unzipping)
    Copy-Item "<unzipped folder>\sell-sim-v1\src\*" -Destination ".\src" -Recurse -Force

This ADDS src/screens/sell-sim/ and UPDATES four files that came from my earlier zip:
src/App.tsx (now has the Sell SIM route), src/lib/format.ts, src/lib/api.ts, src/styles/theme.css (form fields, alerts).
If you changed any of those four yourself, tell me first or merge by hand. Nothing else is touched.

Then run `npm run dev` (keep VITE_USE_MOCK=true in .env.local) and open Sell SIM in the sidebar.

## Try these in the mock data
- Search "aisha"  -> KYC pending: you can choose SIM and plan, but "Continue to review" stays disabled with the KYC message.
- Search "fatima" -> KYC verified: complete the sale (activation is mocked).
- Search "danjuma" -> blocked: cannot continue.
- "Register a new customer" -> NIN must be 11 digits; new customers start as KYC pending.

## Assumptions to confirm (also marked TODO in src/screens/sell-sim/api.ts)
- Endpoints /v1/customers, /v1/stock/sims, /v1/stock/numbers, /v1/plans, /v1/lines are guesses from the Build Plan.
- How the first plan is paid at the counter (voucher, wallet, card) is not defined, so there is no payment field yet.
- Blocked customers are stopped from continuing. The plan has a "blocked" flag but does not say what it means.
- Email is optional; name, phone, NIN (11 digits) and address are required.
# Lines screen (v1)

Checked: type-check, lint (0 warnings) and build pass. I did not run a browser walk-through of this screen.

## Copy into your project (PowerShell, from the ratel-desk folder, after unzipping)
    Copy-Item "<unzipped folder>\lines-v1\src\*" -Destination ".\src" -Recurse -Force
Adds src/screens/lines/ and src/lib/messages.ts. UPDATES src/App.tsx (Lines route), src/lib/api.ts (handles empty responses)
and src/styles/theme.css (red button). If you edited any of those three yourself, merge by hand.

## What it does
- Search by name, phone number, ICCID or IMSI; results update as you type. The search, state tab and page live in the URL (/lines?q=...&state=...&page=...),
  so the search box in the header also lands here and Back works.
- Tabs: All, Active, Out of Data, Suspended, Expired, each with its count. Pagination, 10 per page.
- State badges: active green; out_of_data and expired red; awaiting_activation and suspended amber.
- Navy Actions menu per row: View Details, Top-Up, Suspend (with the "Changes take effect when the phone next attaches" note).
  Suspend opens a dialog that requires a reason and sends one request with an Idempotency-Key. Only active or out-of-data lines can be suspended.
- View Details and Top-Up link to /lines/:imsi, which is still a placeholder until the Line Detail screen is built.

## Assumptions to confirm (also in src/screens/lines/api.ts)
- GET /v1/lines?q=&state=&page=&pageSize= returning { items, total, counts }, and POST /v1/lines/{imsi}/suspend { reason }.
- Tab counts follow the current search.
- Your design has five tabs, but the Build Plan has six states (awaiting_activation and terminated only appear under All).

# Line Detail screen (v1)

Checked: type-check, lint (0 warnings) and build pass. I did not run a browser walk-through of this screen.
Needs the Lines screen (lines-v1) already in your project: it reuses the Suspend dialog from there.

## Copy into your project (PowerShell, from the ratel-desk folder, after unzipping)
    Copy-Item "<unzipped folder>\line-detail-v1\src\*" -Destination ".\src" -Recurse -Force
Adds src/screens/line-detail/. UPDATES four files from my earlier zips: src/App.tsx (route for /lines/:imsi),
src/lib/format.ts, src/components/charts/charts.tsx (ring and bar charts added), src/screens/lines/mock.ts (one export added).
If you edited any of those yourself, merge by hand.

## What it does
- Header: customer initials, phone number, live state badge, customer | plan | IMSI. Top-Up goes to the Wallet screen (placeholder for now).
  Suspend line opens the same reason dialog as the Lines screen and is only enabled for active or out-of-data lines.
- The "Changes take effect when the phone next attaches to the network." note stays visible above the tabs.
- Tabs (the open tab is in the URL, e.g. ?tab=usage): Overview, Usage, Calls, History.
  - Overview: data allowance ring, data used per day, line profile (speeds, static IP, provisioning status, network check).
  - Usage: 5-minute intervals (ogstun), uploaded and downloaded MB, rated or not yet, paged.
  - Calls: VoLTE history with duration, number (To or From), QCI 1 bearer status and end reason. Calls are not charged yet.
  - History: the append-only audit trail, newest first, with who and why. All times are in WAT.
- Out-of-data lines show a short explanation: the internet is slowed or off, calls still work.

## Left out on purpose
- "Throttle speed" button from the first mockup: the Build Plan has no manual speed action (speed changes follow the line states). Tell me if you want it and what it should call.
- Reactivate and Terminate actions: not in the design yet.

## Assumptions to confirm (also in src/screens/line-detail/api.ts)
- Endpoints: GET /v1/lines/{imsi}, /usage, /calls, /history.
- The QCI 1 bearer status is not in the Contract 2 call record, so it needs RatelVoice data.
- "Rated" per usage interval comes from the rating job in RatelBSS.

# Customers & KYC screen (v1)

Checked: type-check, lint (0 warnings) and build pass, and the new dev-server endpoints were exercised in-process.
I did not run a browser walk-through of this screen.
Needs the earlier zips already in your project (sell-sim, lines, line-detail).

## Copy into your project (PowerShell, from the ratel-desk folder, after unzipping)
    Copy-Item "<unzipped folder>\customers-v1\src\*" -Destination ".\src" -Recurse -Force
Adds src/screens/customers/. UPDATES five files from earlier zips: src/App.tsx (Customers route), src/components/ui.tsx (KycBadge),
src/styles/theme.css (green button), src/screens/sell-sim/mock.ts (shares the customer list) and src/screens/sell-sim/api.ts
(customer search now reads { items } from GET /v1/customers). If you edited any of those yourself, merge by hand.
Also replace the dev server with the new ratel-dev-server.zip: GET /v1/customers now returns { items, total, counts }.

## What it does
- Directory: customer, masked NIN, phone, email, linked lines (links to Lines), KYC badge, and a Blocked tag. Search by name, phone or NIN.
  Tabs: All, Pending, Verified, Rejected, each with a count. 10 per page. Search, tab, page and the open customer live in the URL.
- Click a customer to open the verification drawer (Esc or the X closes it):
  - Details: status, NIN (masked), phone, email, address, who submitted it and when (WAT), linked SIMs, blocked flag, a placeholder for the NIN document.
  - Pending customers: Approve (green) or Reject (red). Reject needs a reason.
  - History tab: every decision with who made it and why.
- After a decision the list, counts, drawer, history and dashboard refresh. Approved customers can then be sold a SIM.

## Assumptions to confirm (also in src/screens/customers/api.ts)
- Endpoints: GET /v1/customers?q=&kyc=&page=&pageSize=, GET /v1/customers/{id}, GET /v1/customers/{id}/history, POST /v1/customers/{id}/kyc { status, reason }.
- A decision can be recorded once. Changing a verified or rejected decision is not offered (policy to confirm).
- The NIN should arrive already masked in lists; the mock sends it in full and the screen masks it.
- Who may approve or reject (roles) is not defined yet, so every signed-in staff member can.
- The document preview is a placeholder until the backend provides the submitted NIN document.


# Plans & Bundles screen (v1)

Checked: type-check, lint (0 warnings) and build pass, and the new dev-server endpoints were exercised in-process.
I did not run a browser walk-through of this screen.
Needs the earlier zips already in your project (it shares the plan list with Sell SIM).

## Copy into your project (PowerShell, from the ratel-desk folder, after unzipping)
    Copy-Item "<unzipped folder>\plans-v1\src\*" -Destination ".\src" -Recurse -Force
Adds src/screens/plans/. UPDATES two files from earlier zips: src/App.tsx (Plans route) and src/lib/api.ts (adds a PUT helper).
If you edited either yourself, merge by hand. Also replace the dev server with the new ratel-dev-server.zip.

## What it does
- Two tables: Plans (price in naira, validity, data, speeds, what happens when data runs out, On sale or Retired) and Bundles
  (extra data on top of a plan). Click a row to open the drawer. The open drawer lives in the URL (?open=plan:p2).
- Create plan and Create bundle open the same drawer, empty.
- Drawer: name, price (₦, kept as whole kobo), validity, data (GB), channels, and for plans the upload and download speeds,
  the on-exhaustion choice (slow down or stop internet) and the slow speeds. Fields are checked before saving.
- Saving an existing plan or bundle first shows: "Modifying a plan applies strictly to new purchases; existing active allowances remain unchanged."
- Retire asks for confirmation. A retired plan or bundle is read-only and cannot be put back on sale.
- History tab: created, edited (what changed), retired, with who and when in WAT.
- Plans changed or retired here are what Sell SIM offers (in mock mode and with the dev server).

## Assumptions to confirm (also in src/screens/plans/api.ts and types.ts)
- Channels: the Build Plan has the field but not the values. I used RatelDesk and RatelPay.
- Retiring is one-way (create a new plan instead of un-retiring).
- Retired plans are read-only.
- Endpoints: GET/POST /v1/plans and /v1/bundles, PUT /{id}, POST /{id}/retire, GET /{id}/history.
- Who may change plans (roles) is not defined, so every signed-in staff member can.

# Stock & Vouchers screen (v1)

Checked: type-check, lint (0 warnings) and build pass, and the new dev-server endpoints were exercised in-process.
I did not run a browser walk-through of this screen.
Needs the earlier zips already in your project.

## Copy into your project (PowerShell, from the ratel-desk folder, after unzipping)
    Copy-Item "<unzipped folder>\stock-v1\src\*" -Destination ".\src" -Recurse -Force
Adds src/screens/stock/. UPDATES two files from earlier zips: src/App.tsx (route) and src/screens/sell-sim/api.ts
(numbers now come from GET /v1/stock/numbers as { items }, with state). Also replace the dev server with the new ratel-dev-server.zip.

## What it does (tabs are in the URL, e.g. ?tab=vouchers)
- SIMs: counts (in stock, in use, retired), the notice "SIM secret keys (Ki/OPc) are encrypted and transferred directly to RatelLink;
  they are never visible or stored in BSS/UI memory.", a batch import, and recent batches.
  - The import file may only have the columns iccid, imsi and batch. If it has anything else (for example Ki or OPc) the file is refused
    after reading only its first line. Rows are checked (ICCID 18 to 20 digits, IMSI 15 digits starting 62100, no repeats) and nothing is imported unless every row is valid.
- Numbers: search, Available / In use / Quarantined tabs with counts, paging, and when a quarantined number can be used again (WAT).
- Vouchers: request a batch (face value in naira, number of cards); move a batch one step at a time
  (requested, approved, sent to printer, in stock, on sale); look up a card by its 20-digit number: masked number, batch, face value, state,
  Luhn check, failed attempts this hour out of 5; and a red Lock card (reason required). PINs are never shown.
- History: imports, voucher batch steps and card locks, with who and when in WAT.

## Try it in mock mode
- Vouchers tab, look up 1000 0000 0000 0000 2222 (on sale, 3 of 5 attempts) and lock it. Try ...4821 (already locked), ...3333 (used).
- SIMs tab: import samples/sim-batch-ok.csv (works) and samples/sim-batch-with-keys.csv (refused).

## Assumptions to confirm (also in src/screens/stock/api.ts)
- Endpoints: GET /v1/stock/sims/summary, /sims/batches, POST /v1/stock/sims/import, GET /v1/stock/numbers (paged), GET and POST /v1/voucher-batches,
  POST .../{id}/advance, POST /v1/vouchers/lookup, POST /v1/vouchers/{id}/lock, GET /v1/stock/history.
- How the SIM keys actually reach RatelLink is outside this screen (supplier file to RatelLink); the screen only keeps ICCID, IMSI and batch.
- The Luhn check shown for a card is reported by the server.
- Batch-level states stop at "on sale"; cards then become used, expired or locked one by one.
- Who may approve batches or lock cards (roles) is not defined, so every signed-in staff member can.


# Reports screen (v1)

Checked: type-check, lint (0 warnings) and build pass, and the new dev-server endpoints were exercised in-process.
I did not run a browser walk-through of this screen.
Needs the earlier zips already in your project (it reuses the charts and the Wallet link).

## Copy into your project (PowerShell, from the ratel-desk folder, after unzipping)
    Copy-Item "<unzipped folder>\reports-v1\src\*" -Destination ".\src" -Recurse -Force
Adds src/screens/reports/. UPDATES two files from earlier zips: src/App.tsx (route) and src/lib/format.ts
(compact naira, data size and short date helpers). If you edited either yourself, merge by hand.
Also replace the dev server with the new ratel-dev-server.zip.

## What it does
- Range: 7, 14 or 30 days (default 14), kept in the URL (?days=30).
- Summary cards, each with a 7-day trend: daily sales revenue (with the VAT it includes), data usage total, voucher redemptions (with their value).
  Each shows the change on yesterday.
- Sales revenue chart for the range, and revenue by plan (before VAT) as a donut with percentages.
- Data usage per day (TB) and voucher redemptions per day.
- Nightly reconciliation: the latest run of the check that every wallet balance equals the sum of its ledger entries:
  a match ring, last run time (WAT), wallets checked, wallets that match, mismatches, and the last 7 nights as dots.
  If any wallet does not match, a table lists each one with its wallet, ledger sum and difference, linking to that wallet.
  It refreshes every minute.

## See a failed night in mock mode
Add this line to .env.local and restart `npm run dev`:   VITE_MOCK_RECON=mismatch

## Assumptions to confirm (also in src/screens/reports/api.ts)
- Endpoints: GET /v1/reports/overview?days= and GET /v1/reports/reconciliation.
- Revenue means what customers were charged including VAT (7.5%); revenue by plan is before VAT.
- "Data usage" is the rated usage from RatelMeter, summed per day.
- The screen only reads. It does not start a reconciliation run; the job runs by itself every night.

# Wallet & Ledger screen (v1)

Checked: type-check, lint (0 warnings) and build pass, and the new dev-server endpoints were exercised in-process.
I did not run a browser walk-through of this screen.
Needs the earlier zips already in your project (it reuses the Lines search and the VAT helper from Sell SIM).

## Copy into your project (PowerShell, from the ratel-desk folder, after unzipping)
    Copy-Item "<unzipped folder>\wallet-v1\src\*" -Destination ".\src" -Recurse -Force
Adds src/screens/wallet/. UPDATES two files from earlier zips: src/App.tsx (route) and src/components/charts/charts.tsx
(adds a grouped bar chart). If you edited either yourself, merge by hand. Also replace the dev server with the new ratel-dev-server.zip.

## What it does
- Summary cards: the sum of all line wallets, wallets with a balance, ledger entries today (since 00:00 WAT), each with a 7-day trend.
- Find a line: search by name, phone number, ICCID or IMSI, pick a line, and its wallet appears: balance in naira and a check that
  the balance equals the sum of its ledger entries. The Top-Up button on the Line Detail page links here (?line=...).
- Ledger: entry ID, line (links to the line), amount in kobo with the naira value (credits green, debits red), entry type, reference and time in WAT.
  Filters: All, Top-ups, Plan purchases, VAT, Vouchers, Corrections, each with a count. 10 per page. The filter, line and page live in the URL.
  The ledger is read-only: entries are only appended by the system, and a correction is a new entry.
- Money in and out (₦ thousands) per day for the last 7 days, shown when no single line is selected.

## Assumptions to confirm (also in src/screens/wallet/api.ts)
- Endpoints: GET /v1/wallet/summary, GET /v1/ledger?kind=&line=&page=&pageSize= (line = IMSI), GET /v1/wallets/{imsi}.
- Ledger entries carry the IMSI and phone number so the screen can link to the line (the Build Plan's ledger only has line_id).
- Staff top-ups are not built: the plan only describes vouchers and the payment gateway, which customers use on RatelPay.
- VAT is its own ledger entry (7.5% in whole kobo), as the plan says.
