import { describe, expect, it } from "vitest";

import { stepForTarget } from "./changes";
import { baseState } from "./testState";
import { firstOpenStep, homeFor, stepsFor } from "./steps";

describe("wizard step logic", () => {
  it("resumes at the first unfinished step", () => {
    expect(firstOpenStep({ ...baseState, role: null })).toBe("role");
    expect(firstOpenStep(baseState)).toBe("contact");
    const verified = {
      ...baseState,
      contact: { ...baseState.contact!, phone_verified: true },
    };
    expect(firstOpenStep(verified)).toBe("business");
    expect(firstOpenStep({ ...verified, business: { legal_name: "X" } })).toBe(
      "documents",
    );
  });
  it("gives admins only the security step", () => {
    expect(stepsFor("ADMIN")).toEqual(["security", "review"]);
    expect(firstOpenStep({ ...baseState, role: "ADMIN" })).toBe("security");
  });
  it("routes by account status", () => {
    expect(homeFor({ ...baseState, account_status: "ACTIVE" })).toBe("/app");
    expect(
      homeFor({ ...baseState, account_status: "ACTIVE", role: "SUPPLIER" }),
    ).toBe("/supplier");
    expect(
      homeFor({ ...baseState, account_status: "PENDING_VERIFICATION" }),
    ).toBe("/onboarding/status");
    expect(
      homeFor({
        ...baseState,
        account_status: "PENDING_VERIFICATION",
        decision: "CHANGES_REQUESTED",
      }),
    ).toBeNull();
    expect(homeFor({ ...baseState, account_status: "REJECTED" })).toBe(
      "/account-status?reason=rejected",
    );
    expect(homeFor(baseState)).toBeNull();
  });
  it("maps change-request targets to wizard steps", () => {
    expect(stepForTarget("IRC")).toBe("documents");
    expect(stepForTarget("mobile")).toBe("contact");
    expect(stepForTarget("uscc")).toBe("business");
    expect(stepForTarget("consent")).toBe("security");
  });
});
