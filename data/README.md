# Corpus Provenance

## Source

U.S. Occupational Safety and Health Administration, Title 29 CFR Part 1910
(Occupational Safety and Health Standards for General Industry), scraped from
osha.gov on 2026-07-31.

| Subpart | Scope | Index URL |
|---|---|---|
| Subpart D | Walking-Working Surfaces (1910.21-1910.30) | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910SubpartD |
| Subpart I | Personal Protective Equipment (1910.132-1910.140) | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910SubpartI |
| Subpart J | Lockout/Tagout — **1910.147 only** | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147 |

Subpart J is deliberately scoped to 1910.147 alone. The rest of Subpart J
(1910.141-1910.146) is out of scope.

The corpus contains 20 sections and 937 paragraphs total across all three subparts.

## Licensing

U.S. federal regulatory text. Works of the U.S. federal government are not
subject to copyright protection in the United States (17 U.S.C. § 105) and are
in the public domain. No license restrictions apply to redistribution of the
regulatory text in this directory.

## Why the corpus is committed to this repo

`data/raw/` (cached source HTML) and `data/corpus/` (parsed output) are committed
rather than gitignored. The corpus is small and public-domain, and committing it
means anyone cloning this repository gets a working system without network access
to osha.gov and without depending on OSHA's page structure remaining unchanged.
`scripts/ingest_osha.py` documents how the corpus was produced; it does not need
to be re-run to use the repository.

## Regenerating

    python -m scripts.ingest_osha

Delete `data/raw/` first to force a live re-fetch; otherwise cached HTML is reused.

## Scope note

This corpus is a subset of 29 CFR 1910 selected for a portfolio retrieval system.
It is not a complete or authoritative copy of OSHA's standards and must not be
relied on for compliance purposes. Consult osha.gov or eCFR for authoritative text.
