"use client";

import { createContext, useContext } from "react";

import type { AppUser } from "@/lib/api/auth";

/** The signed-in user as already loaded by the app shell, so children need not refetch /auth/me. */
export const MeContext = createContext<AppUser | undefined>(undefined);

export function useShellUser(): AppUser | undefined {
  return useContext(MeContext);
}
