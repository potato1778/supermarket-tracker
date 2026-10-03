# Requirements — Swedish Grocery Offer Tracker

Status: living document. Last updated 2026-10-04.
Owner: Reese (`potato1778`).

---

## 1. Purpose and scope

### 1.1 What this is

A personal tool that collects current supermarket offers in Sweden, normalizes
them so that prices can be compared across stores, and answers two questions:

1. **Which store currently has the cheapest X per unit?** (e.g. chicken per kg)
2. **Is this advertised discount actually a discount?**

Question 2 is the reason price history exists. Everything else is plumbing.

### 1.2 In scope

- Ingesting offers from Swedish supermarket sources
- Normalizing offers into one comparable shape
- Ranking offers within a category by unit price
- Keeping a price history so past prices can be checked
- Free-text search over product names, tolerant of missing Swedish diacritics
- Sending a daily digest of offers matching a watch list
- Running unattended on a schedule, locally

### 1.3 Out of scope (non-goals)

| Non-goal | Why |
|---|---|
| A public website serving offer data | Redistributing scraped content at scale is the one line we agreed not to cross. See NFR-1. |
| An archive of expired offers | Expired offers are deleted. Only the slim price observation log is kept (FR-4). |
| Mobile app | The delivery channel is a chat message (FR-9), not an app. |
| Multi-user support, accounts, auth | Single user. No personal data is stored. |
| Shopping-list / basket optimization | Considered, not committed. Would be a separate feature with its own requirements. |

---

## 2. Users and use cases

One user: the author, shopping in Gothenburg.

| ID | Use case | Trigger |
|---|---|---|
| UC-1 | "Chicken is expensive. What is the cheapest per kg right now?" | Weekly planning |
| UC-2 | "I need laundry detergent. Which store is cheapest per litre?" | When a household item runs out |
| UC-3 | "Was this 25% off actually cheaper than usual?" | Standing in the store |
| UC-4 | "Tell me when coffee goes below my threshold." | Passive |
| UC-5 | "I typed `mjolk` without the umlaut. Still find milk." | Search |

---

## 3. Functional requirements

Each requirement is testable. Acceptance criteria are the definition of done.

### FR-1 — Ingest offers from a source

Fetch all offers for a given search term, paging until the source is exhausted.

- **Source A**: `ereklamblad.se` (backend: Tjek). Undocumented internal endpoint.
- **Source B**: `lidl.se`. Structured data embedded in category pages. *(blocked on FR-8)*

**Acceptance criteria**
- Paging retrieves more than one page's worth of results, with no duplicate `public_id` across pages.
- A single malformed record is skipped without losing the rest of the page.
- A network failure on page N stops that term but does not abort the run.
- Requests are rate limited and time-bounded. See NFR-2.

### FR-2 — Normalize an offer into the canonical shape

Map a raw record to one canonical dict, regardless of which source produced it.

**Acceptance criteria**
- A record with no usable identifier is rejected rather than stored with a null key.
- Both raw payloads and already-cleaned products map to the same output keys, so no two code paths can store different values for the same field.
- Store name and price are resolved defensively: the source omits `business` on some records, and exposes four price fields with no documented precedence.

### FR-3 — Store current offers, delete expired ones

**Acceptance criteria**
- Re-ingesting the same offer updates it in place. It does not create a duplicate row.
- `first_seen` is set once, on insert, and never overwritten by a later run.
- Offers whose validity window has closed are deleted, together with their search index entry.
- An offer with no `valid_until` is kept. We cannot tell whether it expired, and dropping it would hide data.

### FR-4 — Record price history

Append one observation per product per day.

**Acceptance criteria**
- Running the ingest twice in one day produces one observation, not two.
- Price observations are never deleted by FR-3.
- Given a product, the history is retrievable in chronological order.

### FR-5 — Free-text search tolerant of missing diacritics

**Acceptance criteria**
- `mjolk` finds `Mjölk` and `Mjölkchoklad`.
- `purjolok` finds `Purjolök`.
- Case is irrelevant.
- Queries shorter than the index token length still return results rather than an error.
- Input containing characters that are meaningful to the index syntax does not raise.

