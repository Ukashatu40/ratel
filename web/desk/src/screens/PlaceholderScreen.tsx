export default function PlaceholderScreen({ title, reason }: { title: string; reason?: string }) {
  return (
    <div>
      <h1>{title}</h1>
      <p className="muted" style={{ marginTop: 6 }}>{reason ?? "This screen is coming soon."}</p>
    </div>
  );
}
