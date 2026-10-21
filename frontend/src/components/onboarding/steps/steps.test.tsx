import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang } from "@/components/shell/testUtils";
import { ApiError } from "@/lib/api/client";
import { baseState } from "@/lib/onboarding/testState";

const api = vi.hoisted(() => ({
  selectRole: vi.fn(),
  saveContact: vi.fn(),
  sendPhoneCode: vi.fn(),
  verifyPhoneCode: vi.fn(),
  saveBusiness: vi.fn(),
  saveConsent: vi.fn(),
  submitProfile: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
}));
vi.mock("@/lib/api/onboarding", () => api);

import { BusinessStep } from "./BusinessStep";
import { ContactStep } from "./ContactStep";
import { DocumentsStep } from "./DocumentsStep";
import { ReviewStep } from "./ReviewStep";
import { RoleStep } from "./RoleStep";
import { SecurityStep } from "./SecurityStep";

const noop = () => {};
const props = (over: Partial<typeof baseState> = {}) => ({ state: { ...baseState, ...over }, onState: vi.fn(), onNext: vi.fn() });

beforeEach(() => {
  vi.clearAllMocks();
  setLang("en");
});

describe("RoleStep", () => {
  it("asks for a role, shows the invite field for judges and calls the API", async () => {
    const p = props({ role: null });
    api.selectRole.mockResolvedValue({ ...baseState, role: "JUDGE" });
    renderI18n(<RoleStep {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("alert").textContent).toMatch(/Choose a role/);
    fireEvent.click(screen.getByLabelText(/^Judge/));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("alert").textContent).toMatch(/invite code/);
    fireEvent.change(screen.getByLabelText(/Invite code/), { target: { value: "JUDGE-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(api.selectRole).toHaveBeenCalledWith("JUDGE", "JUDGE-1"));
    expect(p.onNext).toHaveBeenCalled();
  });

  it("shows a friendly message for a wrong invite code", async () => {
    api.selectRole.mockRejectedValue(new ApiError(403, "x", null, "INVALID_INVITE_CODE"));
    renderI18n(<RoleStep {...props({ role: null })} />);
    fireEvent.click(screen.getByLabelText(/^Judge/));
    fireEvent.change(screen.getByLabelText(/Invite code/), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That invite code is not valid.");
  });

  it("locks the chosen role once set", () => {
    renderI18n(<RoleStep {...props({ role: "SUPPLIER" })} />);
    expect((screen.getByLabelText(/^Buyer/) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText(/^Supplier/) as HTMLInputElement).checked).toBe(true);
  });
});

describe("ContactStep", () => {
  it("validates a Bangladesh mobile number before saving", async () => {
    renderI18n(<ContactStep {...props({ contact: null })} />);
    fireEvent.change(screen.getByLabelText(/Full name/), { target: { value: "Rahim Uddin" } });
    fireEvent.change(screen.getByLabelText(/Job title/), { target: { value: "Director" } });
    fireEvent.change(screen.getByLabelText(/Mobile number/), { target: { value: "01212345678" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and verify phone" }));
    expect(await screen.findByText(/Enter a Bangladesh mobile number/)).toBeTruthy();
    expect(api.saveContact).not.toHaveBeenCalled();
  });

  it("saves the contact, sends a code, shows the demo code and verifies", async () => {
    const saved = { ...baseState, contact: { ...baseState.contact!, phone_verified: false } };
    api.saveContact.mockResolvedValue(saved);
    api.sendPhoneCode.mockResolvedValue({ sent: true, expires_in_seconds: 300, sends_left: 2, demo_code: "123456" });
    api.verifyPhoneCode.mockResolvedValue({ ...saved, contact: { ...saved.contact!, phone_verified: true } });
    const p = props({ contact: null });
    const view = renderI18n(<ContactStep {...p} />);
    fireEvent.change(screen.getByLabelText(/Full name/), { target: { value: "Rahim Uddin" } });
    fireEvent.change(screen.getByLabelText(/Job title/), { target: { value: "Director" } });
    fireEvent.change(screen.getByLabelText(/Mobile number/), { target: { value: "01712345678" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and verify phone" }));
    await waitFor(() => expect(api.saveContact).toHaveBeenCalledWith({ full_name: "Rahim Uddin", designation: "Director", mobile: "+8801712345678", language: "en" }));
    view.unmount();

    const p2 = props();
    renderI18n(<ContactStep {...p2} />);
    expect(screen.getByRole("button", { name: "Next" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));
    expect((await screen.findByTestId("demo-code")).textContent).toBe("123456");
    fireEvent.change(screen.getByLabelText(/6-digit code/), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify phone" }));
    await waitFor(() => expect(api.verifyPhoneCode).toHaveBeenCalledWith("123456"));
    expect(p2.onState).toHaveBeenCalled();
  });

  it("does not show a demo code when the API sends none", async () => {
    api.sendPhoneCode.mockResolvedValue({ sent: true, expires_in_seconds: 300, sends_left: 2 });
    renderI18n(<ContactStep {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));
    await screen.findByText(/Code sent/);
    expect(screen.queryByTestId("demo-code")).toBeNull();
  });

  it("explains a locked or expired code", async () => {
    api.sendPhoneCode.mockResolvedValue({ sent: true, expires_in_seconds: 300, sends_left: 1 });
    api.verifyPhoneCode.mockRejectedValue(new ApiError(410, "x", null, "OTP_EXPIRED"));
    renderI18n(<ContactStep {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));
    fireEvent.change(await screen.findByLabelText(/6-digit code/), { target: { value: "111111" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify phone" }));
    expect((await screen.findByText(/has expired/))).toBeTruthy();
  });
});

const buyerFill: Record<string, string> = {
  "Legal company name": "Dhaka Traders Ltd",
  "Trade licence number": "TRAD/DNCC/012345/2024",
  "Issuing authority": "DNCC",
  "Licence expiry date": "2099-01-01",
  "Import Registration Certificate (IRC) number": "BA-0123456",
  TIN: "123456789012",
  Division: "Dhaka",
  District: "Dhaka",
  Upazila: "Gulshan",
  "Street address": "House 1",
  "Main goods you import": "LED lights",
};

function fillBuyer(skip: string[] = []) {
  for (const [label, value] of Object.entries(buyerFill)) {
    if (skip.includes(label)) continue;
    fireEvent.change(screen.getByLabelText(new RegExp(`^${label.replace(/[()/]/g, "\\$&")}`)), { target: { value } });
  }
  fireEvent.change(screen.getByLabelText(/Business type/), { target: { value: "TRADER" } });
  fireEvent.change(screen.getByLabelText(/Monthly import volume/), { target: { value: "500K_2M_BDT" } });
}

describe("BusinessStep (buyer)", () => {
  it("shows inline errors for a bad licence expiry and TIN", async () => {
    renderI18n(<BusinessStep {...props()} />);
    fillBuyer();
    fireEvent.change(screen.getByLabelText(/Licence expiry date/), { target: { value: "2020-01-01" } });
    fireEvent.change(screen.getByLabelText(/^TIN/), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(await screen.findByText("The licence must not be expired.")).toBeTruthy();
    expect(screen.getByText("TIN must be 9 to 13 digits.")).toBeTruthy();
    expect(screen.getByLabelText(/^TIN/).getAttribute("aria-invalid")).toBe("true");
    expect(api.saveBusiness).not.toHaveBeenCalled();
  });

  it("sends a nested body and maps server field errors inline", async () => {
    api.saveBusiness.mockRejectedValueOnce(
      Object.assign(new ApiError(422, "x", null, "VALIDATION_FAILED"), { fields: [{ field: "address.district", code: "required" }, { field: "tin", code: "INVALID_TIN" }] }),
    );
    const p = props();
    renderI18n(<BusinessStep {...p} />);
    fillBuyer();
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(api.saveBusiness).toHaveBeenCalled());
    const body = api.saveBusiness.mock.calls[0][0];
    expect(body.address).toMatchObject({ division: "Dhaka", district: "Dhaka" });
    expect(body.tin).toBe("123456789012");
    expect(await screen.findByText("TIN must be 9 to 13 digits.")).toBeTruthy();
    expect(screen.getAllByText("This field is required.").length).toBeGreaterThan(0);
    expect(p.onNext).not.toHaveBeenCalled();
  });

  it("lets saved masked values stay blank", async () => {
    api.saveBusiness.mockResolvedValue(baseState);
    const state = { ...baseState, business: { legal_name: "Dhaka Traders Ltd", trade_license_no_masked: "****2024", irc_no_masked: "****3456", tin_masked: "****9012", license_authority: "DNCC", license_expiry: "2099-01-01", address: { division: "Dhaka", district: "Dhaka", upazila: "Gulshan", street: "H1" }, business_type: "TRADER", main_import_goods: "LED", monthly_import_volume: "500K_2M_BDT" } };
    const p = { state, onState: vi.fn(), onNext: vi.fn() };
    renderI18n(<BusinessStep {...p} />);
    expect(screen.getAllByText(/Saved: \*\*\*\*/).length).toBe(3);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(p.onNext).toHaveBeenCalled();
    expect(api.saveBusiness).not.toHaveBeenCalled();
  });
});

describe("BusinessStep (supplier)", () => {
  it("rejects a USCC with a bad check character and accepts a good one", async () => {
    api.saveBusiness.mockResolvedValue(baseState);
    const p = props({ role: "SUPPLIER" });
    renderI18n(<BusinessStep {...p} />);
    const set = (label: RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
    set(/Company name \(English\)/, "Shenzhen Bright Co");
    set(/Company name \(Chinese\)/, "深圳明亮有限公司");
    set(/Unified Social Credit Code/, "91350100M000100Y44");
    set(/^Province/, "广东");
    set(/^City/, "深圳");
    set(/^District/, "南山");
    set(/Business scope/, "LED lighting");
    set(/Years of export experience/, "6");
    set(/Bank name/, "Bank of China");
    set(/Account holder name/, "Shenzhen Bright Co");
    set(/Account number/, "6217000012345678");
    set(/Account currency/, "USD");
    set(/SWIFT/, "BKCHCNBJ");
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(await screen.findByText(/This USCC is not valid/)).toBeTruthy();
    expect(screen.getByLabelText(/Company name \(Chinese\)/).getAttribute("lang")).toBe("zh");
    set(/Unified Social Credit Code/, "91350100m000100y43");
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(api.saveBusiness).toHaveBeenCalled());
    expect(api.saveBusiness.mock.calls[0][0]).toMatchObject({ uscc: "91350100M000100Y43", bank: { currency: "USD", swift: "BKCHCNBJ" }, export_experience_years: 6 });
  });
});

describe("DocumentsStep", () => {
  const file = (name: string, type: string, size = 1000) => {
    const f = new File(["x"], name, { type });
    Object.defineProperty(f, "size", { value: size });
    return f;
  };

  it("rejects oversize and wrong-type files without calling the API", async () => {
    renderI18n(<DocumentsStep {...props()} />);
    const input = screen.getByLabelText(/Trade licence \*/) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file("big.pdf", "application/pdf", 5 * 1024 * 1024)] } });
    expect((await screen.findByRole("alert")).textContent).toMatch(/larger than 4 MB/);
    fireEvent.change(input, { target: { files: [file("run.exe", "application/x-msdownload")] } });
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/Only PDF, PNG or JPG/));
    expect(api.uploadDocument).not.toHaveBeenCalled();
  });

  it("uploads, lists the file and unlocks Next once required documents exist", async () => {
    const doc = (type: string, id: string) => ({ id, type, original_name: `${type}.pdf`, mime: "application/pdf", size: 2048, status: "UPLOADED", created_at: "2026-10-20" });
    api.uploadDocument.mockResolvedValue(doc("TRADE_LICENSE", "d1"));
    const p = props();
    renderI18n(<DocumentsStep {...p} />);
    expect(screen.getByRole("button", { name: "Next" })).toHaveProperty("disabled", true);
    fireEvent.change(screen.getByLabelText(/Trade licence \*/), { target: { files: [file("a.pdf", "application/pdf")] } });
    await waitFor(() => expect(api.uploadDocument).toHaveBeenCalledWith("TRADE_LICENSE", expect.any(File)));
    expect(p.onState).toHaveBeenCalled();
  });

  it("enables Next with all required documents and removes a document", async () => {
    const doc = (type: string, id: string) => ({ id, type, original_name: `${type}.pdf`, mime: "application/pdf", size: 2048, status: "UPLOADED" as const, created_at: "x" });
    api.deleteDocument.mockResolvedValue(undefined);
    const p = props({ documents: [doc("TRADE_LICENSE", "d1"), doc("IRC", "d2")] as never });
    renderI18n(<DocumentsStep {...p} />);
    expect(screen.getByRole("button", { name: "Next" })).toHaveProperty("disabled", false);
    fireEvent.click(screen.getByRole("button", { name: /Remove: TRADE_LICENSE.pdf/ }));
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith("d1"));
  });
});

describe("SecurityStep", () => {
  it("needs all three consents before saving", async () => {
    api.saveConsent.mockResolvedValue(baseState);
    const p = props();
    renderI18n(<SecurityStep {...p} onTotpDone={noop} />);
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(screen.getByRole("alert").textContent).toMatch(/Tick all three/);
    for (const box of screen.getAllByRole("checkbox")) fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(api.saveConsent).toHaveBeenCalledWith({ terms_version: "2026-10", accept_terms: true, accept_privacy: true, consent_verification: true }));
  });

  it("requires the authenticator before administrators can save consent", () => {
    renderI18n(<SecurityStep {...props({ role: "ADMIN" })} onTotpDone={noop} />);
    expect(screen.getAllByText(/must turn on two-factor/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Start setup" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save and continue" })).toHaveProperty("disabled", true);
  });
});

describe("ReviewStep", () => {
  it("shows masked values and submits", async () => {
    api.submitProfile.mockResolvedValue({ ...baseState, account_status: "PENDING_VERIFICATION" });
    const state = { ...baseState, business: { legal_name: "Dhaka Traders Ltd", tin_masked: "****9012" }, consent: { terms_version: "2026-10", accepted_at: "x" } };
    const p = { state, onState: vi.fn(), onNext: vi.fn() };
    renderI18n(<ReviewStep {...p} onEdit={vi.fn()} />);
    expect(screen.getByText("****9012")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Submit for verification" }));
    await waitFor(() => expect(api.submitProfile).toHaveBeenCalled());
    expect(p.onNext).toHaveBeenCalled();
  });
});
