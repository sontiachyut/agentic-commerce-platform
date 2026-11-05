import type { Product } from "./types";
import { Icon } from "./ui";
import { money } from "./format";
export function Catalog({
  catalog,
  onSelect,
}: {
  catalog: Product[];
  onSelect: (text: string) => void;
}) {
  return (
    <section className="catalog-section">
      <div className="section-heading">
        <h2>At this kiosk</h2>
        <span className="muted small">Live availability</span>
      </div>
      <div className="catalog-grid">
        {catalog.map((product) => (
          <button
            className="product-card"
            key={product.id}
            onClick={() =>
              onSelect(
                `Find ${product.name} under ${money(product.price_minor + 50)} at Kiosk A`,
              )
            }
          >
            <div className={`product-art ${product.category}`}>
              <Icon
                name={product.category === "drink" ? "box" : "bag"}
                size={30}
              />
              <span>
                {product.category === "drink"
                  ? "REFRESH"
                  : product.category === "protein-bar"
                    ? "PROTEIN"
                    : "PANTRY"}
              </span>
            </div>
            <strong>{product.name}</strong>
            <div>
              <span>{money(product.price_minor)}</span>
              <small>
                {product.available > 0
                  ? `${product.available} available`
                  : "Unavailable"}
              </small>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
