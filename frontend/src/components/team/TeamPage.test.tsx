import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang, user } from "@/components/shell/testUtils";
import { ApiError } from "@/lib/api/client";
import { MeContext } from "@/lib/MeContext";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/lib/api/auth", () => ({ getMe: vi.fn() }));

const listMembers = vi.fn();
const inviteMember = vi.fn();
const removeMember = vi.fn();
vi.mock("@/lib/api/members", () => ({
  listMembers: (...a: unknown[]) => listMembers(...a),
  inviteMember: (...a: unknown[]) => inviteMember(...a),
  removeMember: (...a: unknown[]) => removeMember(...a),
}));

import { TeamPage } from "./TeamPage";

const me = { ...user("BUYER"), party_id: "party-1" };
const member = (id: string, role: string, signed = true) => ({
  user_id: id,
  email: `${id}@acme.example`,
  display_name: `Person ${id}`,
  member_role: role,
  status: "ACTIVE",
  signed_in_once: signed,
  created_at: "2026-10-01T00:00:00Z",
});

function renderTeam() {
  return renderI18n(
    <MeContext.Provider value={me}>
      <TeamPage />
    </MeContext.Provider>,
  );
}

function invite(email = "new@acme.example", name = "New Person") {
  fireEvent.change(screen.getByLabelText("Email address"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: name } });
  fireEvent.click(screen.getByRole("button", { name: "Add member" }));
}

describe("TeamPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setLang("en");
    listMembers.mockResolvedValue({
      party_id: "party-1",
      items: [member(me.id, "OWNER"), member("u2", "FINANCE", false)],
    });
  });

  it("lists members with role and the signed-in flag, and explains that no email is sent", async () => {
    renderTeam();
    expect((await screen.findAllByText("Person u2")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Finance").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not signed in yet").length).toBeGreaterThan(0);
    expect(screen.getByText(/No email is sent/)).toBeInTheDocument();
  });

  it("validates the invite form before calling the API", async () => {
    renderTeam();
    await screen.findByLabelText("Email address");
    invite("not-an-email", "X");
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(inviteMember).not.toHaveBeenCalled();
  });

  it("invites a member and refreshes the list", async () => {
    inviteMember.mockResolvedValue(member("u3", "VIEWER"));
    renderTeam();
    await screen.findByLabelText("Email address");
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "VIEWER" } });
    invite();
    await waitFor(() =>
      expect(inviteMember).toHaveBeenCalledWith("party-1", {
        email: "new@acme.example",
        display_name: "New Person",
        member_role: "VIEWER",
      }),
    );
    expect(await screen.findByText(/new@u3|was added/)).toBeInTheDocument();
    expect(listMembers.mock.calls.length).toBeGreaterThan(1);
  });

  it.each([
    [409, "EMAIL_IN_USE", /already belongs to a Setu account/],
    [409, "PARTY_NOT_VERIFIED", /must be approved/],
    [403, "VIEWER_READ_ONLY", /read-only/],
  ])("maps invite error %s %s", async (status, code, text) => {
    inviteMember.mockRejectedValue(new ApiError(status, "x", null, code));
    renderTeam();
    await screen.findByLabelText("Email address");
    invite();
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("asks before removing and maps LAST_OWNER inside the dialog", async () => {
    removeMember.mockRejectedValue(new ApiError(409, "x", null, "LAST_OWNER"));
    renderTeam();
    fireEvent.click((await screen.findAllByRole("button", { name: "Remove Person u2" }))[0]);
    const dialog = await screen.findByRole("dialog");
    expect(removeMember).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/at least one owner/);
    expect(removeMember).toHaveBeenCalledWith("party-1", "u2");
  });

  it("hides write controls for a viewer", async () => {
    listMembers.mockResolvedValue({ party_id: "party-1", items: [member(me.id, "VIEWER"), member("u2", "OWNER")] });
    renderTeam();
    await screen.findAllByText("Person u2");
    expect(screen.queryByLabelText("Email address")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Remove/ })).toBeNull();
  });

  it("shows the friendly no-access state when the server answers 403", async () => {
    listMembers.mockRejectedValue(new ApiError(403, "x", null, "FORBIDDEN"));
    renderTeam();
    expect(await screen.findByText(/access/i)).toBeInTheDocument();
  });
});
