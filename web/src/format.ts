export const money = (cents: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    cents / 100,
  );
export const label = (value: string) =>
  value.toLowerCase().replaceAll("_", " ");
