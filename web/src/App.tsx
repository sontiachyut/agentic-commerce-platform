import { useEffect, useState } from "react";
import RetailApp from "./RetailApp";
import PharmacyApp from "./PharmacyApp";
export default function App() {
  const [mode, setMode] = useState("");
  useEffect(() => {
    fetch("/api/v1/product")
      .then((r) => r.json())
      .then((p) => setMode(p.mode))
      .catch(() => setMode("error"));
  }, []);
  return mode === "retail" ? (
    <RetailApp />
  ) : mode === "pharmacy" ? (
    <PharmacyApp />
  ) : (
    <main className="boot-screen" role="status">
      {mode === "error"
        ? "Could not connect. Please reload."
        : "Opening your pharmacy…"}
    </main>
  );
}
