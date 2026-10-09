# Team structure

**Assignments below were made by the project lead on 2026-10-08**, from the lead's own knowledge of
each person. The skill matrix is still the lead's to fill in (`?` means not assessed). Job titles
are not a proxy for ability: if an assessment changes an assignment, change
[OWNERSHIP_MATRIX.md](OWNERSHIP_MATRIX.md), `.github/CODEOWNERS` and the issue owners together.

## The team (GitHub usernames)

| GitHub | Role | Background, as stated by the project lead | Works on |
| ------ | ---- | ----------------------------------------- | -------- |
| @Ukashatu40 | **Project lead.** Mid-senior backend-focused full-stack developer | All the relevant skills | RatelLink, RatelBSS: money, contracts, governance (CI, GitHub, ADRs) |
| @CaptRaven | **Independent reviewer.** Software and network engineer | Software and network | Required approver on RatelLink and money; contracts; the Linux counter spike and meter agent design; network-facing reviews |
| @capitanaserdel | Mid-senior frontend and mobile developer. **Frontend lead.** Standing second approver on critical changes | Frontend, mobile | RatelDesk; reviews frontend, RatelPay, BSS lines, the RatelMeter API |
| @Abbalolo | Junior to mid frontend-focused full-stack developer | Uses Supabase for backends; learned Express once, never built a project with it | RatelBSS: lines and its screens |
| @ml-lawarn | Junior frontend and mobile developer | Some small Flask experience | RatelMeter API (`/v1/usage`, `/v1/calls`) |
| @Arfaaah | Intern | HTML, CSS and JavaScript | RatelPay page (plain HTML, CSS and JS suits the 3G rule), supervised |

The software team is the lead, the independent reviewer and four developers. The network team
(RatelCore, RatelVoice, RatelOps, radio) is separate. TODO: confirm whether @CaptRaven is the
network lead the Build Plan describes, and name the rest of the network team.

The software team owns the business and software side. The Network team owns the network side.
Respect that boundary. See [ARCHITECTURE.md](ARCHITECTURE.md).

### What this team shape means

- **There is one strong backend developer** (the lead). The Build Plan's single-backend sequence is
  RatelLink, then a thin slice of BSS lines, then RatelMeter, then BSS money, and warns that
  RatelLink's owner should be the most careful developer. Everything critical sits with the lead,
  and the lead cannot approve their own pull requests. That is risk R-08.
- **Python and FastAPI are new to most of the team.** Three developers have not built with FastAPI.
  Give them small, well-specified first tasks, pair them with the lead, and rely on the existing
  tests and [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md).
- **Two approvers, not one, for the code that holds keys and money.** When the lead writes a
  RatelLink or RatelBSS: money change, @CaptRaven must approve plus one more person, normally
  @capitanaserdel. The gate (`critical-review-gate`) enforces two distinct approvals and names
  @Ukashatu40 and @CaptRaven as required. See [ADR 0004](adr/0004-two-reviewer-enforcement.md).
- **No junior or intern is the only code owner of a path.** `.github/CODEOWNERS` always lists a
  senior as well, and a test keeps every rule at two or more owners.
- **Review load concentrates on @CaptRaven**, who is also on the network team (risk R-10). Watch it.

## Known role categories

- **Project lead:** priorities, assignments, final say on architecture decisions and contract changes.
- **Independent reviewer:** required approver on critical changes (RatelLink, RatelBSS: money).
- **Workstream owner:** accountable for a workstream's delivery. See the ownership matrix.
- **Backup:** can take over a workstream. Mostly none yet.
- **Network lead:** Network team counterpart for RatelLink, RatelMeter and RatelVoice touchpoints. TODO: confirm who.
- **Frontend lead:** @capitanaserdel. Owns RatelDesk and RatelPay review routing.

## Proposed workstream categories

