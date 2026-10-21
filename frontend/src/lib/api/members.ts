import type { components } from "./schema.gen";
import { apiDelete, apiGet, apiPost } from "./client";

type S = components["schemas"];
export type Member = S["MemberOut"];
export type MemberList = S["MemberList"];
export type MemberRole = Member["member_role"];
export type InviteInput = S["InviteIn"];

export const listMembers = (partyId: string, signal?: AbortSignal) =>
  apiGet<MemberList>(`/parties/${partyId}/members`, { signal, cache: "no-store" });
export const inviteMember = (partyId: string, body: InviteInput) =>
  apiPost<Member>(`/parties/${partyId}/members`, body);
export const removeMember = (partyId: string, userId: string) =>
  apiDelete<void>(`/parties/${partyId}/members/${userId}`);
