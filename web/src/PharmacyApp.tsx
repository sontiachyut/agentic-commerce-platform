import { useEffect, useRef, useState } from "react";
import { api, setCsrf } from "./api";
import type { Actor } from "./types";
import "./pharmacy.css";

type Member = {
  id: string;
  alias: string;
  name: string;
  relationship: string;
  access_approved: boolean;
  regular: {
    name: string;
    kind: string;
    package: string;
    price_minor: number;
    eligibility: string;
    coverage: string;
  } | null;
};
type Place = {
  id: string;
  name: string;
  address: string;
  distance_miles?: number;
  eligible?: boolean;
  reason?: string;
};
type Permission = {
  id: string;
  per_order_minor: number;
  total_minor: number;
  held_minor: number;
  spent_minor: number;
  expires_at: number;
  revoked: boolean;
};
type Line = {
  alias: string;
  name: string;
  member_name: string;
  package: string;
  amount_minor: number;
  kind: string;
  quantity: number;
};
type Terms = {
  lines: Line[];
  amount_minor: number;
  facility: Place;
  alternatives: Place[];
  requested_limit_minor: number;
  budget_comparison: string;
};
type Order = {
  id: string;
  reference: string;
  state: string;
  payment_state: string;
  fulfillment_state: string;
  amount_minor: number;
  facility: Place;
  terms: Terms;
  pickup_code: string | null;
};
type Result = {
  id: string;
  text: string;
  state: string;
  message: string;
  quote: {
    id: string;
    digest: string;
    terms: Terms;
    expires_at: number;
  } | null;
  order: Order | null;
  events: { type: string; at: number }[];
};
type Workspace = {
  home: string;
  members: Member[];
  permission: Permission | null;
  facilities: Place[];
  requests: { id: string; text: string; state: string; message: string }[];
  orders?: Order[];
  model_provider: string;
};
const usd = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    n / 100,
  );
const nice = (s: string) => s.toLowerCase().replaceAll("_", " ");
function Symbol({
  kind = "leaf",
  size = 20,
}: {
  kind?: string;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {kind === "mic" ? (
        <>
          <rect x="9" y="2" width="6" height="13" rx="3" />
          <path d="M5 10v2a7 7 0 0014 0v-2M12 19v3M8 22h8" />
        </>
      ) : kind === "pin" ? (
        <>
          <path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1116 0Z" />
          <circle cx="12" cy="10" r="2.5" />
        </>
      ) : kind === "check" ? (
        <path d="m5 12 4 4 10-10" />
      ) : kind === "pill" ? (
        <>
          <rect
            x="3"
            y="7"
            width="18"
            height="10"
            rx="5"
            transform="rotate(-40 12 12)"
          />
          <path d="m9 8 6 8" />
        </>
      ) : kind === "shield" ? (
        <>
          <path d="m12 2 8 3v6c0 6-8 11-8 11S4 17 4 11V5l8-3Z" />
          <path d="m8 11 3 3 5-5" />
        </>
      ) : kind === "arrow" ? (
        <path d="M4 12h15m-5-5 5 5-5 5" />
      ) : kind === "clock" ? (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </>
      ) : (
        <>
          <path d="M20 3C10 2 3 7 5 14c2 7 14 5 15-11Z" />
          <path d="M4 21 15 9" />
        </>
      )}
    </svg>
  );
}

