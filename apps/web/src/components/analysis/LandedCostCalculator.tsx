"use client";

import { useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { FormField, inputClass } from "@/components/ui/FormField";
import { QueryError } from "@/components/ui/QueryError";
import { useT } from "@/i18n";
import {
  postLandedCost,
  type Currency,
  type LandedCostRequest,
} from "@/lib/api/analysis";
import { INPUT_DECIMAL } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/useApi";

import { AnalysisResults } from "./AnalysisResults";
import { AnalysisSkeleton } from "./OrderAnalysisView";
import { useTargetMargin } from "./useTargetMargin";

type Kind = "FREIGHT" | "INSURANCE" | "DUTY" | "BANK_CHARGES" | "OTHER";
type Line = { id: number; kind: Kind; amount: string; label: string };

const KINDS: Kind[] = ["FREIGHT", "INSURANCE", "DUTY", "BANK_CHARGES", "OTHER"];
const ZERO = /^0+(\.0+)?$/;

const DEFAULT_LINES: Line[] = [
  { id: 1, kind: "FREIGHT", amount: "600", label: "" },
  { id: 2, kind: "INSURANCE", amount: "50", label: "" },
  { id: 3, kind: "DUTY", amount: "800", label: "" },
  { id: 4, kind: "BANK_CHARGES", amount: "150", label: "" },
];

export function LandedCostCalculator() {
  const t = useT();
  const nextId = useRef(DEFAULT_LINES.length + 1);
  const [inputCurrency, setInputCurrency] = useState<Currency>("USD");
  const [display, setDisplay] = useState<Currency>("USD");
  const [goods, setGoods] = useState("9600");
  const [qty, setQty] = useState("8000");
  const [unit, setUnit] = useState("pcs");
  const [price, setPrice] = useState("1.70");
  const [lines, setLines] = useState<Line[]>(DEFAULT_LINES);
  const target = useTargetMargin();

  const errors = {
    goods: INPUT_DECIMAL.test(goods.trim()) ? null : t("calc.err.decimal"),
    qty: !INPUT_DECIMAL.test(qty.trim())
      ? t("calc.err.decimal")
      : ZERO.test(qty.trim())
        ? t("calc.err.qtyPositive")
        : null,
    unit: unit.trim() && unit.trim().length <= 8 ? null : t("calc.err.unit"),
    price:
      price.trim() === "" || INPUT_DECIMAL.test(price.trim())
        ? null
        : t("calc.err.decimal"),
  };
  const lineErrors = lines.map((l) =>
    l.amount.trim() === "" || INPUT_DECIMAL.test(l.amount.trim())
      ? null
      : t("calc.err.decimal"),
  );
  const valid =
    !errors.goods &&
    !errors.qty &&
    !errors.unit &&
    !errors.price &&
    !target.error &&
    lineErrors.every((e) => !e);

  const bodyJson = useMemo(() => {
    if (!valid) return null;
    const body: LandedCostRequest = {
      currency: inputCurrency,
      goods_value: goods.trim(),
      quantity: qty.trim(),
      unit: unit.trim(),
      cost_lines: lines
        .filter((l) => l.amount.trim() !== "")
        .map((l) => ({
          kind: l.kind,
          amount: l.amount.trim(),
          ...(l.label.trim() ? { label: l.label.trim() } : {}),
        })),
      selling_price_per_unit: price.trim() || null,
      target_margin_pct: target.request ?? null,
    };
    return JSON.stringify(body);
  }, [valid, inputCurrency, goods, qty, unit, lines, price, target.request]);

  const debouncedJson = useDebounced(bodyJson);
  const { data, error, loading, reload } = useApi(
    (s) =>
      postLandedCost(JSON.parse(debouncedJson ?? "{}") as LandedCostRequest, s),
    debouncedJson ?? "",
    debouncedJson !== null,
  );

  function updateLine(id: number, patch: Partial<Line>) {
    setLines((ls) => ls.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  }

  const decimalInput = (
    aria: Record<string, unknown>,
    value: string,
    set: (v: string) => void,
  ) => (
    <input
      {...aria}
      type="text"
      inputMode="decimal"
      value={value}
      onChange={(e) => set(e.target.value)}
      className={inputClass}
    />
  );

  return (
    <div className="space-y-6">
      <Card as="section" labelledBy="calc-h">
        <h2 id="calc-h" className="text-lg font-semibold text-ink">
          {t("calc.title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("calc.intro")}</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <FormField id="calc-currency" label={t("calc.currency")}>
            {(aria) => (
              <select
                {...aria}
                value={inputCurrency}
                onChange={(e) => setInputCurrency(e.target.value as Currency)}
                className={inputClass}
              >
                <option value="USD">USD</option>
                <option value="BDT">BDT</option>
                <option value="CNY">CNY</option>
              </select>
            )}
          </FormField>
          <FormField
            id="calc-goods"
            label={t("calc.goodsValue")}
            error={errors.goods}
          >
            {(aria) => decimalInput(aria, goods, setGoods)}
          </FormField>
          <FormField
            id="calc-qty"
            label={t("calc.quantity")}
            error={errors.qty}
          >
            {(aria) => decimalInput(aria, qty, setQty)}
          </FormField>
          <FormField id="calc-unit" label={t("calc.unit")} error={errors.unit}>
            {(aria) => (
              <input
                {...aria}
                type="text"
                maxLength={8}
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                className={inputClass}
              />
            )}
          </FormField>
          <FormField
            id="calc-price"
            label={t("calc.sellingPrice")}
            error={errors.price}
            hint={t("calc.optional")}
          >
            {(aria) => decimalInput(aria, price, setPrice)}
          </FormField>
        </div>

        <fieldset className="mt-6">
          <legend className="text-sm font-semibold text-ink">
            {t("calc.costLines")}
          </legend>
          <ul className="mt-3 space-y-3">
            {lines.map((l, i) => (
              <li
                key={l.id}
                className="grid grid-cols-2 items-start gap-3 sm:grid-cols-[10rem_8rem_1fr_auto]"
              >
                <FormField id={`line-kind-${l.id}`} label={t("calc.lineKind")}>
                  {(aria) => (
                    <select
                      {...aria}
                      value={l.kind}
                      onChange={(e) =>
                        updateLine(l.id, { kind: e.target.value as Kind })
                      }
                      className={inputClass}
                    >
                      {KINDS.map((k) => (
                        <option key={k} value={k}>
                          {t(`kind.${k}`)}
                        </option>
                      ))}
                    </select>
                  )}
                </FormField>
                <FormField
                  id={`line-amount-${l.id}`}
                  label={t("calc.lineAmount")}
                  error={lineErrors[i]}
                >
                  {(aria) =>
                    decimalInput(aria, l.amount, (v) =>
                      updateLine(l.id, { amount: v }),
                    )
                  }
                </FormField>
                <FormField
                  id={`line-label-${l.id}`}
                  label={t("calc.lineLabel")}
                >
                  {(aria) => (
                    <input
                      {...aria}
                      type="text"
                      maxLength={60}
                      value={l.label}
                      onChange={(e) =>
                        updateLine(l.id, { label: e.target.value })
                      }
                      className={inputClass}
                    />
                  )}
                </FormField>
                <Button
                  variant="secondary"
                  className="mt-6"
                  aria-label={t("calc.removeLine", {
                    kind: t(`kind.${l.kind}`),
                  })}
                  onClick={() =>
                    setLines((ls) => ls.filter((x) => x.id !== l.id))
                  }
                >
                  {t("calc.remove")}
                </Button>
              </li>
            ))}
          </ul>
          <Button
            variant="ghost"
            className="mt-3"
            disabled={lines.length >= 20}
            onClick={() =>
              setLines((ls) => [
                ...ls,
                { id: nextId.current++, kind: "OTHER", amount: "", label: "" },
              ])
            }
          >
            + {t("calc.addLine")}
          </Button>
        </fieldset>
      </Card>

      {!valid ? (
        <p role="status" className="text-sm font-medium text-danger">
          {t("calc.fixErrors")}
        </p>
      ) : error ? (
        <QueryError error={error} onRetry={reload} />
      ) : data ? (
        <AnalysisResults
          data={data}
          currency={display}
          onCurrency={setDisplay}
          busy={loading}
          target={{
            value: target.value,
            error: target.error,
            updating: target.updating || loading,
            onChange: target.setValue,
          }}
        />
      ) : (
        <AnalysisSkeleton />
      )}
    </div>
  );
}
