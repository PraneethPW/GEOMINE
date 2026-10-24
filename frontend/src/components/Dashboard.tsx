import { useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Fingerprint,
  MapPin,
  Radar,
  ShieldCheck,
} from "lucide-react";
import type { Alert, Area, Audit, Job } from "../api";
import {
  CHART_COLORS,
  ChartEmpty,
  Distribution,
  QualityBars,
  TimelineChart,
} from "./Analytics";

type Props = {
  areas: Area[];
  jobs: Job[];
  alerts: Alert[];
  audit: Audit[];
  connected: boolean;
  lastUpdated: string | null;
  lastEvent: string | null;
  onCreateArea: () => void;
};
export default function Dashboard({
  areas,
  jobs,
  alerts,
  audit,
  connected,
  lastUpdated,
  lastEvent,
  onCreateArea,
}: Props) {
  const [period, setPeriod] = useState(0),
    [area, setArea] = useState("all");
  const navigate = useNavigate();
  const completed = jobs.filter((j) => j.status === "completed" && j.result);
  const cutoff = period ? Date.now() - period * 86400000 : 0;
  const measured = completed.filter(
    (j) => (area === "all" || j.area_id === area) && Date.parse(j.after_end) >= cutoff,
  );
  const statuses = ["completed", "running", "queued", "failed", "cancelled"];
  const metrics = [
    {
      label: "STUDY AREAS",
      value: areas.length,
      detail: `${areas.filter((a) => a.monitoring).length} monitored on schedule`,
      icon: MapPin,
    },
    {
      label: "RECENT COMPLETED ANALYSES",
      value: completed.length,
      detail: `${jobs.filter((j) => ["running", "queued"].includes(j.status)).length} processing or queued`,
      icon: Activity,
    },
    {
      label: "CANDIDATES TO REVIEW",
      value: alerts.filter((a) => a.status === "new").length,
      detail: `${alerts.length} recorded candidates`,
      icon: ShieldCheck,
    },
    {
      label: "SAVED COVERAGE",
      value: areas.reduce((v, a) => v + a.area_km2, 0).toFixed(2),
      unit: "km²",
      detail: "Sum of saved study-area sizes",
      icon: Radar,
    },
  ];
  return (
    <div className="dashboard">
      <div className="dashboard-metrics">
        {metrics.map((m) => (
          <div key={m.label}>
            <span>
              {m.label}
              <m.icon size={16} />
            </span>
            <strong>
              {m.value}
              <small>{m.unit}</small>
            </strong>
            <p>{m.detail}</p>
          </div>
        ))}
      </div>
      {!areas.length && (
        <div className="onboarding-line">
          <span className="onboarding-number">01</span>
          <div>
            <strong>Start with a place you know.</strong>
            <p>
              Define your first study area. Your observations and charts will build from
              there.
            </p>
          </div>
          <button className="button primary small" onClick={onCreateArea}>
            Define study area <ArrowRight size={15} />
          </button>
        </div>
      )}
      <div className="dashboard-primary">
        <section className="chart-panel observation-chart">
          <div className="chart-heading">
            <div>
              <span className="eyebrow">OBSERVATIONS ACROSS TIME</span>
              <h2>Measured surface change</h2>
            </div>
            <div className="chart-period" aria-label="Chart time range">
              {[7, 30, 90, 0].map((n) => (
                <button
                  key={n}
                  className={period === n ? "active" : ""}
                  onClick={() => setPeriod(n)}
                  aria-pressed={period === n}
                >
                  {n ? `${n}D` : "All"}
                </button>
              ))}
            </div>
          </div>
          <div className="chart-toolbar">
            <select
              aria-label="Chart study area"
              value={area}
              onChange={(e) => setArea(e.target.value)}
            >
              <option value="all">All study areas</option>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
            <span>Acquisition-window end · candidate area in hectares</span>
          </div>
          <TimelineChart
            points={measured.map((j) => ({
              id: j.id,
              date: j.after_end,
              value: j.result!.area_ha,
              label: j.area_name || "Study area",
              group: j.area_name || j.area_id,
            }))}
            unit="ha"
            onSelect={(id) => navigate(`/app/analyses/${id}`)}
            empty={
              completed.length
                ? "No completed observations in this date range."
                : "Your first completed comparison will appear here."
            }
          />
          <p className="chart-note">
            Each point is a measured run. Repeated observations can overlap; this is not
            cumulative land loss.
          </p>
        </section>
        <section className="chart-panel">
          <div className="chart-heading">
            <div>
              <span className="eyebrow">PROCESSING ACTIVITY</span>
              <h2>Analysis pipeline</h2>
            </div>
            <Activity size={18} />
          </div>
          <Distribution
            items={statuses.map((name, i) => ({
              name,
              value: jobs.filter((j) => j.status === name).length,
              color: CHART_COLORS[i],
            }))}
            totalLabel="analyses"
          />
          <Link className="chart-page-link" to="/app/analyses">
            Open analysis history <ArrowUpRight size={15} />
          </Link>
        </section>
      </div>
      <div className="dashboard-secondary">
        <section className="chart-panel">
          <div className="chart-heading">
            <div>
              <span className="eyebrow">SENSOR COVERAGE</span>
              <h2>Observation quality</h2>
            </div>
            <Radar size={18} />
          </div>
          <QualityBars jobs={completed} />
        </section>
        <section className="chart-panel">
          <div className="chart-heading">
            <div>
              <span className="eyebrow">WORKSPACE PULSE</span>
              <h2>Activity as it happens</h2>
            </div>
            <span className={`connection ${connected ? "online" : ""}`}>
              <span />
              {connected ? "Live" : "Reconnecting"}
            </span>
          </div>
          {audit.length ? (
            <div className="live-activity">
              {audit.slice(0, 6).map((a) => (
                <div key={a.id}>
                  <span className="activity-glyph">
                    <Fingerprint size={14} />
                  </span>
                  <div>
                    <strong>{a.action.replaceAll(".", " · ")}</strong>
                    <small>{new Date(a.created_at).toLocaleString()}</small>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <ChartEmpty>
              Saved changes, completed analyses, and reviews appear here.
            </ChartEmpty>
          )}
          <div className="activity-stream-note">
            <span className={connected ? "live-dot" : "offline-dot"} />
            {lastEvent
              ? `Last event received ${new Date(lastEvent).toLocaleTimeString()}`
              : connected
                ? "Connected. Waiting for your next workspace event."
                : "Reconnecting to your event stream."}
          </div>
        </section>
      </div>
      <section className="panel latest-observations">
        <div className="panel-title">
          <span>Recent observations</span>
          <Link to="/app/analyses" className="inline-link">
            View all <ArrowRight size={14} />
          </Link>
        </div>
        {jobs.length ? (
          <div className="recent-job-list">
            {jobs.slice(0, 5).map((j) => (
              <Link key={j.id} to={`/app/analyses/${j.id}`}>
                <span className={`job-dot ${j.status}`} />
                <div>
                  <strong>{j.area_name || "Study area"}</strong>
                  <small>
                    {j.before_start} → {j.after_end}
                  </small>
                </div>
                <span>{j.status}</span>
                <strong>
                  {j.result
                    ? `${j.result.area_ha.toFixed(2)} ha`
                    : j.status === "running"
                      ? `${j.progress}%`
                      : "—"}
                </strong>
                <ArrowUpRight size={16} />
              </Link>
            ))}
          </div>
        ) : (
          <div className="recent-empty">
            <Activity size={20} />
            <p>
              No observations yet. Choose two time windows after adding a study area.
            </p>
          </div>
        )}
      </section>
      <div className="dashboard-data-stamp">
        Based on the latest 100 analyses and up to 2,000 candidates. Updated
        {lastUpdated ? ` at ${new Date(lastUpdated).toLocaleTimeString()}` : ""}. New
        measurements arrive when processing completes.
      </div>
    </div>
  );
}
