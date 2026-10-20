import { Suspense } from "react";

import { AccountStatusScreen } from "@/components/auth/AccountStatusScreen";

export default function AccountStatusPage() {
  return (
    <Suspense>
      <AccountStatusScreen />
    </Suspense>
  );
}
