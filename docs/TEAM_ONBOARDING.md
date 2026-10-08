# Team onboarding: learning the flow by doing it

Most of the team has not worked in a shared codebase with reviews and checks before. That is normal
and fixable. The fastest way to learn the flow in [WORKFLOW.md](WORKFLOW.md) is to run it end to end on a
tiny real change in the first two days, then grow from there. This page is the plan for the
project lead (who teaches) and for the new person (who learns).

## Principles

1. **Learn the process on a small change, not on a hard task.** The first pull request should be easy,
   so the only new thing is the flow.
2. **Real work, small slices.** Every starter task is a real, useful piece of the plan with a clear
   spec, tests, and a reviewer who will read it.
3. **Reviews teach.** A review comment is a lesson. Review kindly, say why, and suggest a fix.
4. **Ask early, in the open.** Questions go in the issue or the pull request, so the answer helps the next person.
5. **Safety rails do the policing.** `main` is protected, CI must pass, risky areas need two people.
   Nobody can break production by making a normal mistake. Mistakes are cheap here. Hiding them is not.

## Before day 1

| Everyone | |
| -------- | - |
| GitHub | Two-factor authentication on. Accept the repository invitation. Your username matches `.github/CODEOWNERS` |
| Tools | Git, Python 3.12, `make`, a code editor. Docker is optional (local databases). On Windows use WSL2 with Ubuntu, because `make` and the scripts need it |
| Access | The Build Plan and the PRD, shared privately by the project lead (they are not in the repository). Read only what your role needs first |

## The first two days

| When | What | Who helps |
| ---- | ---- | --------- |
| Day 1 morning | **Session 1: the flow, live** (below). Then clone, `make install`, `make check` | Project lead |
| Day 1 afternoon | **Practice pull request** (below). Fill in the onboarding issue checklist as you go | Your mentor |
| Day 2 morning | Review someone else's practice PR (comments only). Get your own reviewed | Your mentor |
| Day 2 afternoon | **Session 2 and 3** for your role. Read your first real issue and ask your questions in it | Project lead |
| Day 3 | Start the first real task | Your mentor |

The project lead creates one **Onboarding** issue per person from the issue form. Its checklist is the
definition of "onboarded".

## The sessions (60 to 90 minutes each, with an exercise)

1. **The flow, live.** The lead does the whole of [WORKFLOW.md](WORKFLOW.md) on screen with a trivial change:
   create an issue from a form, make a branch, change one line, run `make check`, push, open a PR,
   watch CI, request review, answer a comment, squash merge, watch the issue close. Everyone then does
   the same on their own practice change. *Exercise: your practice PR.*
2. **Git for this project.** `status`, `add`, `commit`, `switch -c`, `push`, `pull`, how to read a diff,
   how to undo a mistake (`git restore`, `git revert`). Rules: never force push, never work on `main`,
   never commit secrets. If you commit something you should not have, stop and tell the lead: deleting
   the commit is not enough, a leaked secret must be replaced. *Exercise: fix a deliberately messy branch.*
3. **Reading and writing a review.** Take a real merged PR (for example the RatelLink key code, #10, or
   the code organisation PR) and review it together with the checklist from
   [CODE_REVIEW_GUIDELINES.md](CODE_REVIEW_GUIDELINES.md). Learn to label comments *blocker*, *suggestion* or
   *question*, and to say what you checked. *Exercise: write three comments on a small PR.*
4. **The code and its layers** (backend people: Abbalolo, ml-lawarn, capitanaserdel for review). A tour of
   `services/ratel_link/`: `api`, `services`, `domain`, `repositories`, `security`, and why imports only go
   inward. Run the tests, add one. Run the service and call `/healthz`. *Exercise: add a test for an existing function.*
5. **Security habits** (30 minutes, everyone). What must never be committed or pasted anywhere
   (keys, Ki/OPc, NINs, real customer or call data, production logs). Why the repository being public
   matters. How logging redacts, why tests use synthetic data, and the rules for AI tools in
   [AI_ENGINEERING_POLICY.md](AI_ENGINEERING_POLICY.md). *Exercise: find the three places the repo guards against a leaked secret.*
6. **Frontend conventions** (led by capitanaserdel, for the frontend people). Folder structure, the API mock,
   and the 3G page budget for RatelPay. *Exercise: run the mock and read one response.*

## The practice pull request

Pick **one**. It must be small, safe, and real.

- Follow the setup guide ([DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md)) on your machine and fix the first sentence that was wrong or unclear.
- Fix a typo or an unclear sentence in a document you read this week.
- Add one test for an existing function that has none for an edge case.
- Fill in a `TODO` that is a plain fact you can verify yourself.

The point is to feel every step: issue, branch, commit, PR, CI, review, merge. A merged practice
PR is a success even if the change is tiny.

