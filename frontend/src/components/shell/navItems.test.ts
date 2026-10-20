import { describe, expect, it } from "vitest";

import { navGroups } from "./navItems";

const hrefs = (role: string | undefined) => navGroups(role).flatMap((g) => g.items.map((i) => i.href));

describe("navGroups role gating", () => {
  it("shows the onboarding review entry only to ADMIN", () => {
    expect(hrefs("ADMIN")).toContain("/app/admin/verifications");
    for (const role of ["JUDGE", "BUYER", "SUPPLIER", undefined]) {
      expect(hrefs(role)).not.toContain("/app/admin/verifications");
    }
  });

  it("shows the team page to buyers only", () => {
    expect(hrefs("BUYER")).toContain("/app/team");
    expect(hrefs("ADMIN")).not.toContain("/app/team");
    expect(hrefs("JUDGE")).not.toContain("/app/team");
  });
});
