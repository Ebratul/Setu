import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang } from "@/components/shell/testUtils";
import { ApiError } from "@/lib/api/client";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/auth/client", () => ({
  getAuthMode: () => Promise.resolve("neon"),
  endAuthSession: vi.fn(),
}));
vi.mock("@/lib/api/auth", () => ({ startSession: vi.fn(), logout: vi.fn() }));

const submitOnboarding = vi.fn();
const getOnboardingStatus = vi.fn();
vi.mock("@/lib/api/onboarding", () => ({
  submitOnboarding: (b: unknown) => submitOnboarding(b),
  getOnboardingStatus: () => getOnboardingStatus(),
}));

import { OnboardingForm } from "./OnboardingForm";

const type = (label: string | RegExp, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
const next = () => fireEvent.click(screen.getByRole("button", { name: "Next" }));

async function toCompany(country = "BD") {
  renderI18n(<OnboardingForm />);
  await screen.findByLabelText("I am a");
  type("I am a", "BUYER");
  type("Your name", "Rahim Uddin");
  next();
  await screen.findByLabelText("Company legal name");
  type("Country", country);
}

function fillCompany(tin = "123456789") {
  type("Company legal name", "Rahim Traders Ltd");
  type(/Trade licence number/, "TL-12345");
  type(/TIN/, tin);
  type("City", "Dhaka");
}

function fillBank() {
  type("Bank name", "Sample Bank");
  type("Account number", "1234567890");
}

async function toReview() {
  await toCompany();
  fillCompany();
  next();
  await screen.findByLabelText("Bank name");
  fillBank();
  next();
  await screen.findByRole("button", { name: "Submit for review" });
}

describe("OnboardingForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setLang("en");
    getOnboardingStatus.mockRejectedValue(new ApiError(404, "x", null, "NOT_ONBOARDED"));
  });

  it("says money is simulated and that a person reviews", async () => {
    renderI18n(<OnboardingForm />);
    expect(await screen.findByText(/Simulated/, { selector: "div *" })).toBeInTheDocument();
    expect(screen.getAllByText(/person reviews every company/).length).toBeGreaterThan(0);
  });

  it("blocks the first step until a type and name are given", async () => {
    renderI18n(<OnboardingForm />);
    await screen.findByLabelText("I am a");
    next();
    expect(screen.getAllByText("This field is required.").length).toBe(2);
    expect(screen.getByLabelText("Your name")).toHaveAttribute("aria-invalid", "true");
  });

  it("requires a 9 to 13 digit TIN for a Bangladesh buyer", async () => {
    await toCompany();
    fillCompany("ABC-123");
    next();
    expect(await screen.findByText(/TIN must be 9 to 13 digits/)).toBeInTheDocument();
    type(/TIN/, "123456789");
    next();
    expect(await screen.findByLabelText("Bank name")).toBeInTheDocument();
  });

  it("does not apply the Bangladesh TIN rule to a Chinese company", async () => {
    await toCompany("CN");
    fillCompany("91310000MA1");
    next();
    expect(await screen.findByLabelText("Bank name")).toBeInTheDocument();
  });

  it("prefills the holder name from the company and rejects SIM- numbers", async () => {
    await toCompany();
    fillCompany();
    next();
    await screen.findByLabelText("Bank name");
    expect(screen.getByLabelText("Account holder name")).toHaveValue("Rahim Traders Ltd");
    expect(screen.getByText(/Must match the company's legal name/)).toBeInTheDocument();
    type("Bank name", "Sample Bank");
    type("Account number", "SIM-123456789");
    next();
    expect(await screen.findByText(/SIM-\) account numbers/)).toBeInTheDocument();
  });

  it("submits the payload and goes to the status page", async () => {
    submitOnboarding.mockResolvedValue({});
    await toReview();
    fireEvent.click(screen.getByRole("button", { name: "Submit for review" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/onboarding/status"));
    expect(submitOnboarding).toHaveBeenCalledWith(
      expect.objectContaining({
        account_type: "BUYER",
        legal_name: "Rahim Traders Ltd",
        license_name: null,
        tax_id: "123456789",
        country: "BD",
        language: "en",
        bank_account: expect.objectContaining({ account_number: "1234567890", holder_name: "Rahim Traders Ltd", currency: "BDT" }),
      }),
    );
  });

  it.each([
    ["EMAIL_IN_USE", /already belongs to another Setu account/],
    ["COUNTRY_NOT_SUPPORTED", /does not support companies in that country/],
    ["LICENSE_EXISTS", /licence number is already registered/],
    ["ONBOARDING_EXISTS", /already submitted/],
  ])("maps the 409 code %s to a friendly message", async (code, text) => {
    submitOnboarding.mockRejectedValue(new ApiError(409, "x", null, code));
    await toReview();
    fireEvent.click(screen.getByRole("button", { name: "Submit for review" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("shows field-level 422 errors and returns to the step that holds the field", async () => {
    const detail = JSON.stringify([{ loc: ["body", "tax_id"], msg: "bad", type: "value_error" }]);
    submitOnboarding.mockRejectedValue(new ApiError(422, "x", detail));
    await toReview();
    fireEvent.click(screen.getByRole("button", { name: "Submit for review" }));
    const field = await screen.findByLabelText(/TIN/);
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/server did not accept this value/)).toBeInTheDocument();
  });

  it("moves an already-onboarded user to the status page", async () => {
    getOnboardingStatus.mockResolvedValue({ status: "PENDING" });
    renderI18n(<OnboardingForm />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/onboarding/status"));
  });
});