### FR-6 — Cross-store ranking by unit price

Given a category, list current offers ordered by unit price, cheapest first.

**Acceptance criteria**
- Results are ordered by unit price ascending.
- Each row shows the price, the unit price, the store, and the pack size.
- The query never returns an offer whose unit price is unknown or zero.
- The query never mixes currencies.

### FR-7 — Refuse to compare incomparable units

**Acceptance criteria**
- A category declares which base units it compares. Offers in other base units are excluded, not converted.
- Kilogram and litre are never converted into each other. They are not interchangeable without a density.
- A category that would otherwise mix units is split into one category per unit (e.g. liquid detergent vs powder).
- **No unit price is ever computed from a unit we do not understand.** Producing a precise-looking wrong number is worse than producing nothing.

### FR-8 — Extract pack size from the product name

Needed to unlock two things that are currently blocked: offers priced per
`piece` (toilet paper, eggs) and the entire Lidl source.

**Acceptance criteria**
- Given `Toalettpapper 24 rullar`, extract 24 rolls; given `6-pack`, extract 6; given `2 x 500 ml`, extract 1000 ml.
- Extraction is evaluated against a labelled set, and the accuracy is reported. A number, not a claim.
- Records where extraction is uncertain are marked as such and excluded from rankings, rather than guessed.

### FR-9 — Daily digest notification

**Acceptance criteria**
- One message per run, not one message per matching offer.
- A given offer is announced at most once.
- An offer already announced is re-announced only when its price drops further.
- Notification failures do not corrupt state: a re-run after a failed send still sends exactly the pending items.
- Credentials are read from the environment and never committed.

### FR-10 — Manage categories

**Acceptance criteria**
- Adding a category requires editing data, not code.
- Each category carries labels in Swedish, English and Chinese.
- Each category can carry exclusion terms to suppress known noise.

### FR-11 — Run unattended

**Acceptance criteria**
- Ingest, purge and notify run in sequence on a schedule, without interaction.
- A run leaves a record of what it did, sufficient to tell a silent failure from a quiet week.

---

## 4. Non-functional requirements

| ID | Requirement | Rationale |
|---|---|---|
| **NFR-1** | The repository contains code only. No scraped data, no database file, no credentials. | Redistributing the content is the actual legal exposure. Publishing the code is not. EU database rights exist and are stricter than US law. |
| **NFR-2** | Outbound requests carry a timeout, a delay between pages, and a hard page cap. | Undocumented endpoints. Hammering them is both rude and a fast route to being blocked. Low frequency also supports the personal-use framing. |
| **NFR-3** | No fabricated data. If a value cannot be derived correctly, it is `NULL` and excluded from results. | A wrong number that looks right is worse than a missing one. |
| **NFR-4** | Ingest is idempotent. Running it twice changes nothing. | The job runs on a schedule; duplicates would corrupt both the ranking and the notification state. |
| **NFR-5** | Source drift is detected automatically. | Both sources are undocumented. Silent breakage is the main long-term risk. |
| **NFR-6** | Behaviour is covered by tests, and the tests run in CI. | Manual verification does not scale, and regressions in the price logic are invisible without them. |
| **NFR-7** | Runs on Windows with a plain Python install. Docker is optional. | It has to run on the machine that exists. |
| **NFR-8** | User-facing output states which unit a ranking is in, and what was excluded. | Otherwise a ranking looks complete when it is not. |

---

## 5. Data model

```
offer                 one row per currently valid offer
  public_id           source-assigned identifier (primary key)
  source              which source produced it
  name, name_folded   name_folded is what the search index uses
  store
  price               what you pay
  unit_price          price per base unit, as supplied by the source
  base_unit           kilogram | liter | piece
  unit_symbol         display symbol, e.g. g, kg, ml, l, pcs
  size_from, size_to  pack size; a range when the source gives a range
  currency
  department          source's coarse category
  valid_from, valid_until
  first_seen, last_seen

price_observation     append-only, kept forever
  public_id, observed_on, price, unit_price

offer_fts             FTS5, trigram tokenizer, over name_folded

category              code-level data (categories.py), not a table
  match / exclude / allowed_base_units / canonical_unit / labels
```

