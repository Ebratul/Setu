import type { CreateDealRequest } from "@/lib/api/deals";
import { isDecimal, isZero, mulDecimal } from "@/lib/decimal";

export type CostKind = "FREIGHT" | "INSURANCE" | "DUTY" | "BANK_CHARGES";
export const COST_KINDS: CostKind[] = ["FREIGHT", "INSURANCE", "DUTY", "BANK_CHARGES"];

export type Draft = {
  supplierId: string;
  title: string;
  hsCode: string;
  quantity: string;
  unit: string;
  unitPrice: string;
  currency: "USD" | "CNY";
  incoterm: string;
  portOfLoading: string;
  portOfDischarge: string;
  expectedSale: string;
  costs: Record<CostKind, string>;
};

export const EMPTY_DRAFT: Draft = {
  supplierId: "",
  title: "",
  hsCode: "",
  quantity: "",
  unit: "pcs",
  unitPrice: "",
  currency: "USD",
  incoterm: "FOB",
  portOfLoading: "",
  portOfDischarge: "Chattogram",
  expectedSale: "",
  costs: { FREIGHT: "", INSURANCE: "", DUTY: "", BANK_CHARGES: "" },
};

export const INCOTERMS = ["EXW", "FCA", "FOB", "CFR", "CIF", "CIP", "DAP", "DDP"];

/** Exact preview of quantity x unit price (string math). Null until both parse. */
export function goodsTotal(d: Draft): string | null {
  return mulDecimal(d.quantity, d.unitPrice);
}

export type GoodsErrors = Partial<
  Record<"title" | "hsCode" | "quantity" | "unit" | "unitPrice" | "expectedSale", string>
>;

/** Error keys (i18n) per field for the goods step. */
export function goodsErrors(d: Draft): GoodsErrors {
  const e: GoodsErrors = {};
  if (!d.title.trim()) e.title = "dn.err.required";
  if (!/^[0-9.]{4,12}$/.test(d.hsCode.trim())) e.hsCode = "dn.err.hs";
  if (!isDecimal(d.quantity) || isZero(d.quantity)) e.quantity = "dn.err.positive";
  if (!d.unit.trim() || d.unit.trim().length > 16) e.unit = "dn.err.unit";
  if (!isDecimal(d.unitPrice) || isZero(d.unitPrice)) e.unitPrice = "dn.err.positive";
  if (d.expectedSale.trim() !== "" && !isDecimal(d.expectedSale)) {
    e.expectedSale = "dn.err.decimal";
  }
  return e;
}

export type ShipErrors = Partial<
  Record<"portOfLoading" | "portOfDischarge" | CostKind, string>
>;

export function shipErrors(d: Draft): ShipErrors {
  const e: ShipErrors = {};
  if (!d.portOfLoading.trim()) e.portOfLoading = "dn.err.required";
  if (!d.portOfDischarge.trim()) e.portOfDischarge = "dn.err.required";
  for (const k of COST_KINDS) {
    if (d.costs[k].trim() !== "" && !isDecimal(d.costs[k])) e[k] = "dn.err.decimal";
  }
  return e;
}

export function buildRequest(d: Draft): CreateDealRequest {
  return {
    supplier_id: d.supplierId,
    title: d.title.trim(),
    hs_code: d.hsCode.trim(),
    quantity: d.quantity.trim(),
    unit: d.unit.trim(),
    unit_price: d.unitPrice.trim(),
    currency: d.currency,
    incoterm: d.incoterm,
    port_of_loading: d.portOfLoading.trim(),
    port_of_discharge: d.portOfDischarge.trim(),
    expected_sale_value: d.expectedSale.trim() || null,
    costs: COST_KINDS.filter((k) => d.costs[k].trim() !== "" && !isZero(d.costs[k])).map(
      (k) => ({ kind: k, amount: d.costs[k].trim(), currency: d.currency }),
    ),
  };
}
