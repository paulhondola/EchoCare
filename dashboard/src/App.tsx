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
    <main>
      <header>
        <h1>Sentinela DAS</h1>
        <span className="health">API: {health}</span>
      </header>
      <IncidentBoard />
    </main>
  );
}
