"use client";

import { useId } from "react";

type Option<V extends string> = { value: V; label: string; title?: string };

type Props<V extends string> = {
  legend: string;
  options: Option<V>[];
  value: V;
  onChange: (value: V) => void;
};

export function SegmentedControl<V extends string>({
  legend,
  options,
  value,
  onChange,
}: Props<V>) {
  const name = useId();
  return (
    <fieldset className="min-w-0">
      <legend className="sr-only">{legend}</legend>
      <div className="inline-flex rounded-xl border border-line bg-surface p-1">
        {options.map((o) => (
          <label
            key={o.value}
            title={o.title}
            className="relative cursor-pointer rounded-lg px-3 py-1.5 text-sm font-semibold text-muted has-checked:bg-brand-700 has-checked:text-white has-focus-visible:ring-2 has-focus-visible:ring-brand-500 has-focus-visible:ring-offset-2"
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={o.value === value}
              onChange={() => onChange(o.value)}
              className="absolute inset-0 opacity-0"
            />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
