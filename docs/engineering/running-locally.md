# Running CounselReady on your own machine

Everything below runs on one computer. No cloud service is involved, nothing is
uploaded anywhere, and the app makes no outbound network calls.

## Before you start — what "local" does and does not protect

Running locally means your documents never leave your machine. Two things it does
**not** mean:

- **Local PostgreSQL is not encrypted at rest.** The extracted text of every document
  sits in a database file on your disk in plain text. If your machine's disk is not
  encrypted (FileVault, BitLocker), turn that on before putting real case documents in.
- **The document bytes live outside the repository**, at the path you set as
  `OBJECT_ROOT` below. Keep it outside the checkout so a stray `git add` can never
  sweep a filing into version control. `/samples/` and `/case-files/` are gitignored as
  a second line of defence, but the object root is the real one.

Nothing in this repo — fixtures, tests, seeds — may ever contain real case material
(CLAUDE.md §3). Use synthetic documents for anything you commit.

## 1. PostgreSQL

PostgreSQL 16. Create a role and two databases — one you use, one the tests wipe:

```
createuser counselready --pwprompt
createdb -O counselready counselready_dev
createdb -O counselready counselready_test
```

## 2. Backend

```
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

Create `backend/.env` (gitignored — never commit it):

```
APP_ENV=local
DATABASE_URL=postgresql+asyncpg://counselready:<password>@127.0.0.1:5432/counselready_dev
JWT_SECRET=<at least 32 random characters>
MFA_ENCRYPTION_KEY=<a Fernet key>
OBJECT_ROOT=<a directory outside this repo>
```

Generate the two keys with:

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Then bring the schema up and start the API:

```
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

`http://127.0.0.1:8000/readyz` should answer `{"status":"ok","database":"ok"}`.
Interactive API docs are at `/docs`.

## 3. Frontend

```
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The dev server proxies `/api` to the backend, so the
browser only ever talks to one origin and no CORS configuration exists to get wrong.

Create an account on the sign-in screen — registration is open because the only person
who can reach this server is you.

## 4. What works today

- Create a case, upload PDFs into it, and see them listed.
- Open a document and read the text exactly as it was extracted, page by page.
- Build a timeline by hand. Entries you type are labelled as your own account of
  events; once extraction ships, entries read out of documents will appear in the same
  chronology carrying the page and passage they came from.
- **Correct an entry without erasing it.** Entries are permanent; "Add a correction"
  records a note beside the entry and both stay on the record. That applies to
  document-derived entries too — the citation keeps pointing at what the filing says,
  and your disagreement sits next to it, attributed to you.

Not yet built: document dissection, automatic timeline extraction, issue flags, and
language review. A scanned PDF with no text layer is honestly reported as
*"Scanned — text not read yet"* rather than silently treated as empty — OCR needs the
Azure engine, which is owner-side work.

## Running the quality gate

```
cd backend
export TEST_DATABASE_URL=postgresql+asyncpg://counselready:<password>@127.0.0.1:5432/counselready_test
ruff check . && ruff format --check . && mypy app && pytest
```

The integration tests run the real migrations against `counselready_test` and wipe it
each session — point it at a scratch database, never at the one holding your case.

```
cd frontend
npx tsc --noEmit && npx vite build
```
