import { useEffect, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { api } from "../api";

type Operations = {
  checked_at: string;
  worker: { status: string; last_seen_at: string | null };
  jobs: {
    queued: number;
    running: number;
    failed_24h: number;
    completed_24h: number;
    expired_leases: number;
    oldest_queued_at: string | null;
    duration_p95_seconds: number | null;
  };
  monitoring: { enabled: number; overdue: number };
};

export default function OperationsPanel() {
  const [value, setValue] = useState<Operations | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      if (document.visibilityState === "hidden") return;
      try {
        const result = await api<Operations>("/workspace/operations", {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setValue(result);
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Health check unavailable.");
      }
    };
    void load();
    const interval = setInterval(load, 30_000);
    document.addEventListener("visibilitychange", load);
    return () => {
      controller.abort();
      clearInterval(interval);
      document.removeEventListener("visibilitychange", load);
    };
  }, [refresh]);
  return (
    <section className="panel operations-panel" aria-labelledby="operations-title">
      <div className="panel-title">
        <span id="operations-title">
          <Activity size={17} /> Processing health
        </span>
        <button
          className="icon-button"
          aria-label="Refresh processing health"
          onClick={() => setRefresh((n) => n + 1)}
        >
          <RefreshCw size={16} />
        </button>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {!value && !error && <p role="status">Checking the analysis worker…</p>}
      {value && (
        <>
          <div className="connection-row">
            <span
              className={`status-icon ${!error && value.worker.status === "healthy" ? "ready" : ""}`}
            >
              <Activity size={17} />
            </span>
            <div>
              <strong>Analysis worker</strong>
              <small>
                {value.worker.last_seen_at
                  ? `Last heartbeat ${new Date(value.worker.last_seen_at).toLocaleTimeString()}`
                  : "No heartbeat received"}
              </small>
            </div>
            <span
              className={`badge ${!error && value.worker.status === "healthy" ? "green" : "red"}`}
            >
              {error
                ? "Check unavailable"
                : value.worker.status === "healthy"
                  ? "Online"
                  : "Unavailable"}
            </span>
          </div>
          <dl className="operations-measurements">
            {(
              [
                ["Queued analyses", value.jobs.queued],
                ["Running analyses", value.jobs.running],
                ["Completed · 24 hours", value.jobs.completed_24h],
                ["Failed · 24 hours", value.jobs.failed_24h],
                ["Expired leases", value.jobs.expired_leases],
                ["Monitored areas", value.monitoring.enabled],
                ["Overdue monitoring checks", value.monitoring.overdue],
              ] as const
            ).map(([label, count]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{count}</dd>
              </div>
            ))}
            <div>
              <dt>Processing time · p95 / 24h</dt>
              <dd>
                {value.jobs.duration_p95_seconds === null
                  ? "No completed runs"
                  : `${Math.round(value.jobs.duration_p95_seconds)}s`}
              </dd>
            </div>
          </dl>
          {value.jobs.oldest_queued_at && (
            <p className="panel-footnote">
              Oldest queued analysis:{" "}
              {new Date(value.jobs.oldest_queued_at).toLocaleString()}
            </p>
          )}
          <p className="panel-footnote">
            Your workspace only. Checked{" "}
            {new Date(value.checked_at).toLocaleTimeString()}; refreshes every 30
            seconds while visible.
          </p>
        </>
      )}
    </section>
  );
}
