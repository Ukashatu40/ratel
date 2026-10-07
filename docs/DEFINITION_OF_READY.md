# Definition of Ready

Nobody starts implementation until the issue has all of this. It does not need to be long. It needs
to be checkable.

- **Objective** in one or two sentences.
- **Source**: the Build Plan section, weekly gate, or PRD requirement id it serves. If it serves none, ask whether it belongs before the demo.
- **Deliverable-sized.** Finishable and reviewable in a few days at most. "Build RatelBSS" is not ready; "Implement Line state machine" is. See [TASK_MANAGEMENT.md](TASK_MANAGEMENT.md).
- **Scope and out of scope**, including a check against the Build Plan's "What not to build yet" list.
- **Acceptance criteria** that can pass or fail.
- **Dependencies** named: other issues, contract fields still marked TODO, lab access, network-team input, SIM keys.
- **Contract impact** known: does `openapi.yaml` change? Is there a mock the developer can use meanwhile?
- **Data, security and privacy requirements** stated, or "none". Does it touch Ki, OPc, NIN, money, call records?
- **Testing requirements**, including whether a lab run is needed.
- **Priority and risk** set (see [PRIORITY_RISK_FRAMEWORK.md](PRIORITY_RISK_FRAMEWORK.md)). Risk decides reviewer count.
- **Reviewer(s)** named. Two for RatelLink and RatelBSS: money.
- **Owner** assigned by the project lead. Never self-assigned for critical areas.
- **Target date** inside the week it serves.

If any item is unknown, write `TODO` in the issue and resolve it before the status moves to Ready.
