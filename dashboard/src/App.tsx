import { useEffect, useState } from "react";
import IncidentBoard from "./IncidentBoard";

const API_URL = import.meta.env.VITE_API_URL;

export default function App() {
  const [health, setHealth] = useState("…");

  // ponytail: a cross-origin call to /api/health proves the API, the database and CORS in one request
  useEffect(() => {
    fetch(`${API_URL}/api/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((h) => setHealth(`${h.status} (${h.env})`))
      .catch((e) => setHealth(`unreachable: ${e}`));
  }, []);

  return (
    <main className="mx-auto max-w-7xl p-4">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-base-300 pb-2">
        <h1 className="text-2xl font-bold">Sentinela DAS</h1>
        <span className="text-sm text-base-content/60">API: {health}</span>
      </header>
      <IncidentBoard />
    </main>
  );
}
