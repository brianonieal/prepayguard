# REAL_SOURCE_INGEST.md — wiring the real SAM.gov exclusions

Work Order 2 and course objective 10 (respond to messy real data / schema drift).
Moves the demo from "models the structure of the Do Not Pay sources" to "screens
against the actual federal debarment list" for one source, while keeping the three
genuinely restricted sources synthetic. Decision of record: DEC-22.

## 1. Source and verified access terms (checked 2026-07-06)

- **Source:** GSA System for Award Management (SAM.gov) **Exclusions API v4**,
  `https://api.sam.gov/entity-information/v4/exclusions`. This is the authoritative
  federal debarment/suspension list.
- **Access (live-checked 2026-07-06 at `https://open.gsa.gov/api/exclusions-api/`):**
  the exclusion records are public, but the API **requires a SAM.gov account and an
  API key** (personal or system account); there is no anonymous access. Rate limits
  run 10/day (no role) up to 10,000/day (federal system account). An unauthenticated
  request to the endpoint returns 404 (no data leaks without a key), which is why the
  ingestion cannot run until a `SAM_API_KEY` is provisioned.
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
   carrying a 1024-float embedding computed at publish). The ingestion caps to a
   documented `--limit` (default 300 most-recent active) so embedding cost and the
   reference-document size stay bounded for the demo. This is a deliberate, labeled
   scope limit: the live list is NOT the exhaustive federal list. Production would
   use the async extract endpoint plus a real vector index (the DEC-19 OpenSearch
   swap), not in-store cosine.

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
export SAM_API_KEY=<your SAM.gov system-account key>   # never commit this
# dry run first: fetch + normalize + summarize, no publish, no embedding cost
python scripts/ingest_sam_exclusions.py --bucket treasury-dev-reference-<ACCOUNT_ID> --limit 300 --dry-run
# then publish (mints reference version 4, embeds the real entries):
python scripts/ingest_sam_exclusions.py --bucket treasury-dev-reference-<ACCOUNT_ID> --limit 300
```

The normalization, dedupe, severity mapping, and doc-build logic are pinned by
`tests/test_sam_ingest.py` (deterministic, no network, no Bedrock), so the pieces
that do not need the key are already proven green.

## 6. Status

Built and tested; the live pull + publish is **pending a SAM.gov API key**, the one
external dependency. Until the key runs the publish, the live store remains at
version 3 (all synthetic) and the demo screens synthetic data. This document and
DEC-22 record the design; nothing here fakes a live real-source screening.