## First real tasks (proposed by role)

These come from [issues-week2/README.md](issues-week2/README.md). They are chosen to be pure logic with a clear spec,
no database or network needed, so the learning is the flow and the tests.

| Person | Mentor | First real task | Why it suits |
| ------ | ------ | --------------- | ------------ |
| @Abbalolo | @Ukashatu40 | W2-13: the line state machine (a table and its tests) | Python basics and tests, a table straight from the Build Plan, builds toward BSS lines |
| @ml-lawarn | @CaptRaven, with @Ukashatu40 | W2-14: counter delta and interval logic for the meter agent, then W2-15 the disk spool | Pure functions and failure cases, close to Flask-sized Python, builds toward RatelMeter |
| @Arfaaah | @capitanaserdel | W2-17: follow the setup guide on a clean machine and fix what is unclear | The best use of fresh eyes. Teaches the whole toolchain without risk |
| @capitanaserdel | @Ukashatu40 | W2-16: first-pass read of the RatelLink key code with the security checklist | Becomes the standing second approver, so must know the code that holds the keys |

## Learning to review: a ladder

| Stage | What you do | Counts as approval? |
| ----- | ----------- | ------------------- |
| Week 1 | Watch. Read the reviews on your own PR | No |
| Weeks 2 to 3 | Review small PRs with **comments only**. Your mentor reads your review afterwards | No |
| After that | Approve low-risk changes (`risk:low`, `risk:medium`) in areas you understand | Yes, but never as the only reviewer |
| Later, by decision of the project lead | Approve `risk:high` | Yes |
| Only named people | `risk:critical` (RatelLink, money): the independent reviewer and the standing second approver | Yes |

The review gate counts any two approvals on a critical change, so the rule is a team agreement:
**interns and junior developers do not approve RatelLink or RatelBSS: money changes**, however
confident they feel. Approving means you are answerable for the change.

## Habits that make a small team work

- **Small pull requests.** One issue, one PR, reviewable in half an hour. A 600-line PR does not get a real review.
- **Draft early.** Open a Draft PR when you are half done and unsure. Feedback on day 1 beats a rewrite on day 4.
- **Stuck for 30 minutes? Ask.** In the issue, with what you tried and the exact error. Do not stay silent.
- **Daily one-line update on your issue:** done yesterday, doing today, blocked by. Silence is the real risk.
- **Answer review comments within a day.** Reviewers answer within half a day. Both sides keep the queue short.
- **Read the error, then ask.** Paste the real error text (never a secret). "It doesn't work" cannot be answered.
- **AI tools are allowed but you own every line.** You must be able to explain it. Never paste secrets or customer data into one.

## Common mistakes

| Mistake | What happens | Do this instead |
| ------- | ------------ | --------------- |
| Committing to `main` | GitHub refuses the push | Always `git switch -c` first |
| A huge PR | Nobody reviews it properly | Split by deliverable, one issue per PR |
| Not running `make check` | CI fails, everyone waits | Run it before every push |
| "Fixing" CI by disabling a check | Hides a real problem | Fix the cause. Never skip a check or a test |
| Pushing after approval without telling | The approval is removed | Re-request review after every push |
| Approving without reading | You own a bug you did not look at | Read the diff, run it, say what you checked |
| Pasting a key or a customer's number into chat or an issue | Exposure | Stop, tell the lead, the secret must be replaced |
| Working in private for days | Late surprises | Draft PR, daily update |
| Guessing what the spec means | Wrong work | Ask in the issue. The Build Plan, PRD and contract decide |

## Checklist (also the onboarding issue)

- [ ] Two-factor authentication on, invitation accepted, Project board visible
- [ ] Read README.md, CONTRIBUTING.md, [WORKFLOW.md](WORKFLOW.md)
- [ ] `make install` and `make check` pass on my machine
- [ ] I know what must never be committed, and who to tell if I do
- [ ] Practice PR merged
- [ ] I reviewed someone else's PR (comments only)
- [ ] I wrote down what was unclear in the setup guide
- [ ] My first real task is assigned and I understand its acceptance criteria

## For the project lead: teaching this

- **Run Session 1 once, for everyone.** It is the single most valuable hour.
- **Do not fix their code for them.** Review it. They learn from the comment, not from your commit.
- **Pair for the first hour of the first real task**, then let them work and check in at the end of the day.
- **Spread the mentoring.** Peers can review each other's practice PRs (comments only). capitanaserdel
  mentors the frontend people. @CaptRaven mentors the meter work. You mentor the backend slice. Otherwise you
  become the bottleneck for both coding and teaching.
- **Make the first merges visible.** A merged first PR is a small win worth saying out loud.
- **Expect the first PR to take most of a day.** By the third it takes an hour.
