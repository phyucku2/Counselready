import { useCallback, useEffect, useState } from "react";
import {
  Link,
  Navigate,
  Route,
  BrowserRouter as Router,
  Routes,
  useParams,
} from "react-router-dom";
import {
  ApiError,
  api,
  clearTokens,
  isSignedIn,
  type CaseSummary,
  type DocumentDetail,
  type DocumentSummary,
  type Page,
  type Passage,
  type TimelineEvent,
} from "./api";

/** Plain-language message for anything that went wrong. */
function message(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}

function Notice({ children }: { children: React.ReactNode }) {
  // role=alert so a screen reader announces the failure rather than leaving the
  // user waiting for a response that already arrived.
  return (
    <p className="notice" role="alert">
      {children}
    </p>
  );
}

function Shell({ children, onSignOut }: { children: React.ReactNode; onSignOut?: () => void }) {
  return (
    <>
      <header className="bar">
        <div className="inner">
          <div className="brand">
            CounselReady
            <span>Organize your file. Your attorney advises.</span>
          </div>
          {onSignOut && (
            <button className="secondary" onClick={onSignOut}>
              Sign out
            </button>
          )}
        </div>
      </header>
      <main className="page">{children}</main>
    </>
  );
}

function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (needsCode) {
        await api.verifyMfa(code);
        onSignedIn();
        return;
      }
      if (registering) await api.register(email, password);
      const outcome = await api.login(email, password);
      if (outcome === "mfa_required") setNeedsCode(true);
      else onSignedIn();
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <h1>{registering ? "Create your account" : "Sign in"}</h1>
      <p className="lede">
        CounselReady organizes the documents in your case so you can walk into your
        attorney meeting prepared. It does not give legal advice.
      </p>

      <form className="card stack" onSubmit={submit}>
        {error && <Notice>{error}</Notice>}

        {needsCode ? (
          <div>
            <label htmlFor="code">Verification code</label>
            <input
              id="code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
            />
            <p className="hint">
              From your authenticator app, or one of your recovery codes.
            </p>
          </div>
        ) : (
          <>
            <div>
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete={registering ? "new-password" : "current-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              {registering && <p className="hint">At least 12 characters.</p>}
            </div>
          </>
        )}

        <div className="row-actions">
          <button type="submit" disabled={busy}>
            {busy ? "Working…" : needsCode ? "Verify" : registering ? "Create account" : "Sign in"}
          </button>
          {!needsCode && (
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setRegistering(!registering);
                setError(null);
              }}
            >
              {registering ? "I already have an account" : "Create an account"}
            </button>
          )}
        </div>
      </form>
    </Shell>
  );
}