**Why `unit_price` is not recomputed.** The source already normalizes it onto
`base_unit`, including multi-pack offers (verified: a 6 × 450 g coffee pack at
699 kr yields 129.44 kr/kg). Recomputing it from `price` and `size` would
introduce a second, disagreeing implementation.

---

## 6. Constraints and assumptions

- **Assumption**: the `unit_price` field keeps its current meaning. If the source changes it to mean something else, every ranking is silently wrong. See NFR-5.
- **Assumption**: offers are store-specific, not chain-specific. Two branches of the same chain can carry different offers.
- **Constraint**: neither source is officially supported. Tjek's API is customer-only; Lidl has none.
- **Constraint**: kilogram and litre are not convertible here. No density data is available, and guessing one is not acceptable.
- **Constraint**: GitHub Actions is unsuitable for the scheduled job. It has no persistent disk, so the database would have to live in the repository, which NFR-1 forbids.

---

## 7. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Source format changes without notice | Ingest silently returns nothing | NFR-5 drift canary; assert on non-zero record counts |
| Legal exposure from redistributing data | Cease and desist, account ban | NFR-1; personal, low-frequency use; no public service |
| Wrong unit price enters a ranking | User buys on a false signal | FR-7; unit declared in output (NFR-8) |
| Notification spam | Channel muted, feature abandoned | FR-9 idempotency and digest |
| Scope creep (maps, websites, optimization) | Nothing ships | Section 1.3 exists to be pointed at |

---

## 8. Milestones

| Milestone | Contents | State |
|---|---|---|
| **M0 — Hygiene** | Remove committed data, fix the store bug, add dependencies | Done |
| **M1 — Comparable data** | Ingest with paging, normalize, store, price history, ranking, search | Done |
| **M2 — Trustworthy** | Test suite, CI, source drift canary | Next |
| **M3 — Complete** | Pack-size extraction; unblocks `piece` categories and Lidl | Planned |
| **M4 — Useful** | Digest notification with idempotency | Planned |
| **M5 — Presentation** | Rewire the web UI to the new data layer, README, Docker | Planned |

---

## 9. Traceability

| Requirement | State | Evidence |
|---|---|---|
| FR-1 source A | Done | 4 pages, 80 records, zero duplicates |
| FR-1 source B | Blocked on FR-8 | Lidl exposes no numeric unit price |
| FR-2 | Done | `normalize.py`; both raw and cleaned shapes map to the same keys |
| FR-3 | Done | Second ingest: 0 new, 0 updated, 82 unchanged; `first_seen` preserved |
| FR-4 | Done | 187 observations for 187 offers |
| FR-5 | Done | `mjolk` returns `Mjölk`; `mjölkchoklad` matched by `choklad` |
| FR-6 | Done | `cheapest kyckling` ranks 24.98 → 71.36 kr/kg across 23 stores |
| FR-7 | Done | Laundry detergent split into liquid and powder categories |
| FR-8 | Not started | — |
| FR-9 | Not started | — |
| FR-10 | Done | 15 rankable categories, 2 awaiting FR-8 |
| FR-11 | Partial | `fetch` and `purge` exist; no scheduler, no run log |
| NFR-1 | Done | Data untracked, `.gitignore` in place |
| NFR-2 | Done | 25 s timeout, 0.6 s between pages, 40-page cap |
| NFR-3 | Done | Zero unit prices treated as unknown, not free |
| NFR-4 | Done | Verified by re-running ingest |
| NFR-5 | Not started | — |
| NFR-6 | Not started | — |
| NFR-7 | Done | Runs on Windows, no Docker required |
| NFR-8 | Partial | CLI declares the unit; exclusions are not yet reported |
