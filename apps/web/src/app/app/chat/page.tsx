import { Suspense } from "react";

import { ChatPage } from "@/components/chat/ChatPage";
import { Skeleton } from "@/components/ui/Skeleton";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <ChatPage />
    </Suspense>
  );
}