function Cases({ onSignOut }: { onSignOut: () => void }) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setCases(await api.listCases());
    } catch (caught) {
      setError(message(caught));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createCase(title.trim());
      setTitle("");
      await load();
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell onSignOut={onSignOut}>
      <h1>Your cases</h1>
      <p className="lede">
        A case holds the filings for one matter. Family matters often run in parallel,
        so keep a dissolution, an injunction, and a support case separate.
      </p>

      {error && <Notice>{error}</Notice>}

      <form className="card stack" onSubmit={create}>
        <div>
          <label htmlFor="title">New case name</label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="e.g. Dissolution — Roe"
            required
          />
        </div>
        <div>
          <button type="submit" disabled={busy || title.trim() === ""}>
            {busy ? "Creating…" : "Create case"}
          </button>
        </div>
      </form>

      <h2>Open cases</h2>
      {cases === null ? (
        <p role="status">Loading…</p>
      ) : cases.length === 0 ? (
        <p className="empty">No cases yet. Create one above to start adding documents.</p>
      ) : (
        <ul className="list">
          {cases.map((item) => (
            <li key={item.id}>
              <Link to={`/cases/${item.id}`}>
                <span>{item.title}</span>
                <span className="tag">{item.jurisdiction}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}

/** Plain words for a pipeline state the user did not ask about. */
function describeStatus(status: string): string {
  switch (status) {
    case "complete":
      return "Text read";
    case "needs_ocr":
      return "Scanned — text not read yet";
    case "processing":
      return "Reading…";
    case "failed":
      return "Could not read";
    default:
      return "Waiting";
  }
}

function CaseDetail({ onSignOut }: { onSignOut: () => void }) {
  const { caseId = "" } = useParams();
  const [matter, setMatter] = useState<CaseSummary | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [detail, docs] = await Promise.all([
        api.readCase(caseId),
        api.listDocuments(caseId),
      ]);
      setMatter(detail);
      setDocuments(docs);
    } catch (caught) {
      setError(message(caught));
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const created = await api.uploadDocument(caseId, file);
      setNote(
        created.ocr_status === "needs_ocr"
          ? `Added “${created.title}”. Some pages are scanned images, so their text has not been read yet.`
          : `Added “${created.title}” — ${created.page_count} page${created.page_count === 1 ? "" : "s"} read.`,
      );
      await load();
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  if (error && !matter) {
    return (
      <Shell onSignOut={onSignOut}>
        <Notice>{error}</Notice>
        <p>
          <Link to="/cases">Back to your cases</Link>
        </p>
      </Shell>
    );
  }

  return (
    <Shell onSignOut={onSignOut}>
      <p className="meta">
        <Link to="/cases">← Your cases</Link>
      </p>
      <h1>{matter?.title ?? "Loading…"}</h1>
      <p style={{ margin: "0 0 1.25rem" }}>
        <Link to={`/cases/${caseId}/timeline`}>View the timeline for this case →</Link>
      </p>
      <p className="lede">
        Add the filings in this matter — petitions, motions, orders, notices. Same
        document twice is fine; it will be recognized.
      </p>

      {error && <Notice>{error}</Notice>}
      {note && (
        <p
          className="notice"
          role="status"
          style={{ borderLeftColor: "var(--accent)", background: "#f2f8f5", color: "var(--ink)" }}
        >
          {note}
        </p>
      )}

      <div className="card stack">
        <div>
          <label htmlFor="file">Add a document (PDF)</label>
          <input id="file" type="file" accept="application/pdf" onChange={upload} disabled={busy} />
          <p className="hint">
            {busy ? "Reading the document…" : "Up to 100 MB. Nothing is shared with anyone."}
          </p>
        </div>
      </div>

      <h2>Documents</h2>
      {documents === null ? (
        <p role="status">Loading…</p>
      ) : documents.length === 0 ? (
        <p className="empty">Nothing here yet. Add the first filing above.</p>
      ) : (
        <ul className="list">
          {documents.map((document) => (
            <li key={document.id}>
              <Link to={`/cases/${caseId}/documents/${document.id}`}>
                <span>{document.title}</span>
                <span className="meta">
                  {document.page_count} page{document.page_count === 1 ? "" : "s"} ·{" "}
                  {describeStatus(document.ocr_status)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <p className="footnote">
        CounselReady organizes what your documents say and shows you where each
        statement came from. It does not give legal advice, predict outcomes, or tell
        you what to do — those are questions for your attorney.
      </p>
    </Shell>
  );
}

/**
 * A date rendered no more precisely than the source knew it.
 *
 * A filing that says "in March" must never surface as "March 1, 2026, 12:00 AM".
 * That is not a formatting nicety — on a legal chronology, invented precision is a
 * false statement about what the document says.
 */
function formatOccurred(iso: string, precision: TimelineEvent["date_precision"]): string {
  const when = new Date(iso);
  switch (precision) {
    case "year":
      return String(when.getFullYear());
    case "month":
      return when.toLocaleDateString(undefined, { year: "numeric", month: "long" });
    case "exact":
      return when.toLocaleString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    default:
      return when.toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
  }
}

/** Midday local time, so no timezone offset can shift a date onto the wrong day. */
function middayIso(day: string): string {
  return new Date(`${day}T12:00:00`).toISOString();
}

/**
 * The correction affordance on one entry.
 *
 * Deliberately not an edit control. The entry stays exactly as recorded and the note
 * is added beside it, so the wording here says "add a correction", never "edit" —
 * the label has to match what actually happens or the permanence is a surprise.
 */
function Correction({
  caseId,
  event,
  onAdded,
}: {
  caseId: string;
  event: TimelineEvent;
  onAdded: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(submitted: React.FormEvent) {
    submitted.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.addNote(caseId, event.id, body.trim());
      setBody("");
      setOpen(false);
      await onAdded();
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="quiet" onClick={() => setOpen(true)}>
        Add a correction
      </button>
    );
  }

  return (
    <form className="correction-form" onSubmit={submit}>
      {error && <Notice>{error}</Notice>}
      <div>
        <label htmlFor={`correction-${event.id}`}>Correction</label>
        <textarea
          id={`correction-${event.id}`}
          rows={2}
          value={body}
          onChange={(changed) => setBody(changed.target.value)}
          placeholder="What is wrong, and what is correct."
          required
        />
        <p className="hint">
          The entry above stays exactly as it was recorded. This is added beside it.
        </p>
      </div>
      <div className="row-actions">
        <button type="submit" disabled={busy || body.trim() === ""}>
          {busy ? "Saving…" : "Save correction"}
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setOpen(false);
            setError(null);
          }}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function Timeline({ onSignOut }: { onSignOut: () => void }) {
  const { caseId = "" } = useParams();
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [summary, setSummary] = useState("");
  const [day, setDay] = useState("");
  const [precision, setPrecision] = useState<TimelineEvent["date_precision"]>("day");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setEvents(await api.listEvents(caseId));
    } catch (caught) {
      setError(message(caught));
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createEvent(caseId, {
        summary: summary.trim(),
        occurred_at: middayIso(day),
        date_precision: precision,
      });
      setSummary("");
      setDay("");
      setPrecision("day");
      await load();
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell onSignOut={onSignOut}>
      <p className="meta">
        <Link to={`/cases/${caseId}`}>← Back to the case</Link>
      </p>
      <h1>Timeline</h1>
      <p className="lede">
        Everything in this case, in order. Entries read out of your documents carry the
        page they came from; entries you add are marked as your own account. Entries are
        permanent — if something is wrong, add a correction and both stay on the record.
      </p>

      {error && <Notice>{error}</Notice>}

      <form className="card stack" onSubmit={add}>
        <div>
          <label htmlFor="summary">What happened</label>
          <textarea
            id="summary"
            rows={3}
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            placeholder="Describe it plainly, as you would to your attorney."
            required
          />
        </div>
        <div className="row-actions">
          <div>
            <label htmlFor="day">Date</label>
            <input
              id="day"
              type="date"
              value={day}
              onChange={(event) => setDay(event.target.value)}
              required
            />
          </div>
          <div>
            <label htmlFor="precision">How well do you know the date?</label>
            <select
              id="precision"
              value={precision}
              onChange={(event) =>
                setPrecision(event.target.value as TimelineEvent["date_precision"])
              }
            >
              <option value="day">The exact day</option>
              <option value="month">Only the month</option>
              <option value="year">Only the year</option>
            </select>
          </div>
        </div>
        <div>
          <button type="submit" disabled={busy || summary.trim() === "" || day === ""}>
            {busy ? "Adding…" : "Add to timeline"}
          </button>
          <p className="hint">
            This is recorded as your account of events, not as something a document says.
          </p>
        </div>
      </form>

      <h2>Chronology</h2>
      {events === null ? (
        <p role="status">Loading…</p>
      ) : events.length === 0 ? (
        <p className="empty">
          Nothing on the timeline yet. Add what you remember above, or upload the filings
          in this case.
        </p>
      ) : (
        <ol className="timeline">
          {events.map((event) => (
            <li key={event.id}>
              <div className="when">{formatOccurred(event.occurred_at, event.date_precision)}</div>
              <p className="what">{event.summary}</p>
              {event.citation ? (
                <p className="source">
                  <Link to={`/cases/${caseId}/documents/${event.citation.document_id}`}>
                    {event.citation.document_title}, page {event.citation.page_number}
                  </Link>
                  <span className="quote">“{event.citation.quote}”</span>
                </p>
              ) : (
                <p className="source">
                  <span className="tag">Your own account — no document says this</span>
                </p>
              )}

              {event.notes.length > 0 && (
                <ul className="corrections">
                  {event.notes.map((correction) => (
                    <li key={correction.id}>
                      <span className="stamp">
                        Correction ·{" "}
                        {new Date(correction.created_at).toLocaleDateString(undefined, {
                          year: "numeric",
                          month: "long",
                          day: "numeric",
                        })}
                      </span>
                      <p>{correction.body}</p>
                    </li>
                  ))}
                </ul>
              )}

              <Correction caseId={caseId} event={event} onAdded={load} />
            </li>
          ))}
        </ol>
      )}
    </Shell>
  );
}

/**
 * A page split into highlighted and unhighlighted runs.
 *
 * Overlapping or out-of-range passages are clamped rather than trusted, because a bad
 * offset must degrade to "no highlight" and never to text silently dropped from the
 * page the reader is checking.
 */
function segments(text: string, passages: Passage[]): { text: string; cited: boolean }[] {
  const out: { text: string; cited: boolean }[] = [];
  let cursor = 0;
  for (const passage of passages) {
    const start = Math.max(cursor, Math.min(passage.start_offset, text.length));
    const end = Math.max(start, Math.min(passage.end_offset, text.length));
    if (start > cursor) out.push({ text: text.slice(cursor, start), cited: false });
    if (end > start) out.push({ text: text.slice(start, end), cited: true });
    cursor = Math.max(cursor, end);
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor), cited: false });
  return out;
}

function PageView({ page }: { page: Page }) {
  return (
    <section className="card page-text" aria-label={`Page ${page.page_number}`}>
      <p className="meta">
        Page {page.page_number}
        {page.ocr_confidence !== null &&
          ` · read by OCR, ${Math.round(page.ocr_confidence * 100)}% confident`}
      </p>
      {page.text.trim() === "" ? (
        <p className="empty">
          This page is an image. Its text has not been read, so nothing on it has been
          searched or placed on your timeline.
        </p>
      ) : (
        <p>
          {segments(page.text, page.passages).map((run, index) =>
            run.cited ? <mark key={index}>{run.text}</mark> : <span key={index}>{run.text}</span>,
          )}
        </p>
      )}
    </section>
  );
}

function DocumentViewer({ onSignOut }: { onSignOut: () => void }) {
  const { caseId = "", documentId = "" } = useParams();
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setDetail(await api.readDocument(caseId, documentId));
      } catch (caught) {
        setError(message(caught));
      }
    })();
  }, [caseId, documentId]);

  const cited = detail?.pages.reduce((total, page) => total + page.passages.length, 0) ?? 0;

  return (
    <Shell onSignOut={onSignOut}>
      <p className="meta">
        <Link to={`/cases/${caseId}`}>← Back to the case</Link>
      </p>
      <h1>{detail?.title ?? "Loading…"}</h1>
      {error && <Notice>{error}</Notice>}

      {detail && (
        <>
          <p className="lede">
            {detail.page_count} page{detail.page_count === 1 ? "" : "s"} ·{" "}
            {describeStatus(detail.ocr_status)}
            {cited === 0
              ? " · nothing has been extracted from this document yet"
              : ` · ${cited} passage${cited === 1 ? "" : "s"} highlighted`}
          </p>
          {detail.pages.map((page) => (
            <PageView key={page.page_number} page={page} />
          ))}
        </>
      )}

      <p className="footnote">
        This is the text as it was read from your file, not a summary of it. Where a
        statement elsewhere in CounselReady points at this document, the passage it
        points at is highlighted here.
      </p>
    </Shell>
  );
}

export default function App() {
  const [signedIn, setSignedIn] = useState(isSignedIn());

  async function signOut() {
    await api.logout();
    clearTokens();
    setSignedIn(false);
  }

  if (!signedIn) return <SignIn onSignedIn={() => setSignedIn(true)} />;

  return (
    <Router>
      <Routes>
        <Route path="/cases" element={<Cases onSignOut={signOut} />} />
        <Route path="/cases/:caseId" element={<CaseDetail onSignOut={signOut} />} />
        <Route path="/cases/:caseId/timeline" element={<Timeline onSignOut={signOut} />} />
        <Route
          path="/cases/:caseId/documents/:documentId"
          element={<DocumentViewer onSignOut={signOut} />}
        />
        <Route path="*" element={<Navigate to="/cases" replace />} />
      </Routes>
    </Router>
  );
}
