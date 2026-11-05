import { label } from "./format";
const iconPaths: Record<string, string> = {
  bag: "M6 7h12l1 13H5L6 7Zm3 0V5a3 3 0 0 1 6 0v2",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  shield: "M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Zm-4 9 3 3 5-6",
  clock: "M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  check: "m5 12 4 4L19 6",
  settings: "M4 7h16M4 17h16M8 4v6M16 14v6",
  box: "m12 3 9 5v9l-9 5-9-5V8l9-5Zm0 9v10M3 8l9 4 9-4",
  exit: "M9 4H4v16h5m5-12 4 4-4 4m-6-4h10",
};
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
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
      <path d={iconPaths[name] || iconPaths.box} />
    </svg>
  );
}
export function Badge({ state }: { state: string }) {
  return (
    <span
      className={`badge ${["COMPLETED", "CAPTURED", "DISPENSED", "CONFIRMED"].includes(state) ? "good" : ["RECOVERY_REQUIRED", "POLICY_DENIED", "MODEL_UNAVAILABLE", "DECLINED", "CANCELED"].includes(state) ? "warning" : ""}`}
    >
      {label(state)}
    </span>
  );
}
