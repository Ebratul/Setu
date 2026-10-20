"use client";

import { ErrorPageView } from "@/components/shell/ErrorPageView";

export default function Error(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorPageView {...props} />;
}
