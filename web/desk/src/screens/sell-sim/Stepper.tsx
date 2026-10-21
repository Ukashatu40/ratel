const STEPS = ["Customer & KYC", "SIM & Number", "Choose Plan", "Review & Activate"];

// Finished steps can be clicked to go back. Later steps are unlocked only by Continue.
export function Stepper({ current, onGo }: { current: number; onGo: (i: number) => void }) {
  return (
    <ol className="sell-steps" aria-label="Progress">
      {STEPS.map((label, i) => {
        const state = i < current ? "done" : i === current ? "current" : "todo";
        return (
          <li key={label}>
            <button type="button" className={`sell-step sell-step--${state}`} disabled={state !== "done"} onClick={() => onGo(i)} aria-current={state === "current" ? "step" : undefined}>
              <i>{i + 1}</i>{label}
            </button>
          </li>
        );
      })}
    </ol>
  );
}