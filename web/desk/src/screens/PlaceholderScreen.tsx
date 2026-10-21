export default function PlaceholderScreen({ title }: { title: string }) {
  return (
    <div>
      <h1>{title}</h1>
      <p className="muted" style={{ marginTop: 6 }}>This screen is coming soon.</p>
    </div>
  );
}