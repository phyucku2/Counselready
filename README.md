# CounselReady

Organize your family court file and walk into your attorney meeting prepared.

CounselReady reads the documents in a family law case — petitions, motions,
declarations, orders, evaluations — and gives you back a structured view of them:

- **Dissection** — what each document is, who filed it, what it asks for, what it
  references.
- **Timeline** — a chronology of events assembled across the whole file, every entry
  linked to the passage it came from.
- **Issue flags** — questions worth raising with your attorney: dates that disagree
  across filings, requests that were never answered.
- **Language review** — what each party actually wrote, quoted and attributed.

**CounselReady does not give legal advice.** It organizes your documents and shows you
what they say, with a citation for every statement. What any of it means for your case
is a question for your attorney — the product exists to make that conversation shorter
and better prepared, not to replace it.

## Status

Pre-release and private. Florida first. Nothing here is deployed or published.

## Contributing

Read [`CLAUDE.md`](CLAUDE.md) first — it is binding on every contributor, human or AI.
Two rules govern everything else:

1. **The non-advice line** (§1) — we organize and surface; we never advise, predict, or
   interpret legal meaning.
2. **Grounded output** (§2) — every generated statement cites document, page, and
   passage. A claim the system cannot point at is a bug.

Decisions live in [`docs/decisions/`](docs/decisions/). Current state of the build is
[`docs/roadmap-status.md`](docs/roadmap-status.md).

## Layout

```
backend/        FastAPI service, SQLAlchemy models, Alembic migrations
frontend/       React + Vite web client
docs/
  decisions/    ADRs — dated, short, why-not-just-what
  brainstorm/   Multi-lens brainstorms and research (CLAUDE.md §8)
  product/      Product specs and positioning
  engineering/  Standards and design notes
```

## Running it

[`docs/engineering/running-locally.md`](docs/engineering/running-locally.md) — Postgres,
the API, and the web client on one machine, with the cautions that apply before you put
real case documents through it.
