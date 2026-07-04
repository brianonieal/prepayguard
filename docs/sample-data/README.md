# Sample test data

Synthetic, legit-looking payments for exercising the live pipeline end to end.
Everything here is fabricated (same posture as the reference list: invented names,
TINs in the never-issued 90000000x range).

## Files

- `sample_payments.csv` : ready to upload (24 rows).
- Regenerate a fresh batch (new payment IDs) any time:
  ```sh
  python scripts/gen_sample_payments.py 30 docs/sample-data/sample_payments.csv
  ```

## What it triggers

The rows are built against the actual Do Not Pay reference list
(`src/component_b_enrichment/reference_data.json`), so they produce a real mix:

| Row type | Example | Disposition |
|---|---|---|
| Clean vendor, unmatched TIN | `Meridian Office Supplies LLC` | approve (auto) |
| Exact listed NAME, clean TIN | `Acme Shell LLC`, `Umbrella Holdings Group` | review (human queue) |
| Listed TIN on a HIGH-severity entry | a normal-looking vendor reusing TIN `900000002` | reject (auto-blocked) |
| Listed TIN on a MEDIUM entry | reusing `900000003` or `900000006` | review |
| Fuzzy near-miss of a listed name | `Glbex Offshore Inc` | review |

Only **review** items land in the Review Queue for a human. **Approve** and
**reject** are decided automatically by the risk engine and never need a click.

## How to run it

1. Sign in at https://d2rbxaf6pqgvb1.cloudfront.net
2. **Submit Payment** tab: drag `sample_payments.csv` onto the upload box (or click
   to browse). It parses and previews the rows, then click **Submit N payments**.
   The file uploads once and is ingested server-side (Component E); you get a
   summary: queued / duplicate / rejected.
3. **Review Queue** tab: the flagged (review) payments show as pending. Open one
   to see the screening evidence, the SHA-256 integrity check, and the
   approve / reject controls.

## Two things to know

- **Idempotency:** payments dedupe on `payment_id`. Re-uploading the *same* file
  is safe but enqueues nothing new (all duplicates). Regenerate for a fresh run.
- **Segregation of duties:** whoever submits a payment cannot approve it. If you
  upload as yourself and then open a flagged item, approve/reject returns a 403
  by design. To exercise the approve path, decide the item from a *different*
  account (see the second-reviewer login option).
