import { useEffect, useState } from "react";

export function useAnalysisRefresh(week) {
  const [job, setJob] = useState({ state: "idle", message: "" });
  const [busy, setBusy] = useState(false);
  const running = job.state === "running";
  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const response = await fetch("/api/refresh", { cache: "no-store" });
        if (!response.ok) return;
        const next = await response.json();
        if (!active) return;
        setJob(next);
        if (running && next.state !== "running") window.dispatchEvent(new Event("nfl:refresh-scores"));
      } catch { /* The score feed keeps its own retained-state error. */ }
    };
    void check();
    const timer = setInterval(check, running ? 2500 : 30000);
    return () => { active = false; clearInterval(timer); };
  }, [week, running]);
  const refresh = async () => {
    if (busy || running) return;
    setBusy(true);
    window.dispatchEvent(new Event("nfl:refresh-scores"));
    try {
      const response = await fetch("/api/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ week }) });
      if (!response.ok) throw new Error("Scores and lines requested. Full model refresh requires the local analysis server.");
      setJob(await response.json());
    } catch (error) { setJob({ state: "blocked", message: error.message }); }
    finally { setBusy(false); }
  };
  return { job, refresh, busy: busy || running };
}
