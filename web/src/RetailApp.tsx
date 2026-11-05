import type {
  Actor,
  Product,
  History,
  Session,
  Grant,
  Overview,
} from "./types";
import { api, setCsrf } from "./api";
import { money, label } from "./format";
import { Icon, Badge } from "./ui";
import { Catalog } from "./Catalog";
import { PurchaseReview } from "./PurchaseReview";
import { PurchaseActivity } from "./PurchaseActivity";
import React, { useEffect, useState } from "react";

export default function App() {
  const [actor, setActor] = useState<Actor | null>(null),
    [ready, setReady] = useState(false);
  const [authMode, setAuthMode] = useState("loading");
  const [view, setView] = useState("shop"),
    [request, setRequest] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [catalog, setCatalog] = useState<Product[]>([]),
    [history, setHistory] = useState<History[]>([]),
    [session, setSession] = useState<Session | null>(null);
  const [grants, setGrants] = useState<Grant[]>([]),
    [grantId, setGrantId] = useState(""),
    [provider, setProvider] = useState("baseline");
  const [fault, setFault] = useState("none"),
    [overview, setOverview] = useState<Overview | null>(null),
    [now, setNow] = useState(Date.now());
  const [grantTotal, setGrantTotal] = useState("7"),
    [grantLimit, setGrantLimit] = useState("4");
  async function refresh() {
    const [products, sessions, permissions, health] = await Promise.all([
      api<{ products: Product[] }>("/api/v1/catalog"),
      api<{ sessions: History[] }>("/api/v1/sessions"),
      api<{ grants: Grant[] }>("/api/v1/grants"),
      api<{ model_provider: string }>("/health/ready"),
    ]);
    setCatalog(products.products);
    setHistory(sessions.sessions);
    setGrants(permissions.grants);
    setProvider(health.model_provider);
  }
  useEffect(() => {
    api<{ mode: string }>("/api/v1/auth/config")
      .then((data) => setAuthMode(data.mode))
      .catch(() => setError("Unable to load sign-in. Please reload."));
    api<{ actor: Actor; csrf_token: string }>("/api/v1/auth/me")
      .then((data) => {
        setCsrf(data.csrf_token);
        setActor(data.actor);
      })
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    if (actor) refresh().catch((e) => setError(e.message));
  }, [actor]);
  useEffect(() => {
    if (!actor) return;
    let current = true;
    const timer = window.setInterval(() => {
      setNow(Date.now());
      if (
        session &&
        ![
          "COMPLETED",
          "CANCELED",
          "POLICY_DENIED",
          "NO_MATCH",
          "CLARIFICATION_REQUIRED",
          "RECOVERY_REQUIRED",
        ].includes(session.state)
      )
        api<Session>(`/api/v1/sessions/${session.id}`)
          .then((value) => {
            if (current) setSession(value);
          })
          .catch((e) => {
            if (current) setError(e.message);
          });
      if (view === "operations")
        api<Overview>("/api/v1/operator/overview")
          .then((value) => {
            if (current) setOverview(value);
          })
          .catch((e) => {
            if (current) setError(e.message);
          });
    }, 1000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [actor, session?.id, session?.state, view]);
  useEffect(() => {
    if (session?.state === "COMPLETED" || session?.state === "CANCELED")
      refresh().catch(() => {});
  }, [session?.state]);
  async function login(persona: string) {
    try {
      setBusy(true);
      const data = await api<{ actor: Actor; csrf_token: string }>(
        "/api/v1/auth/demo",
        { method: "POST", body: JSON.stringify({ persona }) },
      );
      setCsrf(data.csrf_token);
      setActor(data.actor);
      setSession(null);
      setView(persona === "operator" ? "operations" : "shop");
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submit(text = request) {
    if (!text.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ session_id: string }>("/api/v1/sessions", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ request: text, grant_id: grantId || null }),
      });
      setSession(await api<Session>(`/api/v1/sessions/${result.session_id}`));
      setRequest("");
      setView("shop");
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function approve() {
    if (!session?.quote) return;
    setBusy(true);
    setError("");
    try {
      const q = session.quote;
      const approval = await api<{ id: string }>(
        `/api/v1/quotes/${q.id}/approval`,
        { method: "POST", body: JSON.stringify({ quote_digest: q.digest }) },
      );
      await api("/api/v1/executions", {
        method: "POST",
        headers: { "Idempotency-Key": `checkout-${q.id}` },
        body: JSON.stringify({
          quote_id: q.id,
          approval_id: approval.id,
          fault_profile: fault,
        }),
      });
      setSession(await api<Session>(`/api/v1/sessions/${session.id}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function createGrant() {
    setBusy(true);
    setError("");
    try {
      const result = await api<Grant>("/api/v1/grants", {
        method: "POST",
        body: JSON.stringify({
          product_ids: ["bar-cocoa", "bar-peanut", "last-bar"],
          kiosk_ids: ["kiosk-a"],
          per_purchase_minor: Math.round(Number(grantLimit) * 100),
          total_minor: Math.round(Number(grantTotal) * 100),
          max_purchases: 3,
          valid_for_seconds: 3600,
        }),
      });
      setGrantId(result.id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!ready) return <div className="loading">Opening your workspace…</div>;
  if (!actor)
    return (
      <main className="login-page">
        <div className="login-card">
          <span className="brand-mark">
            <Icon name="bag" size={30} />
          </span>
          <p className="eyebrow">AGENTIC COMMERCE / LOCAL DEMO</p>
          <h1>
            A purchase,
            <br />
            with proof.
          </h1>
          <p className="muted">
            Describe what you need. Review the exact purchase. Follow it through
            payment and delivery.
          </p>
          <div className="login-options">
            {authMode === "oidc" ? (
              <button
                onClick={() => window.location.assign("/api/v1/auth/login")}
              >
                Sign in securely <Icon name="arrow" />
              </button>
            ) : authMode === "demo" ? (
              <>
                <button onClick={() => login("alex")} disabled={busy}>
                  Enter Alex’s workspace <Icon name="arrow" />
                </button>
                <button
                  className="secondary"
                  onClick={() => login("sam")}
                  disabled={busy}
                >
                  Enter Sam’s workspace
                </button>
                <button
                  className="text-button"
                  onClick={() => login("operator")}
                  disabled={busy}
                >
                  Open operations console
                </button>
              </>
            ) : (
              <p role="status">Loading sign-in…</p>
            )}
          </div>
          <p className="fine-print">
            Synthetic products and payments. This workspace runs locally on this
            computer.
          </p>
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
        </div>
        <div className="login-art">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="art-card">
            <Icon name="shield" size={38} />
            <h2>
              Your intent.
              <br />
              Your approval.
              <br />A verified outcome.
            </h2>
            <span className="art-label">01 — THE PURCHASE WORKSPACE</span>
          </div>
        </div>
      </main>
    );
  return (
    <div className="layout">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="Agentic Commerce home">
          <span className="brand-mark">
            <Icon name="bag" />
          </span>
          <span>
            agentic<span className="brand-light">commerce</span>
          </span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <div className="workspace">
          <div className="workspace-icon">A</div>
          <div>
            <strong>Kiosk A</strong>
            <small>Demo storefront</small>
          </div>
          <span className="live-dot" />
        </div>
        <nav aria-label="Main navigation">
          {[
            ["shop", "spark", "Shopping assistant"],
            ["activity", "clock", "Purchase history"],
            ["permissions", "shield", "Spending permissions"],
            ...(actor.role === "operator"
              ? [["operations", "settings", "Operations"]]
              : []),
          ].map(([id, icon, title]) => (
            <button
              key={id}
              className={view === id ? "nav-active" : ""}
              onClick={() => {
                setView(id);
                if (id === "operations")
                  api<Overview>("/api/v1/operator/overview")
                    .then(setOverview)
                    .catch((e) => setError(e.message));
                if (id === "activity" || id === "permissions")
                  refresh().catch((e) => setError(e.message));
              }}
            >
              <Icon name={icon} />
              {title}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="security-note">
            <Icon name="shield" />
            <div>
              <strong>Permission comes first</strong>
              <small>
                The assistant cannot approve a purchase on your behalf.
              </small>
            </div>
          </div>
          <div className="user">
            <span className="avatar">
              {(actor.display_name || actor.user_id)[0].toUpperCase()}
            </span>
            <div>
              <strong>
                {actor.user_id === "operator"
                  ? "Operations"
                  : `${(actor.display_name || actor.user_id)[0].toUpperCase()}${actor.user_id.slice(1)}`}
              </strong>
              <small>Local demonstration</small>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={async () => {
                await api("/api/v1/auth/logout", { method: "POST" });
                setActor(null);
                setSession(null);
                setCsrf("");
              }}
            >
              <Icon name="exit" />
            </button>
          </div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <span>
            Workspace <span className="slash">/</span>{" "}
            {view === "shop"
              ? "Shopping assistant"
              : view === "permissions"
                ? "Permissions"
                : view === "operations"
                  ? "Operations"
                  : "History"}
          </span>
          <div className="topbar-right">
            <span className="provider">
              <span className="live-dot" />
              {provider === "codex" ? "Codex · local" : "Rule baseline"}
            </span>
            <span className="demo-pill">SANDBOX</span>
          </div>
        </header>
        <div className="content">
          {error && (
            <div className="error" role="alert">
              <span>{error}</span>
              <button className="text-button" onClick={() => setError("")}>
                Dismiss
              </button>
            </div>
          )}
          {view === "shop" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">YOUR INTENT, FOLLOWED THROUGH</p>
                  <h1>What can we pick up for you?</h1>
                  <p className="muted">
                    One request. Exact approval. A purchase you can follow.
                  </p>
                </div>
                <div className="heading-icon">
                  <Icon name="spark" size={28} />
                </div>
              </div>
              <div className="shop-grid">
                <section className="shopping-column">
                  <div className="composer card">
                    <div className="composer-label">
                      <Icon name="spark" />
                      <strong>Shopping assistant</strong>
                      <span>At Kiosk A</span>
                    </div>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        submit();
                      }}
                    >
                      <label className="sr-only" htmlFor="shopping-request">
                        Shopping request
                      </label>
                      <textarea
                        id="shopping-request"
                        placeholder="Find me a cocoa protein bar under $4…"
                        value={request}
                        maxLength={2000}
                        onChange={(e) => setRequest(e.target.value)}
                      />
                      <div className="composer-footer">
                        <label className="permission-select">
                          <Icon name="shield" size={16} />
                          <select
                            aria-label="Purchase permission"
                            value={grantId}
                            onChange={(e) => setGrantId(e.target.value)}
                          >
                            <option value="">Ask me before buying</option>
                            {grants
                              .filter(
                                (g) => !g.revoked && g.expires_at * 1000 > now,
                              )
                              .map((g) => (
                                <option key={g.id} value={g.id}>
                                  Use permission ·{" "}
                                  {money(
                                    g.total_minor -
                                      g.spent_minor -
                                      g.held_minor,
                                  )}{" "}
                                  left
                                </option>
                              ))}
                          </select>
                        </label>
                        <button
                          type="submit"
                          disabled={busy || !request.trim()}
                        >
                          {busy ? "Working…" : "Find an item"}
                          <Icon name="arrow" size={18} />
                        </button>
                      </div>
                    </form>
                  </div>
                  <div className="suggestions">
                    <span>TRY A REQUEST</span>
                    {[
                      "A cocoa protein bar under $4",
                      "Lime sparkling water under $3",
                    ].map((text) => (
                      <button
                        key={text}
                        onClick={() =>
                          setRequest(`Find ${text.toLowerCase()} at Kiosk A`)
                        }
                      >
                        {text}
                        <span>↗</span>
                      </button>
                    ))}
                  </div>
                  {session && (
                    <PurchaseActivity
                      session={session}
                      onRetry={async () => {
                        try {
                          await api(`/api/v1/sessions/${session.id}/retry`, {
                            method: "POST",
                          });
                          setSession({ ...session, state: "QUEUED" });
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    />
                  )}
                  <Catalog catalog={catalog} onSelect={setRequest} />
                </section>
                <PurchaseReview
                  session={session}
                  now={now}
                  busy={busy}
                  fault={fault}
                  onApprove={approve}
                  onFaultChange={setFault}
                />
              </div>
            </>
          )}
          {view === "activity" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">EVERY REQUEST HAS A RECORD</p>
                  <h1>Purchase history</h1>
                  <p className="muted">
                    Reopen a purchase to see its approval and confirmed outcome.
                  </p>
                </div>
              </div>
              <div className="card history">
                {history.length ? (
                  history.map((row) => (
                    <button
                      key={row.id}
                      onClick={async () => {
                        setSession(
                          await api<Session>(`/api/v1/sessions/${row.id}`),
                        );
                        setView("shop");
                      }}
                    >
                      <span className="history-icon">
                        <Icon name="bag" />
                      </span>
                      <span className="history-text">
                        <strong>{row.request}</strong>
                        <small>
                          {new Date(row.created_at * 1000).toLocaleString()}
                        </small>
                      </span>
                      <Badge state={row.state} />
                      <Icon name="arrow" size={18} />
                    </button>
                  ))
                ) : (
                  <div className="empty-state">
                    Your purchases will appear here.
                  </div>
                )}
              </div>
            </>
          )}
          {view === "permissions" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">AUTONOMY WITH BOUNDARIES</p>
                  <h1>Spending permissions</h1>
                  <p className="muted">
                    Set exactly what your assistant can buy, and how much it can
                    spend.
                  </p>
                </div>
              </div>
              <div className="permissions-grid">
                <section className="card permission-form">
                  <h2>A small, explicit allowance</h2>
                  <p className="muted">
                    Allow protein bars at Kiosk A for one hour. Maximum three
                    purchases. Pending purchases count toward your budget.
                  </p>
                  <label>
                    Maximum per purchase
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={grantLimit}
                      onChange={(e) => setGrantLimit(e.target.value)}
                    />
                  </label>
                  <label>
                    Total allowance
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={grantTotal}
                      onChange={(e) => setGrantTotal(e.target.value)}
                    />
                  </label>
                  <button disabled={busy} onClick={createGrant}>
                    <Icon name="shield" size={18} />
                    Create permission
                  </button>
                  <p className="fine-print">
                    Revocation stops new checkouts. An already accepted
                    transaction may still finish.
                  </p>
                </section>
                <div>
                  {grants.map((grant) => (
                    <section className="card grant-card" key={grant.id}>
                      <div className="section-heading">
                        <h2>Protein bars · Kiosk A</h2>
                        <Badge
                          state={
                            grant.revoked
                              ? "REVOKED"
                              : grant.expires_at * 1000 < now
                                ? "EXPIRED"
                                : "ACTIVE"
                          }
                        />
                      </div>
                      <div className="grant-amount">
                        {money(
                          grant.total_minor -
                            grant.spent_minor -
                            grant.held_minor,
                        )}
                        <small>available of {money(grant.total_minor)}</small>
                      </div>
                      <div className="budget-bar">
                        <span
                          style={{
                            width: `${(100 * (grant.spent_minor + grant.held_minor)) / grant.total_minor}%`,
                          }}
                        />
                      </div>
                      <p className="small muted">
                        Spent {money(grant.spent_minor)} · Pending{" "}
                        {money(grant.held_minor)} · Per purchase{" "}
                        {money(grant.per_purchase_minor)}
                      </p>
                      <p className="fine-print">
                        Expires{" "}
                        {new Date(grant.expires_at * 1000).toLocaleString()}
                      </p>
                      <button
                        className="secondary"
                        disabled={grant.revoked}
                        onClick={async () => {
                          try {
                            await api(`/api/v1/grants/${grant.id}/revoke`, {
                              method: "POST",
                            });
                            if (grantId === grant.id) setGrantId("");
                            await refresh();
                          } catch (e) {
                            setError((e as Error).message);
                          }
                        }}
                      >
                        Revoke permission
                      </button>
                    </section>
                  ))}
                </div>
              </div>
            </>
          )}
          {view === "operations" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">OBSERVE. RECONCILE. RECOVER.</p>
                  <h1>Operations</h1>
                  <p className="muted">
                    Payment, delivery and order states remain visible
                    independently.
                  </p>
                </div>
              </div>
              <div className="stats-grid">
                <div className="card stat">
                  <small>RECENT PURCHASES</small>
                  <strong>{overview?.executions.length || 0}</strong>
                </div>
                <div className="card stat">
                  <small>COMPLETED</small>
                  <strong>
                    {overview?.executions.filter((e) => e.state === "COMPLETED")
                      .length || 0}
                  </strong>
                </div>
                <div className="card stat">
                  <small>NEED REVIEW</small>
                  <strong>
                    {overview?.executions.filter(
                      (e) => e.state === "RECOVERY_REQUIRED",
                    ).length || 0}
                  </strong>
                </div>
              </div>
              <section className="card table-card">
                <h2>Purchase executions</h2>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Execution</th>
                        <th>Order</th>
                        <th>Payment</th>
                        <th>Delivery</th>
                        <th>Recovery</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview?.executions.map((e) => (
                        <tr key={e.id}>
                          <td>
                            <code>{e.id.slice(0, 8)}</code>
                          </td>
                          <td>
                            <Badge state={e.state} />
                          </td>
                          <td>
                            <Badge state={e.payment_state} />
                          </td>
                          <td>
                            <Badge state={e.fulfillment_state} />
                          </td>
                          <td>
                            {e.state === "RECOVERY_REQUIRED" &&
                            e.failure_code !==
                              "CAPTURE_DECLINED_AFTER_DELIVERY" ? (
                              <button
                                className="secondary small"
                                onClick={async () => {
                                  try {
                                    await api(
                                      `/api/v1/operator/executions/${e.id}/retry`,
                                      { method: "POST" },
                                    );
                                  } catch (error) {
                                    setError((error as Error).message);
                                  }
                                }}
                              >
                                Retry original action
                              </button>
                            ) : (
                              <span className="small muted">
                                {e.failure_code ? label(e.failure_code) : "—"}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!overview?.executions.length && (
                  <div className="empty-state">
                    No executions yet. Open a shopper workspace to make a
                    purchase.
                  </div>
                )}
              </section>
              <section className="card table-card">
                <h2>Durable work</h2>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Kind</th>
                        <th>Resource</th>
                        <th>State</th>
                        <th>Attempts</th>
                        <th>Last issue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview?.jobs.map((job) => (
                        <tr key={job.id}>
                          <td>{label(job.kind)}</td>
                          <td>
                            <code>{job.resource_id.slice(0, 8)}</code>
                          </td>
                          <td>
                            <Badge state={job.state} />
                          </td>
                          <td>{job.attempts}</td>
                          <td>{job.last_error || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
          <footer className="page-footer">
            <span>Agentic Commerce</span>
            <span>Local demonstration · Synthetic transactions · v0.1</span>
          </footer>
        </div>
      </div>
    </div>
  );
}
