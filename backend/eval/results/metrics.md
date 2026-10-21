# Setu evaluation (test split)

Generated 2026-10-20T14:43:49+00:00 · seed data `data/generated` · no LLM extraction used · synthetic data, a ceiling not real-world accuracy.

## Fraud detection (11 checks)

WARN or FAIL counts as flagged: precision 1.0, recall 1.0, F1 1.0.
FAIL only: precision 1.0, recall 0.9508, F1 0.9748.
Clean packs flagged: 0/50. Tampered packs with at least one unpassed document: 50/50.

| fraud type | packs | detected | recall |
|---|---|---|---|
| WRONG_PORT | 6 | 6 | 1.0 |
| VALUE_MISMATCH | 7 | 7 | 1.0 |
| NAME_MISMATCH | 5 | 5 | 1.0 |
| HS_CODE_MISMATCH | 6 | 6 | 1.0 |
| PRICE_OUTLIER | 6 | 6 | 1.0 |
| QUANTITY_MISMATCH | 5 | 5 | 1.0 |
| VESSEL_DATE_MISMATCH | 5 | 5 | 1.0 |
| ALTERED_BENEFICIARY | 6 | 6 | 1.0 |
| DUPLICATE_INVOICE | 5 | 5 | 1.0 |
| HIDDEN_INSTRUCTION | 5 | 5 | 1.0 |

| check | TP | FP | FN | precision | recall |
|---|---|---|---|---|---|
| QUANTITY_MATCH | 5 | 0 | 0 | 1.0 | 1.0 |
| VALUE_MATCH | 7 | 0 | 0 | 1.0 | 1.0 |
| VESSEL_DATE_MATCH | 5 | 0 | 0 | 1.0 | 1.0 |
| NAME_MATCH | 5 | 0 | 0 | 1.0 | 1.0 |
| DUPLICATE_INVOICE | 5 | 0 | 0 | 1.0 | 1.0 |
| PRICE_IN_BAND | 6 | 0 | 0 | 1.0 | 1.0 |
| BENEFICIARY_MATCH | 6 | 0 | 0 | 1.0 | 1.0 |
| HIDDEN_TEXT_SCAN | 5 | 0 | 0 | 1.0 | 1.0 |
| INSTRUCTION_SCAN | 5 | 0 | 0 | 1.0 | 1.0 |
| PORT_MATCH | 6 | 0 | 0 | 1.0 | 1.0 |
| HS_CODE_MATCH | 6 | 0 | 0 | 1.0 | 1.0 |

## Duplicate-document catch rate

| variant | n | caught | rate |
|---|---|---|---|
| near | 3 | 3 | 1.0 |
| any | 5 | 5 | 1.0 |
| exact | 2 | 2 | 1.0 |

## Prompt injection (attack success rate)

| defences | attack success | money moved |
|---|---|---|
| off | 100% | 0 |
| on | 0% | 0 |
| on_without_detector | 0% | 0 |

Detection recall 100%; false positives 0/300.

## PII leakage to the model

```json
{
  "split": "test",
  "packs": 100,
  "on": {
    "documents": 600,
    "ground_truth_identifiers": 600,
    "ground_truth_leaked": 0,
    "detected_leaked": 0,
    "masked_by_type": {
      "ACCT": 400,
      "AMT": 900,
      "NAME": 504,
      "SWIFT": 200
    },
    "fields_checked": 1200,
    "fields_ok": 1200,
    "field_accuracy": 1.0
  },
  "off": {
    "documents": 600,
    "ground_truth_identifiers": 600,
    "ground_truth_leaked": 600,
    "detected_leaked": 2491,
    "masked_by_type": {},
    "fields_checked": 1200,
    "fields_ok": 1200,
    "field_accuracy": 1.0
  }
}
```

## Auto vs escalated (USD 3,000 release per pack)

| group | n | auto (T0/1) | escalated (T2/3) | blocked |
|---|---|---|---|---|
| all | 100 | 50 | 27 | 23 |
| clean | 50 | 50 | 0 | 0 |
| tampered | 50 | 0 | 27 | 23 |

False-escalation rate on clean packs: 0.0. Tampered packs auto-released: 0.
