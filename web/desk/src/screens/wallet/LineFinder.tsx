import { useDeferredValue, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getLines } from "../lines/api";

// Search for a line by name, phone number, ICCID or IMSI and pick it to see its wallet.
export function LineFinder({ onPick }: { onPick: (imsi: string) => void }) {
  const [text, setText] = useState("");
  const term = useDeferredValue(text.trim());
  const { data, isFetching } = useQuery({ queryKey: ["wallet-line-search", term], queryFn: () => getLines({ q: term, tab: "all", page: 1, pageSize: 6 }), enabled: term.length >= 2 });
  return (
    <div className="wal-finder">
      <div className="card wal-finder__box">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Find a line wallet by phone number, ICCID or IMSI" aria-label="Find a line wallet" />
        {isFetching && <span className="muted">Searching...</span>}
      </div>
      {term.length >= 2 && data && (
        <div className="card wal-finder__list" role="listbox">
          {data.items.length === 0 && <div className="muted wal-finder__empty">No line matches.</div>}
          {data.items.map((l) => (
            <button key={l.imsi} type="button" role="option" aria-selected="false" onClick={() => { onPick(l.imsi); setText(""); }}>
              <b>{l.msisdn}</b><span className="muted">{l.customerName} &nbsp;|&nbsp; {l.planName}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
