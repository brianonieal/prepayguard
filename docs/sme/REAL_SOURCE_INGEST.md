# REAL_SOURCE_INGEST.md: wiring the real SAM.gov exclusions

Work Order 2 and course objective 10 (respond to messy real data / schema drift).
Moves the demo from "models the structure of the Do Not Pay sources" to "screens
against the actual federal debarment list" for one source, while keeping the three
genuinely restricted sources synthetic. Decision of record: DEC-22.

## 1. Source and verified access terms (checked 2026-07-06)

- **Source:** GSA System for Award Management (SAM.gov) **Exclusions API v4**,
  `https://api.sam.gov/entity-information/v4/exclusions`. This is the authoritative
  federal debarment/suspension list.
- **Access (live-checked 2026-07-06):** the exclusion records are public, but the API
  **requires a SAM.gov account and an API key**; there is no anonymous access. Verified
  behaviors against the live API on 2026-07-06:
  - Unauthenticated request -> HTTP 404 (no data leaks without a key).
  - With a key, sending `Accept: application/json` -> HTTP 406; sending a neutral
    User-Agent and no explicit Accept -> HTTP 200. The script sets the working headers.
  - The **free personal-key tier is 10 requests/day**. Once spent, the API returns
    **HTTP 429** with a `retry-after` reset at 00:00 GMT (observed live). A role-bearing
    personal key or a system account is 1,000-10,000/day.
  - The v4 regular endpoint returns records in a **nested** shape
    (`excludedEntity[].exclusionDetails` + `.exclusionIdentification` +
    `.exclusionActions.listOfActions[].recordStatus`); the normalizer targets exactly
    this shape (confirmed against a real pull before the daily quota was exhausted).
  - Consequence for design: the default paginated pull is **capped to fit the free
    tier** (see section 3.7). A `--extract` mode (one async call) is available for a
    higher-tier key or the full list.
- **Keyless fallback considered and documented, not used:** OpenSanctions
  `us_sam_exclusions` republishes the same GSA data daily as keyless JSON/CSV
  (verified available 2026-07-06, last processed that day). It is licensed
  **CC-BY-NC** (attribution, non-commercial), which is acceptable for a capstone or
  portfolio but is a re-publisher, not the primary federal source. DEC-22 chose the
  authoritative GSA API; OpenSanctions remains the drop-in fallback if a key is not
  available (swap the fetch function; the normalize/publish path is unchanged).

## 2. What the API returns vs the reference schema (the mapping)

SAM v4 exclusion fields: `entityName` (or individual name parts), `ueiSAM`,
`cageCode`, `classificationType` (Firm / Individual / Vessel / Special Entity
Designation), `exclusionType`, `exclusionProgram`, `excludingAgencyName`, dates
(`activateDate`, `terminationDate`), `recordStatus`, and an address block.

The reference-store schema is `{name, tin, source, severity}` plus a per-entry
`embedding` computed at publish (DEC-18/DEC-19). Mapping:

| Reference field | From SAM | Handling |
|---|---|---|
| `name` | `entityName`, else assembled `firstName/middleName/lastName` | firms and individuals both supported |
| `tin` | (none exists) | **empty** - SAM has no TIN; matching is name-only |
| `uei` | `ueiSAM` | kept for **audit provenance**, not used for matching |
| `source` | constant | `"sam_exclusions"` |
| `severity` | `exclusionType` | Prohibition/Restriction and Proceedings-Completed -> high; Proceedings-Pending and Voluntary -> medium; unknown -> high (fail-safe) |
| `classification`, `exclusion_type`, `excluding_agency` | passthrough | retained for reviewer context |

## 3. Messy-real-data handling (objective 10), decision by decision

1. **No TIN.** SAM keys on name / UEI, not a TIN. So the real entries match only on
   the name paths (exact, fuzzy, semantic); Component B's TIN path never fires for
   them. Documented, not silently broken. Consequence: a name variant of a listed
   individual is caught by fuzzy/semantic, never the strong TIN path, so real-source
   hits skew toward REVIEW rather than the TIN-driven auto-REJECT. That is the honest
   behavior of a name-only source.
2. **Classification variety.** Firm, Individual, Vessel, Special Entity are all
   ingested (DEC-22: full list). `_record_name` handles the firm `entityName` shape
   and the individual name-parts shape; the classification is carried through for the
   reviewer.
3. **Exclusion-type variety.** Mapped to `severity` by an explicit, documented table
   (above), with an unknown-type fail-safe to `high` so a new SAM exclusion type
   never silently downgrades to low signal.
4. **Active-only filtering.** Records with `recordStatus` inactive, or with a
   `terminationDate` and no active status, are dropped, so the screen reflects
   currently-excluded parties, not historical ones.
