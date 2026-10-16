import type { Forecast, ScenarioRequest } from "@/lib/api/cashflow";
import { INPUT_DECIMAL } from "@/lib/format";

export type WhatIfState = {
  moveRef: string;
  moveOn: string;
  loanOn: boolean;
  loanAmount: string;
  loanDate: string;
  repayDate: string;
  repayAmount: string;
  removed: string[];
};

export type WhatIfField =
  "moveOn" | "loanAmount" | "loanDate" | "repayDate" | "repayAmount";
export type WhatIfError = "invalidDecimal" | "invalidDate" | "required";
export type WhatIfErrors = Partial<Record<WhatIfField, WhatIfError>>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function isIsoDate(v: string): boolean {
  if (!ISO_DATE.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().startsWith(v);
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Loan defaults: the server's cover amount, the day before the first shortfall. */
export function initialWhatIf(forecast: Forecast): WhatIfState {
  const shortfall = forecast.first_shortfall;
  return {
    moveRef: "",
    moveOn: "",
    loanOn: false,
    loanAmount: forecast.cover_amount,
    loanDate: shortfall ? addDays(shortfall.on, -1) : forecast.start,
    repayDate: "",
    repayAmount: "",
    removed: [],
  };
}

function checkDecimal(v: string): WhatIfError | undefined {
  if (v.trim() === "") return "required";
  return INPUT_DECIMAL.test(v) && /[1-9]/.test(v)
    ? undefined
    : "invalidDecimal";
}

function checkDate(v: string): WhatIfError | undefined {
  if (v === "") return "required";
  return isIsoDate(v) ? undefined : "invalidDate";
}

export type BuiltScenario = {
  request: ScenarioRequest | null;
  errors: WhatIfErrors;
  hasChanges: boolean;
};

export function buildScenarioRequest(
  state: WhatIfState,
  partyId?: string,
): BuiltScenario {
  const errors: WhatIfErrors = {};
  const request: ScenarioRequest = {
    days: 90,
    moves: [],
    removes: [...state.removed],
    loans: [],
  };
  if (partyId) request.party_id = partyId;

  if (state.moveRef && !state.removed.includes(state.moveRef)) {
    if (state.moveOn === "") {
      /* waiting for the new date: not a change yet */
    } else {
      const e = checkDate(state.moveOn);
      if (e) errors.moveOn = e;
      else request.moves = [{ ref: state.moveRef, on: state.moveOn }];
    }
  }

  if (state.loanOn) {
    const ea = checkDecimal(state.loanAmount);
    if (ea) errors.loanAmount = ea;
    const ed = checkDate(state.loanDate);
    if (ed) errors.loanDate = ed;
    const hasRepayDate = state.repayDate !== "";
    const hasRepayAmount = state.repayAmount !== "";
    if (hasRepayDate && !isIsoDate(state.repayDate)) {
      errors.repayDate = "invalidDate";
    }
    if (hasRepayAmount) {
      const er = checkDecimal(state.repayAmount);
      if (er) errors.repayAmount = er;
      if (!hasRepayDate) errors.repayDate = "required";
    }
    if (!ea && !ed && !errors.repayDate && !errors.repayAmount) {
      request.loans = [
        {
          amount: state.loanAmount,
          on: state.loanDate,
          ...(hasRepayDate ? { repay_on: state.repayDate } : {}),
          ...(hasRepayAmount ? { repay_amount: state.repayAmount } : {}),
        },
      ];
    }
  }

  const hasChanges =
    (request.moves?.length ?? 0) > 0 ||
    (request.removes?.length ?? 0) > 0 ||
    (request.loans?.length ?? 0) > 0;
  const invalid = Object.keys(errors).length > 0;
  return {
    request: hasChanges && !invalid ? request : null,
    errors,
    hasChanges,
  };
}
