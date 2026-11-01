import { useInfiniteQuery } from "@tanstack/react-query";
import { Badge } from "../../components/ui";
import { formatCount, formatDayWAT, formatMB, formatTimeWAT } from "../../lib/format";
import { getUsage } from "./api";

// Usage records are 5-minute intervals read from the user plane (ogstun) by RatelMeter, newest first. The API pages them
// with a cursor, so older ones are loaded on request.
export function UsageTab({ lineKey }: { lineKey: string }) {
  const { data, isPending, isError, refetch, hasNextPage, fetchNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ["line", lineKey, "usage"],
    queryFn: ({ pageParam }) => getUsage(lineKey, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.nextCursor,
  });
  const items = data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <section className="card ld-table">
      <h3>Usage: 5-minute intervals</h3>
      {isError ? <div className="ld-message">Could not load usage. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div> : (
        <table className="data-table">
          <thead><tr><th>Interval (WAT)</th><th>Uploaded (MB)</th><th>Downloaded (MB)</th><th>Rated</th></tr></thead>
          <tbody>
            {isPending && <tr><td colSpan={4} className="muted">Loading...</td></tr>}
            {items.map((r) => (
              <tr key={r.periodStart}>
                <td>{formatDayWAT(r.periodStart)}, {formatTimeWAT(r.periodStart)} to {formatTimeWAT(r.periodEnd)}</td>
                <td>{formatMB(r.bytesUp)}</td><td>{formatMB(r.bytesDown)}</td>
                <td>{r.rated ? <Badge tone="green">Rated</Badge> : <Badge tone="amber">Not yet</Badge>}</td>
              </tr>
            ))}
            {data && items.length === 0 && <tr><td colSpan={4} className="muted">No usage in the last 24 hours.</td></tr>}
          </tbody>
        </table>
      )}
      <div className="ld-footer">
        <span className="muted">{formatCount(items.length)} intervals shown, from the last 24 hours</span>
        {hasNextPage && (
          <button type="button" className="chip" onClick={() => void fetchNextPage()} disabled={isFetchingNextPage}>{isFetchingNextPage ? "Loading..." : "Show older"}</button>
        )}
      </div>
    </section>
  );
}