export default function PharmacyApp() {
  const [actor, setActor] = useState<Actor | null>(null),
    [authMode, setAuthMode] = useState(""),
    [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [view, setView] = useState("pickup"),
    [text, setText] = useState(""),
    [result, setResult] = useState<Result | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [permissionOpen, setPermissionOpen] = useState(false),
    [limit, setLimit] = useState("50"),
    [voiceAvailable, setVoiceAvailable] = useState(false),
    [naturalVoiceAvailable, setNaturalVoiceAvailable] = useState(false),
    [voiceNotice, setVoiceNotice] = useState(""),
    [recording, setRecording] = useState(false),
    [transcribing, setTranscribing] = useState(false),
    [voiceOn, setVoiceOn] = useState(true),
    [spoken, setSpoken] = useState(""),
    [staffReview, setStaffReview] = useState<Record<string, boolean>>({}),
    [codes, setCodes] = useState<Record<string, string>>({});
  const progressCard = useRef<HTMLElement | null>(null);
  const playback = useRef<HTMLAudioElement | null>(null);
  const speechGeneration = useRef(0);
  const requestKey = useRef<{ binding: string; key: string } | null>(null);
  const recorder = useRef<{
      context: AudioContext;
      stream: MediaStream;
      node: AudioWorkletNode;
      frames: Float32Array[];
      timer: number;
      lastSpeech: number;
      started: number;
      heard: boolean;
    } | null>(null),
    spokenEvents = useRef(new Set<string>()),
    voiceRequest = useRef(false);
  const isStaff = actor?.role === "operator";
  useEffect(() => {
    if (result)
      requestAnimationFrame(() =>
        progressCard.current?.scrollIntoView({
          block: "center",
          behavior: "smooth",
        }),
      );
  }, [result?.id]);
  async function refresh() {
    const data = await api<Workspace>("/api/v1/pharmacy/workspace");
    setWorkspace(data);
    return data;
  }
  useEffect(() => {
    api<{ mode: string }>("/api/v1/auth/config")
      .then((d) => setAuthMode(d.mode))
      .catch(() => setError("Sign-in is unavailable. Please reload."));
    api<{ actor: Actor; csrf_token: string }>("/api/v1/auth/me")
      .then((d) => {
        setCsrf(d.csrf_token);
        setActor(d.actor);
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (actor) {
      refresh().catch((e) => setError(e.message));
      api<{ available: boolean; synthesis_available: boolean }>(
        "/api/v1/pharmacy/voice",
      )
        .then((v) => {
          setVoiceAvailable(v.available);
          setNaturalVoiceAvailable(v.synthesis_available);
        })
        .catch(() => {});
    }
  }, [actor]);
  useEffect(() => {
    if (!actor) return;
    const timer = window.setInterval(() => {
      if (isStaff) refresh().catch(() => {});
      else if (result)
        api<Result>("/api/v1/pharmacy/requests/" + result.id)
          .then(setResult)
          .catch((e) => setError(e.message));
    }, 900);
    return () => clearInterval(timer);
  }, [actor, result?.id, isStaff]);
  useEffect(() => {
    if (!result) return;
    const key = result.id + ":" + result.state;
    if (spokenEvents.current.has(key)) return;
    let message = "";
    if (result.state === "ORDERED" && result.order)
      message = `Your family order is accepted at Asterfield ${result.order.facility.name}, ${result.order.facility.address}. The total is ${usd(result.order.amount_minor)}. The pharmacy will confirm when it is ready.`;
    else if (result.state === "READY_FOR_PICKUP" && result.order)
      message = `Your family order is ready for pickup at ${result.order.facility.name}. Payment of ${usd(result.order.amount_minor)} is confirmed.`;
    else if (
      [
        "BLOCKED",
        "NEEDS_INPUT",
        "BUDGET_EXCEEDED",
        "AWAITING_APPROVAL",
        "MODEL_UNAVAILABLE",
        "PICKED_UP",
        "CANCELED",
      ].includes(result.state)
    )
      message = result.message;
    if (message) {
      spokenEvents.current.add(key);
      setSpoken(message);
      if (voiceOn && voiceRequest.current && naturalVoiceAvailable) {
        void playStatus(result.id, result.state);
      }
      refresh().catch(() => {});
    }
  }, [result?.state, result?.id, voiceOn]);
  useEffect(
    () => () => {
      if (recorder.current) {
        recorder.current.stream.getTracks().forEach((t) => t.stop());
        recorder.current.context.close();
        clearInterval(recorder.current.timer);
      }
    },
    [],
  );
  function stopAudio() {
    speechGeneration.current += 1;
    playback.current?.pause();
    playback.current = null;
    setVoiceNotice("");
  }
  async function playStatus(identifier: string, state: string) {
    stopAudio();
    const generation = speechGeneration.current;
    setVoiceNotice("Preparing spoken update…");
    try {
      const response = await api<{ audio: string }>(
        `/api/v1/pharmacy/requests/${identifier}/speech`,
        {
          method: "POST",
          body: JSON.stringify({ state }),
        },
      );
      if (generation !== speechGeneration.current) return;
      const bytes = Uint8Array.from(atob(response.audio), (c) =>
        c.charCodeAt(0),
      );
      const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
      const audio = new Audio(url);
      playback.current = audio;
      const cleanup = () => {
        URL.revokeObjectURL(url);
        if (playback.current === audio) {
          playback.current = null;
          setVoiceNotice("");
        }
      };
      audio.onended = cleanup;
      audio.onerror = cleanup;
      audio.onpause = cleanup;
      try {
        await audio.play();
        setVoiceNotice("Speaking your update…");
      } catch {
        cleanup();
        setVoiceNotice("Tap Hear update to play the spoken confirmation.");
      }
    } catch {
      if (generation === speechGeneration.current)
        setVoiceNotice(
          "Spoken update unavailable. Your written order status is up to date.",
        );
    }
  }
  useEffect(() => {
    if (!actor || isStaff || !voiceOn) stopAudio();
    return () => {
      speechGeneration.current += 1;
      playback.current?.pause();
    };
  }, [actor?.user_id, isStaff, voiceOn]);
  async function login(persona: string) {
    try {
      setBusy(true);
      const d = await api<{ actor: Actor; csrf_token: string }>(
        "/api/v1/auth/demo",
        { method: "POST", body: JSON.stringify({ persona }) },
      );
      voiceRequest.current = false;
      setActor(d.actor);
      setCsrf(d.csrf_token);
      setResult(null);
      setView("pickup");
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function send(value = text, channel: "text" | "voice" = "text") {
    if (!value.trim()) return;
    stopAudio();
    setBusy(true);
    setError("");
    setSpoken("");
    voiceRequest.current = channel === "voice";
    try {
      const binding = JSON.stringify([value, channel]);
      if (requestKey.current?.binding !== binding)
        requestKey.current = { binding, key: crypto.randomUUID() };
      const d = await api<{ request_id: string }>("/api/v1/pharmacy/requests", {
        method: "POST",
        headers: { "Idempotency-Key": requestKey.current!.key },
        body: JSON.stringify({ text: value, channel }),
      });
      setResult(await api<Result>("/api/v1/pharmacy/requests/" + d.request_id));
      requestKey.current = null;
      setText("");
      setView("pickup");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function permission() {
    if (!workspace?.members.length) return;
    try {
      setBusy(true);
      const amount = Math.round(Number(limit) * 100);
      if (!Number.isFinite(amount) || amount <= 0)
        throw Error("Enter a valid spending limit.");
      await api("/api/v1/pharmacy/permissions", {
        method: "POST",
        body: JSON.stringify({
          members: workspace?.members
            .filter((m) => m.access_approved)
            .map((m) => m.alias),
          per_order_minor: amount,
          total_minor: amount * 3,
          max_orders: 3,
          valid_for_seconds: 86400,
        }),
      });
      setPermissionOpen(false);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function approve() {
    if (!result?.quote) return;
    try {
      setBusy(true);
      await api("/api/v1/pharmacy/requests/" + result.id + "/approval", {
        method: "POST",
        body: JSON.stringify({ quote_digest: result.quote.digest }),
      });
      setResult(await api<Result>("/api/v1/pharmacy/requests/" + result.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function progress(order: Order, action: string) {
    try {
      setBusy(true);
      await api("/api/v1/pharmacy/staff/orders/" + order.id, {
        method: "POST",
        body: JSON.stringify({
          action,
          clinical_review_confirmed: !!staffReview[order.id],
          pickup_code: codes[order.id] || null,
        }),
      });
      await refresh();
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function stopRecording() {
    const active = recorder.current;
    if (!active) return;
    recorder.current = null;
    clearInterval(active.timer);
    active.stream.getTracks().forEach((t) => t.stop());
    active.node.disconnect();
    await active.context.close();
    setRecording(false);
    setTranscribing(true);
    try {
      const blob = wav(active.frames);
      const d = await api<{ text: string }>(
        "/api/v1/pharmacy/voice/transcribe",
        {
          method: "POST",
          headers: { "Content-Type": "audio/wav" },
          body: blob,
        },
      );
      setText(d.text);
      setSpoken(`I heard: “${d.text}”`);
      await send(d.text, "voice");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setTranscribing(false);
    }
  }
  async function startVoice() {
    if (recording) {
      await stopRecording();
      return;
    }
    try {
      setError("");
      stopAudio();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      const context = new AudioContext({ sampleRate: 16000 });
      await context.audioWorklet.addModule("/family-recorder.js");
      const node = new AudioWorkletNode(context, "family-recorder");
      context.createMediaStreamSource(stream).connect(node);
      node.connect(context.destination);
      const active = {
        context,
        stream,
        node,
        frames: [] as Float32Array[],
        timer: 0,
        lastSpeech: performance.now(),
        started: performance.now(),
        heard: false,
      };
      recorder.current = active;
      node.port.onmessage = (e) => {
        if (recorder.current !== active) return;
        const chunk = new Float32Array(e.data);
        active.frames.push(chunk);
        const rms = Math.sqrt(
          chunk.reduce((s, x) => s + x * x, 0) / chunk.length,
        );
        if (rms > 0.012) {
          active.heard = true;
          active.lastSpeech = performance.now();
        }
      };
      active.timer = window.setInterval(() => {
        if (
          performance.now() - active.started > 44000 ||
          (active.heard && performance.now() - active.lastSpeech > 1900)
        )
          stopRecording();
      }, 100);
      setRecording(true);
      setSpoken(
        "Listening. Tell me whose regulars to pick up and your spending limit.",
      );
    } catch (e) {
      setError("Microphone unavailable. You can type the same request below.");
      setRecording(false);
    }
  }
  useEffect(() => {
    if (!permissionOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>(".ph-modal");
    const controls = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input,a[href],textarea",
        ) || [],
      );
    controls()[0]?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPermissionOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = controls(),
        first = items[0],
        last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [permissionOpen]);
  const grant = workspace?.permission,
    permissionActive =
      !!grant && !grant.revoked && grant.expires_at * 1000 > Date.now();
  if (!actor)
    return (
      <div className="pharmacy">
        <div className="ph-demo">
          A fictional pharmacy. Synthetic household records and payments.
        </div>
        <header className="ph-header">
          <Brand />
          <span className="ph-header-note">Care that fits into your day.</span>
        </header>
        <main className="ph-login">
          <div>
            <span className="ph-eyebrow">FAMILY PICKUP, SIMPLIFIED</span>
            <h1>
              One stop.
              <br />
              <em>Everyone taken care of.</em>
            </h1>
            <p>
              Your family's saved essentials, one nearby pharmacy and a pickup
              that works around your day.
            </p>
            <div className="ph-login-actions">
              {authMode === "oidc" ? (
                <button
                  className="ph-primary"
                  onClick={() => location.assign("/api/v1/auth/login")}
                >
                  Sign in to your pharmacy <Symbol kind="arrow" />
                </button>
              ) : authMode === "demo" ? (
                <>
                  <button
                    className="ph-primary"
                    onClick={() => login("alex")}
                    disabled={busy}
                  >
                    Explore family pickup <Symbol kind="arrow" />
                  </button>
                  <button
                    className="ph-link"
                    onClick={() => login("operator")}
                    disabled={busy}
                  >
                    Open the pharmacy desk
                  </button>
                </>
              ) : (
                <p role="status">Loading sign-in…</p>
              )}
            </div>
            {error && (
              <p role="alert" className="ph-error">
                {error}
              </p>
            )}
            <small>
              Existing prescriptions stay subject to pharmacy review. This
              demonstration does not prescribe, dispense real medication or
              charge real money.
            </small>
          </div>
          <div className="ph-login-illustration">
            <div className="ph-illustration-label">
              YOUR AFTER-WORK ERRAND, HANDLED
            </div>
            <div className="ph-bag">
              <span>A.</span>
              <strong>asterfield</strong>
              <small>YOUR NEIGHBORHOOD PHARMACY</small>
            </div>
            <div className="ph-float ph-float-one">
              <Symbol kind="shield" />
              <span>Within your permission</span>
            </div>
            <div className="ph-float ph-float-two">
              <Symbol kind="pin" />
              <span>One family. One pickup.</span>
            </div>
          </div>
        </main>
      </div>
    );
  return (
    <div className="pharmacy">
      <div className="ph-demo">
        Asterfield is fictional · synthetic pharmacy records, locations and
        payments{" "}
        <span>
          {workspace?.model_provider === "codex"
            ? "Local AI assistant"
            : "Rule-based development demo"}
        </span>
      </div>
      <header className="ph-header">
        <Brand />
        <nav aria-label="Pharmacy navigation">
          {!isStaff &&
            [
              ["pickup", "Family pickup"],
              ["household", "My household"],
              ["orders", "Pickup history"],
            ].map(([id, title]) => (
              <button
                key={id}
                aria-current={view === id ? "page" : undefined}
                className={view === id ? "active" : ""}
                onClick={() => setView(id)}
              >
                {title}
              </button>
            ))}
          {isStaff && <strong className="ph-desk-label">Pharmacy desk</strong>}
        </nav>
        <div className="ph-account">
          <span className="ph-avatar">{isStaff ? "PT" : "AR"}</span>
          <span>
            {isStaff ? "Pharmacy team" : "Alex Rivera"}
            <small>{isStaff ? "Cedar Square" : "Family organizer"}</small>
          </span>
          <button
            className="ph-signout"
            onClick={async () => {
              await api("/api/v1/auth/logout", { method: "POST" });
              setActor(null);
              setWorkspace(null);
              setResult(null);
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      {error && (
        <div className="ph-global-error" role="alert">
          {error}
          <button onClick={() => setError("")} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}
      {isStaff ? (
        <main className="ph-main">
          <div className="ph-page-title">
            <div>
              <span className="ph-eyebrow">
                CEDAR SQUARE · PHARMACY OPERATIONS
              </span>
              <h1>
                A clear queue.
                <br />
                <em>A considered handoff.</em>
              </h1>
            </div>
            <span className="ph-tag">Staff workspace</span>
          </div>
          <div className="ph-staff-metrics">
            <div>
              <strong>
                {workspace?.orders?.filter((o) => o.state === "AWAITING_REVIEW")
                  .length || 0}
              </strong>
              <span>Awaiting review</span>
            </div>
            <div>
              <strong>
                {workspace?.orders?.filter(
                  (o) => o.state === "READY_FOR_PICKUP",
                ).length || 0}
              </strong>
              <span>Ready for pickup</span>
            </div>
            <div>
              <strong>
                {workspace?.orders?.filter((o) => o.state === "PICKED_UP")
                  .length || 0}
              </strong>
              <span>Collected</span>
            </div>
          </div>
          <section className="ph-order-queue" aria-label="Pharmacy order queue">
            {workspace?.orders?.length ? (
              workspace.orders.map((order) => (
                <article className="ph-staff-order" key={order.id}>
                  <header>
                    <div>
                      <span className="ph-eyebrow">{order.reference}</span>
                      <h2>Rivera family pickup</h2>
                    </div>
                    <span
                      className={
                        "ph-status " +
                        (order.state === "READY_FOR_PICKUP" ||
                        order.state === "PICKED_UP"
                          ? "good"
                          : "")
                      }
                    >
                      {nice(order.state)}
                    </span>
                  </header>
                  <Basket terms={order.terms} />
                  <div className="ph-source-states">
                    <span>Payment: {nice(order.payment_state)}</span>
                    <span>Handoff: {nice(order.fulfillment_state)}</span>
                  </div>
                  {order.state === "AWAITING_REVIEW" && (
                    <div className="ph-staff-controls">
                      <label className="ph-review-check">
                        <input
                          type="checkbox"
                          checked={!!staffReview[order.id]}
                          onChange={(e) =>
                            setStaffReview({
                              ...staffReview,
                              [order.id]: e.target.checked,
                            })
                          }
                        />
                        I reviewed eligibility and prepared every saved item.
                      </label>
                      <button
                        className="ph-primary"
                        disabled={busy || !staffReview[order.id]}
                        onClick={() => progress(order, "ready")}
                      >
                        Confirm prepared & ready
                      </button>
                      <button
                        className="ph-link danger"
                        onClick={() => progress(order, "reject")}
                        disabled={busy}
                      >
                        Unable to prepare · cancel authorization
                      </button>
                    </div>
                  )}
                  {order.state === "READY_FOR_PICKUP" && (
                    <div className="ph-collect">
                      <label>
                        Customer pickup code
                        <input
                          aria-label={"Pickup code for " + order.reference}
                          value={codes[order.id] || ""}
                          onChange={(e) =>
                            setCodes({ ...codes, [order.id]: e.target.value })
                          }
                          placeholder="8-character code"
                          autoComplete="off"
                        />
                      </label>
                      <button
                        className="ph-primary"
                        disabled={busy}
                        onClick={() => progress(order, "collect")}
                      >
                        Confirm collected
                      </button>
                    </div>
                  )}
                </article>
              ))
            ) : (
              <div className="ph-empty">
                <Symbol kind="pill" size={34} />
                <h2>Your queue is clear.</h2>
                <p>
                  New family pickup orders appear here after payment
                  authorization is confirmed.
                </p>
              </div>
            )}
          </section>
        </main>
      ) : (
        <main className="ph-main">
          {view === "pickup" ? (
            <>
              <div className="ph-page-title">
                <div>
                  <span className="ph-eyebrow">YOUR FAMILY, IN GOOD ORDER</span>
                  <h1>
                    One stop.
                    <br />
                    <em>Everyone taken care of.</em>
                  </h1>
                  <p>
                    We'll bring your family's saved regulars together at a
                    nearby pharmacy.
                  </p>
                </div>
                <div className="ph-home">
                  <Symbol kind="pin" />
                  <div>
                    <small>Finding pickup near home</small>
                    <strong>{workspace?.home}</strong>
                    <span>Fictional locations · approximate distance</span>
                  </div>
                </div>
              </div>
              <div className="ph-grid">
                <div>
                  <section className="ph-assistant">
                    <div className="ph-section-label">
                      <span className="ph-live-dot" />
                      YOUR PICKUP ASSISTANT{" "}
                      <label className="ph-speech-toggle">
                        <input
                          type="checkbox"
                          checked={voiceOn}
                          disabled={!naturalVoiceAvailable}
                          onChange={(e) => setVoiceOn(e.target.checked)}
                        />
                        Natural spoken updates
                      </label>
                    </div>
                    <h2>Tell us what to take care of.</h2>
                    <p>
                      “Order the regular medicines for my family, nearest home.
                      You can pay up to fifty dollars.”
                    </p>
                    <div className="ph-voice-row">
                      <button
                        className={"ph-mic " + (recording ? "recording" : "")}
                        onClick={startVoice}
                        disabled={!voiceAvailable || busy || transcribing}
                        aria-label={
                          recording
                            ? "Finish voice request"
                            : "Start voice request"
                        }
                      >
                        <Symbol kind="mic" size={26} />
                      </button>
                      <div>
                        <strong>
                          {recording
                            ? "Listening…"
                            : transcribing
                              ? "Understanding your recording…"
                              : voiceAvailable
                                ? "Just ask. We’ll handle the details."
                                : "Voice setup is not available on this device."}
                        </strong>
                        <small>
                          {recording
                            ? "Pause when you’re finished, or press the microphone."
                            : "Your saved list. Your location. Your spending limit."}
                        </small>
                      </div>
                    </div>
                    <label className="ph-sr" htmlFor="family-request">
                      Family pickup request
                    </label>
                    <textarea
                      id="family-request"
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      placeholder="Or type your family pickup request…"
                      rows={3}
                    />
                    <div className="ph-assistant-footer">
                      <button
                        className="ph-example"
                        onClick={() =>
                          setText(
                            "Order the regular medicines for my dad, mom, sister and myself nearest home, up to $50",
                          )
                        }
                      >
                        Try a family pickup request
                      </button>
                      <button
                        className="ph-primary"
                        disabled={
                          busy || transcribing || recording || !text.trim()
                        }
                        onClick={() => send()}
                      >
                        {busy ? "Starting…" : "Arrange pickup"}
                        <Symbol kind="arrow" size={18} />
                      </button>
                    </div>
                    {(recording || transcribing || (spoken && !result)) && (
                      <div
                        className="ph-voice-feedback"
                        role="status"
                        aria-live="polite"
                      >
                        {transcribing ? "Transcribing locally…" : spoken}
                      </div>
                    )}
                  </section>
                  <section className="ph-regulars">
                    <div className="ph-section-title">
                      <h2>Your family’s regulars</h2>
                      <span>Saved items, never guessed</span>
                    </div>
                    <div className="ph-member-grid">
                      {workspace?.members.map((member) => (
                        <MemberCard member={member} key={member.id} />
                      ))}
                    </div>
                  </section>
                  {result && (
                    <section
                      className="ph-request-progress"
                      ref={progressCard}
                      aria-label="Current pickup request"
                    >
                      <div className="ph-section-title">
                        <h2>
                          {result.order
                            ? result.order.reference
                            : "Your pickup request"}
                        </h2>
                        <span
                          className={
                            "ph-status " +
                            (["READY_FOR_PICKUP", "PICKED_UP"].includes(
                              result.state,
                            )
                              ? "good"
                              : "")
                          }
                        >
                          {nice(result.state)}
                        </span>
                      </div>
                      <p className="ph-original-request">“{result.text}”</p>
                      {naturalVoiceAvailable &&
                        [
                          "ORDERED",
                          "READY_FOR_PICKUP",
                          "PICKED_UP",
                          "BLOCKED",
                          "NEEDS_INPUT",
                          "BUDGET_EXCEEDED",
                          "AWAITING_APPROVAL",
                          "MODEL_UNAVAILABLE",
                          "CANCELED",
                          "NEEDS_REVIEW",
                        ].includes(result.state) && (
                          <button
                            className="ph-link"
                            onClick={() => playStatus(result.id, result.state)}
                          >
                            Hear update
                          </button>
                        )}
                      {voiceNotice && (
                        <p className="ph-voice-notice" role="status">
                          {voiceNotice}
                        </p>
                      )}
                      <div
                        role="status"
                        aria-live="polite"
                        className="ph-result-message"
                      >
                        {result.message}
                      </div>
                      {result.order?.pickup_code && (
                        <div className="ph-pickup-pass">
                          <div>
                            <span className="ph-eyebrow">YOUR PICKUP PASS</span>
                            <strong>{result.order.pickup_code}</strong>
                            <small>
                              Show this code to the pharmacy team at collection.
                            </small>
                          </div>
                          <Symbol kind="check" size={35} />
                        </div>
                      )}
                      <div className="ph-steps">
                        {[
                          [
                            "pharmacy.intent_understood",
                            "Understood your request",
                          ],
                          [
                            "pharmacy.quote_prepared",
                            "Checked family access, items and locations",
                          ],
                          [
                            "pharmacy.order_accepted",
                            "Verified your spending permission",
                          ],
                          [
                            "pharmacy.source_confirmed",
                            "Checked the original payment outcome",
                          ],
                        ].map(([event, title]) => (
                          <div
                            key={event}
                            className={
                              result.events.some((e) => e.type === event)
                                ? "done"
                                : ""
                            }
                          >
                            <span>
                              <Symbol kind="check" size={12} />
                            </span>
                            {title}
                          </div>
                        ))}
                      </div>
                    </section>
                  )}
                </div>
                <aside className="ph-side">
                  <section className="ph-permission-card">
                    <div className="ph-section-title">
                      <Symbol kind="shield" />
                      <span
                        className={
                          "ph-status " + (permissionActive ? "good" : "")
                        }
                      >
                        {permissionActive
                          ? "Permission active"
                          : "Your control"}
                      </span>
                    </div>
                    <h2>
                      A little permission.
                      <br />A lot less to do.
                    </h2>
                    {permissionActive ? (
                      <>
                        <div className="ph-limit">
                          {usd(grant!.per_order_minor)}
                          <span>per family pickup</span>
                        </div>
                        <p>
                          Only approved family members and their saved items.{" "}
                          {usd(
                            grant!.total_minor -
                              grant!.held_minor -
                              grant!.spent_minor,
                          )}{" "}
                          remains in the total allowance.
                        </p>
                        <button
                          className="ph-link"
                          onClick={async () => {
                            await api(
                              "/api/v1/pharmacy/permissions/" + grant!.id,
                              { method: "DELETE" },
                            );
                            await refresh();
                          }}
                        >
                          Revoke permission
                        </button>
                      </>
                    ) : (
                      <>
                        <p>
                          Set a spending permission before you head out. The
                          assistant can order only the saved items you allow.
                        </p>
                        <button
                          className="ph-secondary"
                          disabled={!workspace?.members.length || busy}
                          onClick={() => setPermissionOpen(true)}
                        >
                          Set pickup permission
                        </button>
                      </>
                    )}
                  </section>
                  {result?.quote ? (
                    <section className="ph-basket-card">
                      <span className="ph-eyebrow">
                        YOUR COMPLETE FAMILY BASKET
                      </span>
                      <Basket terms={result.quote.terms} />
                      <div className="ph-selected-place">
                        <Symbol kind="pin" />
                        <div>
                          <strong>
                            Asterfield {result.quote.terms.facility.name}
                          </strong>
                          <span>{result.quote.terms.facility.address}</span>
                          <small>
                            Nearest open location with the complete basket
                          </small>
                        </div>
                      </div>
                      {result.state === "AWAITING_APPROVAL" && (
                        <button
                          className="ph-primary"
                          onClick={approve}
                          disabled={busy}
                        >
                          Approve this exact pickup ·{" "}
                          {usd(result.quote.terms.amount_minor)}
                        </button>
                      )}
                      {result.order && (
                        <div className="ph-basket-source">
                          <span>
                            Payment{" "}
                            <strong>{nice(result.order.payment_state)}</strong>
                          </span>
                          <span>
                            Pickup{" "}
                            <strong>
                              {nice(result.order.fulfillment_state)}
                            </strong>
                          </span>
                        </div>
                      )}
                      <small className="ph-fine">
                        All demo charges included. Existing prescriptions still
                        require pharmacy preparation and review.
                      </small>
                    </section>
                  ) : (
                    <section className="ph-location-card">
                      <div className="ph-section-title">
                        <h2>Close to home.</h2>
                        <Symbol kind="pin" />
                      </div>
                      <div className="ph-map" aria-hidden="true">
                        <div className="ph-map-road r1" />
                        <div className="ph-map-road r2" />
                        <div className="ph-map-road r3" />
                        <span className="ph-map-home">⌂</span>
                        <span className="ph-map-dot m1" />
                        <span className="ph-map-dot m2" />
                        <span className="ph-map-dot m3" />
                        <small>SYNTHETIC LOCATION DIAGRAM</small>
                      </div>
                      {workspace?.facilities
                        .slice()
                        .sort(
                          (a, b) =>
                            (a.distance_miles || 0) - (b.distance_miles || 0),
                        )
                        .map((place) => (
                          <div className="ph-location-row" key={place.id}>
                            <span>{place.name}</span>
                            <strong>
                              {place.distance_miles?.toFixed(1)} mi
                            </strong>
                          </div>
                        ))}
                      <p className="ph-fine">
                        We check hours and the complete basket before choosing a
                        location. No live travel-time estimate.
                      </p>
                    </section>
                  )}
                </aside>
              </div>
            </>
          ) : view === "household" ? (
            <>
              <div className="ph-page-title">
                <div>
                  <span className="ph-eyebrow">PEOPLE BEFORE TASKS</span>
                  <h1>
                    Your household.
                    <br />
                    <em>Their permission.</em>
                  </h1>
                  <p>
                    Adult family access is approved separately from purchasing
                    permission.
                  </p>
                </div>
              </div>
              <div className="ph-member-grid household">
                {workspace?.members.map((member) => (
                  <MemberCard key={member.id} member={member} />
                ))}
              </div>
            </>
          ) : (
            <>
              <div className="ph-page-title">
                <div>
                  <span className="ph-eyebrow">A RECORD YOU CAN RELY ON</span>
                  <h1>
                    Every family pickup.
                    <br />
                    <em>One clear place.</em>
                  </h1>
                </div>
              </div>
              <section className="ph-history">
                {workspace?.requests.length ? (
                  workspace.requests.map((item) => (
                    <button
                      key={item.id}
                      onClick={async () => {
                        setResult(
                          await api<Result>(
                            "/api/v1/pharmacy/requests/" + item.id,
                          ),
                        );
                        setView("pickup");
                      }}
                    >
                      <div>
                        <strong>{item.text}</strong>
                        <span>{item.message}</span>
                      </div>
                      <span className="ph-status">{nice(item.state)}</span>
                      <Symbol kind="arrow" />
                    </button>
                  ))
                ) : (
                  <div className="ph-empty">
                    <h2>No pickup requests yet.</h2>
                    <p>
                      Your orders and any blocked requests will appear here.
                    </p>
                  </div>
                )}
              </section>
            </>
          )}
        </main>
      )}
      <footer className="ph-footer">
        <Brand />
        <span>
          Fictional pharmacy · working synthetic demonstration · no real charges
        </span>
      </footer>
      {permissionOpen && (
        <div className="ph-modal-backdrop">
          <section
            className="ph-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="permission-title"
          >
            <button
              className="ph-close"
              onClick={() => setPermissionOpen(false)}
              aria-label="Close permission setup"
            >
              ×
            </button>
            <Symbol kind="shield" size={30} />
            <span className="ph-eyebrow">SET THIS UP BEFORE YOUR ERRAND</span>
            <h2 id="permission-title">
              Keep the control.
              <br />
              Hand off the routine.
            </h2>
            <p>
              Allow the assistant to request only these approved family members’
              saved items at Asterfield locations.
            </p>
            <div className="ph-permission-people">
              {workspace?.members
                .filter((m) => m.access_approved)
                .map((m) => (
                  <span key={m.id}>
                    <Symbol kind="check" size={14} />
                    {m.relationship}
                  </span>
                ))}
            </div>
            <label className="ph-money-input">
              Maximum per pickup ($)
              <input
                type="number"
                min="1"
                max="1000"
                step="0.01"
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
              />
            </label>
            <p className="ph-fine">
              Valid for 24 hours, up to 3 orders and{" "}
              {usd(Math.round((Number(limit) || 0) * 300))} total. No
              substitutions or new prescriptions. A lower limit in your request
              still applies. You can revoke this permission.
            </p>
            <button
              className="ph-primary"
              onClick={permission}
              disabled={busy || !workspace?.members.length}
            >
              Allow these saved items <Symbol kind="arrow" />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
function Brand() {
  return (
    <a href="/" className="ph-brand" aria-label="Asterfield Pharmacy home">
      <span>A.</span>
      <div>
        asterfield<small>PHARMACY</small>
      </div>
    </a>
  );
}
function MemberCard({ member }: { member: Member }) {
  return (
    <article className="ph-member">
      <div className="ph-member-heading">
        <span className={"ph-person-avatar " + member.alias}>
          {member.name
            .split(" ")
            .map((s) => s[0])
            .join("")}
        </span>
        <span>
          <strong>{member.relationship}</strong>
          <small>{member.name}</small>
        </span>
        <Symbol kind="pill" size={19} />
      </div>
      {member.regular ? (
        <>
          <h3>{member.regular.name}</h3>
          <p>{member.regular.package}</p>
          <div className="ph-member-bottom">
            <span>
              {member.regular.kind === "RX"
                ? "Saved prescription"
                : "Saved OTC item"}
            </span>
            <strong>{usd(member.regular.price_minor)}</strong>
          </div>
          <div className="ph-access">
            <Symbol kind="check" size={12} />{" "}
            {member.alias === "self"
              ? "Your saved record"
              : "Family access approved"}
          </div>
        </>
      ) : (
        <p>
          Adult family authorization is needed before viewing or ordering saved
          items.
        </p>
      )}
    </article>
  );
}
function Basket({ terms }: { terms: Terms }) {
  return (
    <div className="ph-basket">
      <div className="ph-basket-lines">
        {terms.lines.map((line, index) => (
          <div key={index}>
            <span>
              <strong>{line.name}</strong>
              <small>
                {line.member_name} · {line.quantity} saved package
              </small>
            </span>
            <strong>{usd(line.amount_minor)}</strong>
          </div>
        ))}
      </div>
      <div className="ph-basket-total">
        <span>Family total</span>
        <strong>{usd(terms.amount_minor)}</strong>
      </div>
      <div className="ph-basket-limit">
        Requested limit {terms.budget_comparison === "lt" ? "under" : "up to"}{" "}
        {usd(terms.requested_limit_minor)}
      </div>
    </div>
  );
}
function wav(chunks: Float32Array[]) {
  const count = chunks.reduce((sum, chunk) => sum + chunk.length, 0),
    buffer = new ArrayBuffer(44 + count * 2),
    view = new DataView(buffer);
  const text = (at: number, value: string) => {
    for (let i = 0; i < value.length; i++)
      view.setUint8(at + i, value.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + count * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, count * 2, true);
  let offset = 44;
  for (const chunk of chunks)
    for (const sample of chunk) {
      view.setInt16(offset, Math.max(-1, Math.min(1, sample)) * 32767, true);
      offset += 2;
    }
  return new Blob([buffer], { type: "audio/wav" });
}
