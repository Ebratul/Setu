"use client";

import { createContext, useContext } from "react";

import type { DemoUser } from "@/lib/api/auth";

/** The signed-in user as already loaded by the app shell, so children need not refetch /auth/me. */
export const MeContext = createContext<DemoUser | undefined>(undefined);

export function useShellUser(): DemoUser | undefined {
  return useContext(MeContext);
}
