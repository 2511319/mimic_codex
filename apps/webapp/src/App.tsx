import { useEffect, useState } from "react";

import { fetchHealth } from "./api/client";

type HealthState = {
  status: "idle" | "loading" | "ready" | "error";
  message?: string;
};

function App(): JSX.Element {
  const [health, setHealth] = useState<HealthState>({ status: "idle" });

  useEffect(() => {
    setHealth({ status: "loading" });
    fetchHealth()
      .then((payload) => {
        setHealth({ status: "ready", message: `API ${payload.apiVersion}` });
      })
      .catch(() => {
        setHealth({ status: "error", message: "API недоступно" });
      });
  }, []);

  return (
    <main className="app">
      <h1>RPG-Bot Mini App</h1>
      <p>
        Состояние сервера: <strong>{health.status}</strong>
      </p>
      {health.message ? <p>{health.message}</p> : null}
    </main>
  );
}

export default App;
