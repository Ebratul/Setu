type Props = { label: string; value: string; good: boolean | null };

export function StatusRow({ label, value, good }: Props) {
  const dot = good === null ? "bg-muted" : good ? "bg-success" : "bg-danger";
  const icon = good === null ? "…" : good ? "✓" : "✕";
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <dt className="text-muted">{label}</dt>
      <dd className="flex items-center gap-2 font-medium">
        <span aria-hidden="true" className={`size-2.5 rounded-full ${dot}`} />
        <span aria-hidden="true">{icon}</span>
        <span>{value}</span>
      </dd>
    </div>
  );
}