Taken from the Build Plan: Contracts, RatelLink, RatelMeter (agent and API), RatelBSS: lines,
RatelBSS: money, RatelDesk and RatelPay, plus repository/CI/GitHub governance. RatelVoice, RatelOps
and RatelCore belong to the Network team. The Build Plan's guidance for the split: one careful
developer owns RatelLink (it holds every line's keys), the network-facing work (Linux, MongoDB,
packet counters) and the application work (pure application code) are different skills, and
RatelDesk and RatelPay need a frontend developer from week two. With fewer than four backend
developers, whoever owns BSS lines builds its screens too.

## Technical skill assessment matrix

Filled in by the project lead. Suggested scale: `0` none, `1` basic, `2` working, `3` strong, `?` not assessed.

| Person | Role | React | Next.js | TypeScript | Python | FastAPI | Node.js | SQL | PostgreSQL | MongoDB | Docker | Linux | Testing | Git/GitHub | Security | Backend | Frontend | Notes |
| ------ | ---- | ----- | ------- | ---------- | ------ | ------- | ------- | --- | ---------- | ------- | ------ | ----- | ------- | ---------- | -------- | ------- | -------- | ----- |
| @Ukashatu40 | Project lead | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | Stated by the lead: all relevant skills |
| @Abbalolo | Dev | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | Supabase (PostgreSQL) backends; Express learned, not used |
| @ml-lawarn | Dev | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | Small Flask experience |
| @capitanaserdel | Dev, frontend lead | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | Mid-senior frontend and mobile |
| @Arfaaah | Intern | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | HTML, CSS, JavaScript |
| @CaptRaven | Independent reviewer | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | Software and network |

## Ownership matrix

See [OWNERSHIP_MATRIX.md](OWNERSHIP_MATRIX.md).

## Reviewer matrix

| Area | Reviewers required | Who |
| ---- | ------------------ | --- |
| RatelLink (`services/ratel_link/`) | **2** | @Ukashatu40 and @CaptRaven. If the lead is the author: @CaptRaven plus one more, normally @capitanaserdel |
| RatelBSS: money (`services/app/bss_money/`) | **2** | Same as RatelLink |
| Contracts (`contracts/`) | 1, controlled | @Ukashatu40 or @CaptRaven (the network lead is consulted) |
| RatelBSS: lines, RatelMeter API | 1 | @Ukashatu40 or @capitanaserdel |
| RatelMeter agent | 1 | @Ukashatu40 or @CaptRaven |
| RatelDesk, RatelPay | 1 | @capitanaserdel or @Ukashatu40 |
| RatelVoice and RatelOps configuration | 1 | @CaptRaven or @Ukashatu40. TODO: the network lead |
| CI, GitHub governance | 1, controlled | @Ukashatu40 or @capitanaserdel. The review-gate files also need @CaptRaven |
| Security documents | 1, controlled | @Ukashatu40 or @CaptRaven |

"or" means one approval from any listed person satisfies GitHub's code-owner rule (see
`.github/CODEOWNERS`). The author is never one of the approvers.

The author never reviews their own PR. Avoid making one person the reviewer for everything.

## Escalation path

1. **Blocked on a technical question:** ask in the issue; if unresolved within half a day, the workstream owner, then the project lead.
2. **Needs the network team** (RatelCore, RatelVoice, lab access, SIM keys, call record fields): the network lead. TODO: confirm contact.
3. **Product behavior unclear or Build Plan and PRD seem to disagree:** the project lead. The PRD wins.
4. **Architecture or contract decision:** the project lead, via an ADR. Do not decide silently.
5. **Security concern or leaked secret:** the private channel in [../SECURITY.md](../SECURITY.md), never a public issue or chat.
6. **Weekly gate at risk:** the project lead, as soon as it is visible. Risks go in [RISK_REGISTER.md](RISK_REGISTER.md).
7. **Voice decision (Oct 16) and scope changes:** management decides, via the project lead.
