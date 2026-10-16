"use client";

import { useState } from "react";

import { getDemoUsers, getMe } from "@/lib/api/auth";
import { useApi } from "@/lib/useApi";

/** Buyers use their own business; admin/judge must pick one (the API returns 400 otherwise). */
export function useBuyerScope() {
  const me = useApi(getMe, "me-role");
  const needsPicker = me.data?.role === "ADMIN" || me.data?.role === "JUDGE";
  const users = useApi(getDemoUsers, "users-for-picker", needsPicker);
  const [party, setParty] = useState("");
  const buyers = (users.data?.users ?? []).filter(
    (u) => u.role === "BUYER" && u.party_id,
  );
  return {
    ready: me.data !== undefined && (!needsPicker || party !== ""),
    needsPicker,
    party,
    setParty,
    buyers,
    error: me.error ?? users.error,
    reload: me.error ? me.reload : users.reload,
  };
}