5. **Name-variant noise and duplicates.** Deduped on `(normalized name, UEI)` so the
   same party listed under two programs does not double-count.
6. **Schema drift tolerance.** The response unwrap (`_records_from_payload`) accepts
   the couple of envelope shapes SAM has used, and normalization reads several
   possible name keys, so a minor SAM field rename degrades to "drop that record",
   not a crash. The raw counts are logged so drift is visible.
7. **Size cap (the key scope decision).** The full active list is far larger than the
   in-store cosine design supports (DEC-19 is scoped to hundreds of entries, each
   carrying a 1024-float embedding computed at publish), and the free key allows only
   10 requests/day. The ingestion caps to a documented `--limit` (**default 90**, which
   is <= 9 paginated calls of 10, one call of margin under the free tier) so embedding
   cost, document size, AND the daily call budget all stay bounded. This is a
   deliberate, labeled scope limit: the live list is the most-recent active slice, NOT
   the exhaustive federal list. To ingest more, use `--extract` (one async call returns
   the full list, then it is capped locally) with a higher-tier key, or raise `--limit`
   on a role-bearing key. Production would use the extract endpoint plus a real vector
   index (the DEC-19 OpenSearch swap), not in-store cosine.

## 4. Publish path (reuses the lifecycle, does not bolt on a second store)

`build_reference_doc` keeps the three synthetic restricted sources from the current
live document verbatim (reusing their existing embeddings so they are not
re-embedded), drops the synthetic `sam_exclusions` entries, adds the real SAM
entries (each embedded via Titan at publish), bumps the version, and updates the
`sources` map so the SAM source is labeled real. `publish` claims the next
`reference/versions/{N}.json` with a conditional put (`If-None-Match: *`) and
repoints `current.json`, identical to `console_api._put_reference` and
`seed_reference_data.py`. Component B picks up the new version within
`REFERENCE_TTL_SECONDS`, and D writes the cited `reference_list_version` into the
audit record, so a real-source screening is audited end to end.

## 5. How to run the live pull + publish

```
# OPTION A - OpenSanctions (keyless, no rate limit, CC-BY-NC): works immediately.
python scripts/ingest_sam_exclusions.py --bucket treasury-dev-reference-<ACCOUNT_ID> --source opensanctions --limit 90 --dry-run
python scripts/ingest_sam_exclusions.py --bucket treasury-dev-reference-<ACCOUNT_ID> --source opensanctions --limit 90

# OPTION B - authoritative GSA API (needs SAM_API_KEY; free tier 10/day, resets 00:00 GMT):
export SAM_API_KEY="$(tr -d '[:space:]' < .sam_api_key)"   # gitignored, never committed
python scripts/ingest_sam_exclusions.py --bucket treasury-dev-reference-<ACCOUNT_ID> --limit 90 --dry-run
python scripts/ingest_sam_exclusions.py --bucket treasury-dev-reference-<ACCOUNT_ID> --limit 90
# GSA full list / higher-tier key: one async extract call, capped locally
python scripts/ingest_sam_exclusions.py --bucket treasury-dev-reference-<ACCOUNT_ID> --extract --limit 300 --dry-run
```

Both sources normalize into the identical schema and publish through the same
versioned lifecycle; only the fetch differs. OpenSanctions is the practical
no-limit path (verified live 2026-07-06: 90 records = 28 entities + 62 individuals,
all active). GSA is the authoritative primary source when a key/quota is available.

The normalization, dedupe, severity mapping, and doc-build logic are pinned by
`tests/test_sam_ingest.py` (deterministic, no network, no Bedrock), so the pieces
that do not need the key are already proven green.

## 6. Status - LIVE

Published live on 2026-07-06 via `--source opensanctions` (the keyless, no-limit
path; the GSA free key's 10/day quota was exhausted during verification). The live
reference store is now **version 4: 96 entries = 90 real SAM exclusions (28 entities,
62 individuals) + 6 synthetic restricted-source entries** (SSA DMF, TOP, OIG LEIE,
kept synthetic and labeled). Verified end to end (`docs/evidence/live_real_source_ingest.txt`):
the real federal exclusion "YATAI SMART INDUSTRIAL NEW CITY" screens through the live
Component B as a `name_exact` match on `sam_exclusions`, citing `reference_version 4`;
a clean name gets no match. Tests green (`tests/test_sam_ingest.py`, 14 tests).

Attribution (CC-BY-NC): SAM exclusions data via OpenSanctions (`us_sam_exclusions`),
sourced from the U.S. GSA System for Award Management. The authoritative GSA API path
(`--source gsa`) remains available for a key with sufficient quota.

To roll back: repoint `reference/current.json` to the `reference/versions/3.json`
document (the versioned history is intact); the three synthetic sources are unaffected.
