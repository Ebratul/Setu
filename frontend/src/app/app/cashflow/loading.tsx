import { Skeleton } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <div aria-busy="true" className="space-y-4">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-80" />
    </div>
  );
}
