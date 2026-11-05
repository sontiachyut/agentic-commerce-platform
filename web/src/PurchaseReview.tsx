import type { Session } from "./types";
import { Icon } from "./ui";
import { money } from "./format";
export function PurchaseReview({
  session,
  now,
  busy,
  fault,
  onApprove,
  onFaultChange,
}: {
  session: Session | null;
  now: number;
  busy: boolean;
  fault: string;
  onApprove: () => void;
  onFaultChange: (value: string) => void;
}) {
  const quote = session?.quote,
    execution = session?.execution;
  const expired = !!quote && quote.expires_at * 1000 <= now;
  return (
    <aside className="review-column">
      <section className="card review-card">
        <div className="section-heading">
          <h2>Purchase review</h2>
          <Icon name="shield" size={18} />
        </div>
        {quote ? (
          <>
            <div className="review-product">
              <div className="product-thumb">
                <Icon name="bag" size={25} />
              </div>
              <div>
                <strong>{quote.product_name}</strong>
                <small>Kiosk A · Quantity 1</small>
              </div>
            </div>
            <div className="receipt">
              <div>
                <span>Item</span>
                <strong>{money(quote.amount_minor)}</strong>
              </div>
              <div>
                <span>Additional charges</span>
                <strong>{money(0)}</strong>
              </div>
              <div className="total">
                <strong>Total</strong>
                <strong>{money(quote.amount_minor)}</strong>
              </div>
            </div>
            {!execution && (
              <>
                <div className="approval-note">
                  <Icon name="shield" size={17} />
                  <p>
                    Approval applies to this exact item and total. A price
                    change requires a new approval.
                  </p>
                </div>
                <button
                  className="approve-button"
                  onClick={onApprove}
                  disabled={
                    busy || expired || session?.state !== "AWAITING_APPROVAL"
                  }
                >
                  <Icon name="check" size={18} />
                  {expired
                    ? "Quote expired"
                    : busy
                      ? "Confirming…"
                      : `Approve & purchase · ${money(quote.amount_minor)}`}
                </button>
                <p className="fine-print center">
                  {expired
                    ? "Start a new request for current terms."
                    : `Quote expires in ${Math.max(0, Math.ceil((quote.expires_at * 1000 - now) / 1000))} seconds.`}
                </p>
              </>
            )}
            {execution && (
              <div
                className={`receipt-confirmation ${execution.outcome.success ? "success" : ""}`}
              >
                <Icon name={execution.outcome.success ? "check" : "clock"} />
                <strong>
                  {execution.outcome.success
                    ? "Payment & delivery confirmed"
                    : "Follow the status in your purchase"}
                </strong>
                <small>Order {execution.order_id.slice(0, 8)}</small>
              </div>
            )}
          </>
        ) : (
          <div className="review-empty">
            <div className="empty-icon">
              <Icon name="bag" size={30} />
            </div>
            <h3>You’re in control.</h3>
            <p>
              Once an item is selected, you’ll see its exact details here before
              approving.
            </p>
          </div>
        )}
        <div className="review-footer">
          <span className="live-dot" />
          Synthetic payments only
        </div>
      </section>
      <section className="note-card">
        <p className="eyebrow">DESIGNED TO FOLLOW THROUGH</p>
        <h3>Pending means pending.</h3>
        <p>
          A lost response never becomes a second purchase. We check the original
          transaction and show what is confirmed.
        </p>
      </section>
      <details className="lab card">
        <summary>
          <Icon name="settings" size={16} />
          Failure lab
        </summary>
        <p className="fine-print">
          Choose a synthetic failure for the next approved purchase.
        </p>
        <label htmlFor="fault-profile" className="small">
          Scenario
        </label>
        <select
          id="fault-profile"
          value={fault}
          onChange={(e) => onFaultChange(e.target.value)}
        >
          {[
            ["none", "Normal checkout"],
            ["payment_response_lost", "Payment succeeds, response lost"],
            ["dispense_response_lost", "Item delivered, response lost"],
            ["capture_response_lost", "Capture succeeds, response lost"],
            ["dispense_failed", "Delivery fails → cancel authorization"],
            ["captured_dispense_failed", "Captured payment → refund"],
            ["compensation_response_lost", "Cancellation response lost"],
            ["payment_declined", "Payment declined"],
            ["capture_declined", "Delivery succeeds, capture fails"],
            ["source_unavailable", "Payment source unavailable"],
          ].map(([value, title]) => (
            <option key={value} value={value}>
              {title}
            </option>
          ))}
        </select>
      </details>
    </aside>
  );
}
