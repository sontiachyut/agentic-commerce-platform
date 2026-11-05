import type { Session } from "./types";
import { Icon, Badge } from "./ui";
export function PurchaseActivity({
  session,
  onRetry,
}: {
  session: Session;
  onRetry: () => void;
}) {
  const quote = session.quote,
    execution = session.execution;
  const waiting = ["QUEUED", "EXECUTING"].includes(session.state);
  return (
    <section className="card purchase-card" aria-live="polite">
      <div className="section-heading">
        <div className="assistant-avatar">
          <Icon name="spark" size={18} />
        </div>
        <div>
          <h2>Your purchase</h2>
          <small>
            {new Date(
              session.events[0]?.created_at * 1000 || Date.now(),
            ).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </small>
        </div>
        <Badge state={session.state} />
      </div>
      <div className="user-request">“{session.original_request}”</div>
      <p className="purchase-message">{session.message}</p>
      <div className="progress-track">
        {["Request", "Selection", "Approval", "Payment", "Delivery"].map(
          (step, i) => {
            const done =
              i === 0 ||
              (i === 1 && !!quote) ||
              (i === 2 && !!execution) ||
              (i === 3 &&
                ["AUTHORIZED", "CAPTURED", "REFUNDED", "CANCELED"].includes(
                  execution?.payment_state || "",
                )) ||
              (i === 4 && execution?.fulfillment_state === "DISPENSED");
            return (
              <div key={step} className={done ? "step done" : "step"}>
                <span>{done ? <Icon name="check" size={13} /> : i + 1}</span>
                <small>{step}</small>
              </div>
            );
          },
        )}
      </div>
      {waiting && (
        <div className="working">
          <span className="pulse" />
          {session.state === "QUEUED"
            ? "Understanding your request and checking the catalog…"
            : "Checking the original payment and delivery records…"}
        </div>
      )}
      {execution && (
        <div className="outcome-grid">
          <div>
            <small>PAYMENT</small>
            <Badge state={execution.payment_state} />
          </div>
          <div>
            <small>DELIVERY</small>
            <Badge state={execution.fulfillment_state} />
          </div>
          <div>
            <small>COMPENSATION</small>
            <Badge state={execution.compensation_state} />
          </div>
        </div>
      )}
      {session.state === "MODEL_UNAVAILABLE" && (
        <button className="secondary" onClick={onRetry}>
          Retry model connection
        </button>
      )}
      <details className="trace">
        <summary>
          View purchase activity <span>{session.events.length} events</span>
        </summary>
        <ol>
          {session.events.map((event) => (
            <li key={event.id}>
              <span className="event-dot" />
              <div>
                <strong>
                  {event.type.replaceAll(".", " · ").replaceAll("_", " ")}
                </strong>
                <small>
                  {new Date(event.created_at * 1000).toLocaleTimeString()}
                </small>
                <code>{JSON.stringify(event.data)}</code>
              </div>
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
