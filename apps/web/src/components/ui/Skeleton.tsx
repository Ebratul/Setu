type Props = { className?: string };

export function Skeleton({ className = "h-6 w-full" }: Props) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-md bg-line ${className}`}
    />
  );
}
