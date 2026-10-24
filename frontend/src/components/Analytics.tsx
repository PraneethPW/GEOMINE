import { useId, useState } from "react";
import type { ReactNode } from "react";
import { Activity, BarChart3, Crosshair, Layers3 } from "lucide-react";
import type { Alert, Job, Scene } from "../api";

export const CHART_COLORS = ["#b7f477", "#88bbdf", "#e7b971", "#bd9ee8", "#e58985"];
export type ChartPoint = {
  id: string;
  date: string;
  value: number;
  label: string;
  group?: string;
};
const shortDate = (date: string) =>
  new Date(date).toLocaleDateString(undefined, { day: "numeric", month: "short" });

export function ChartEmpty({ children }: { children: ReactNode }) {
  return (
    <div className="chart-empty">
      <div className="empty-chart-grid" aria-hidden="true" />
      <BarChart3 size={25} />
      <p>{children}</p>
      <small>Visuals populate from actual observations.</small>
    </div>
  );
}

export function TimelineChart({
  points,
  unit,
  onSelect,
  empty = "Complete an analysis to see measurements across time.",
}: {
  points: ChartPoint[];
  unit: string;
  onSelect?: (id: string) => void;
  empty?: string;
}) {
  const [focused, setFocused] = useState<ChartPoint | null>(null);
  const gradient = useId().replaceAll(":", "");
  if (!points.length) return <ChartEmpty>{empty}</ChartEmpty>;
  const ordered = [...points].sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
  const dates = ordered.map((p) => Date.parse(p.date)),
    minDate = Math.min(...dates),
    maxDate = Math.max(...dates);
  const low = minDate === maxDate ? minDate - 86400000 : minDate,
    high = minDate === maxDate ? maxDate + 86400000 : maxDate;
  const max = Math.max(1, Math.max(...ordered.map((p) => p.value)) * 1.12);
  const x = (p: ChartPoint) => 52 + ((Date.parse(p.date) - low) / (high - low)) * 690,
    y = (p: ChartPoint) => 210 - (p.value / max) * 170;
  const groups = Array.from(new Set(ordered.map((p) => p.group || "Measurements")));
  return (
    <div className="timeline-chart">
      <svg
        viewBox="0 0 780 260"
        role="group"
        aria-label={`${points.length} measured observations. Unit: ${unit}. Focus a point for its value.`}
      >
        <defs>
          <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#b7f477" stopOpacity=".16" />
            <stop offset="100%" stopColor="#b7f477" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <line
              x1="52"
              x2="742"
              y1={210 - i * 42.5}
              y2={210 - i * 42.5}
              stroke="#27332c"
              strokeDasharray="3 6"
            />
            <text x="39" y={214 - i * 42.5} textAnchor="end">
              {((i * max) / 4).toLocaleString(undefined, { maximumFractionDigits: 1 })}
            </text>
          </g>
        ))}
        <text x="52" y="20">
          {unit}
        </text>
        {(high - low <= 2 * 86400000 ? [0, 0.5, 1] : [0, 1 / 3, 2 / 3, 1]).map((i) => (
          <text
            key={i}
            x={52 + i * 690}
            y="243"
            textAnchor={i === 0 ? "start" : i === 1 ? "end" : "middle"}
          >
            {shortDate(new Date(low + (high - low) * i).toISOString())}
          </text>
        ))}
        {groups.map((group, index) => {
          const series = ordered.filter((p) => (p.group || "Measurements") === group);
          return (
            <g key={group}>
              {groups.length === 1 && series.length > 1 && (
                <path
                  d={`M${x(series[0])},210 ${series.map((p) => `L${x(p)},${y(p)}`).join(" ")} L${x(series[series.length - 1])},210 Z`}
                  fill={`url(#${gradient})`}
                />
              )}
              <path
                d={series.map((p, i) => `${i ? "L" : "M"}${x(p)},${y(p)}`).join(" ")}
                stroke={CHART_COLORS[index % 5]}
                strokeWidth="2"
                fill="none"
              />
              {series.map((p) => (
                <circle
                  key={p.id}
                  cx={x(p)}
                  cy={y(p)}
                  r={focused?.id === p.id ? 6 : 4}
                  fill={CHART_COLORS[index % 5]}
                  stroke="#101713"
                  strokeWidth="2"
                  tabIndex={0}
                  role={onSelect ? "button" : "img"}
                  aria-label={`${p.label}, ${new Date(p.date).toLocaleString()}: ${p.value.toFixed(2)} ${unit}${onSelect ? ". Open observation" : ""}`}
                  onFocus={() => setFocused(p)}
                  onMouseEnter={() => setFocused(p)}
                  onClick={() => onSelect?.(p.id)}
                  onKeyDown={(e) => {
                    if (onSelect && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      onSelect(p.id);
                    }
                  }}
                />
              ))}
            </g>
          );
        })}
      </svg>
      <div className="chart-readout" aria-live="polite">
        {focused ? (
          <>
            <span>
              {focused.label} · {shortDate(focused.date)}
            </span>
            <strong>
              {focused.value.toFixed(2)} {unit}
            </strong>
          </>
        ) : (
          <>
            <span>Focus or hover a point to inspect its source.</span>
            <span>
              {points.length} observation{points.length === 1 ? "" : "s"}
            </span>
          </>
        )}
      </div>
      {groups.length > 1 && (
        <div className="chart-legend">
          {groups.map((g, i) => (
            <span key={g}>
              <i style={{ background: CHART_COLORS[i % 5] }} />
              {g}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function Distribution({
  items,
  totalLabel,
  onSelect,
}: {
  items: { name: string; value: number; color: string; id?: string }[];
  totalLabel: string;
  onSelect?: (id: string) => void;
}) {
  const total = items.reduce((n, i) => n + i.value, 0);
  let offset = 0;
  return (
    <div className="distribution">
      <div className="donut-wrap">
        <svg
          viewBox="0 0 200 200"
          role="img"
          aria-label={`${total} ${totalLabel}. ${items.map((i) => `${i.name}: ${i.value}`).join(", ")}`}
        >
          <circle
            cx="100"
            cy="100"
            r="74"
            fill="none"
            stroke="#233027"
            strokeWidth="14"
          />
          {items
            .filter((i) => i.value > 0)
            .map((i) => {
              const length = (i.value / total) * 464.96;
              const dash = offset;
              offset += length;
              return (
                <circle
                  key={i.name}
                  cx="100"
                  cy="100"
                  r="74"
                  fill="none"
                  stroke={i.color}
                  strokeWidth="14"
                  strokeDasharray={`${Math.max(0, length - 3)} ${464.96 - Math.max(0, length - 3)}`}
                  strokeDashoffset={-dash}
                  transform="rotate(-90 100 100)"
                />
              );
            })}
        </svg>
        <div>
          <strong>{total}</strong>
          <span>{totalLabel}</span>
        </div>
      </div>
      <div className="distribution-legend">
        {items.map((i) =>
          onSelect ? (
            <button key={i.name} onClick={() => onSelect(i.id || i.name)}>
              <i style={{ background: i.color }} />
              <span>{i.name}</span>
              <strong>{i.value}</strong>
            </button>
          ) : (
            <div key={i.name}>
              <i style={{ background: i.color }} />
              <span>{i.name}</span>
              <strong>{i.value}</strong>
            </div>
          ),
        )}
      </div>
    </div>
  );
}

export function QualityBars({ jobs }: { jobs: Job[] }) {
  const completed = jobs.filter((j) => j.result).slice(0, 6);
  if (!completed.length)
    return <ChartEmpty>Optical and radar overlap appear after processing.</ChartEmpty>;
  return (
    <div className="quality-chart">
      <div className="chart-legend">
        <span>
          <i style={{ background: CHART_COLORS[0] }} />
          Clear optical overlap
        </span>
        <span>
          <i style={{ background: CHART_COLORS[1] }} />
          Valid radar overlap
        </span>
      </div>
      {completed.map((j) => (
        <div className="quality-bar-group" key={j.id}>
          <div>
            <strong>{j.area_name || "Study area"}</strong>
            <small>{shortDate(j.after_end)}</small>
          </div>
          {[
            {
              key: "optical",
              value: j.result!.quality.clear_optical_fraction,
              color: CHART_COLORS[0],
            },
            {
              key: "radar",
              value: j.result!.quality.radar_valid_fraction,
              color: CHART_COLORS[1],
            },
          ].map((v) => (
            <div className="quality-bar" key={v.key}>
              <span
                role="meter"
                aria-label={`${j.area_name || "Study area"} ${v.key} overlap`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(v.value * 100)}
              >
                <i
                  style={{
                    width: `${Math.max(0, Math.min(100, v.value * 100))}%`,
                    background: v.color,
                  }}
                />
              </span>
              <b>{(v.value * 100).toFixed(0)}%</b>
            </div>
          ))}
        </div>
      ))}
      <div className="chart-scale">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}

export function CatalogCharts({
  scenes,
  searched,
  sensor,
}: {
  scenes: Scene[];
  searched: boolean;
  sensor: "optical" | "radar";
}) {
  const byDay = new Map<string, number>();
  for (const scene of scenes) {
    const day = scene.datetime.slice(0, 10);
    byDay.set(day, (byDay.get(day) || 0) + 1);
  }
  const days = Array.from(byDay).sort((a, b) => a[0].localeCompare(b[0]));
  const max = Math.max(1, ...days.map((d) => d[1]));
  const optical = scenes.filter(
    (s) => s.cloud_cover !== null && s.cloud_cover !== undefined,
  );
  return (
    <div className="analytics-grid">
      <section className="chart-panel">
        <div className="chart-heading">
          <div>
            <span className="eyebrow">SOURCE AVAILABILITY</span>
            <h2>Acquisitions through time</h2>
          </div>
          <Activity size={18} />
        </div>
        {days.length ? (
          <div className="acquisition-histogram">
            <div className="histogram-bars">
              {days.map(([day, n]) => (
                <div key={day}>
                  <span>{n}</span>
                  <i
                    style={{ height: `${(n / max) * 145}px` }}
                    role="img"
                    aria-label={`${day}: ${n} returned acquisitions`}
                    title={`${day}: ${n} acquisitions`}
                  />
                  <small>{shortDate(day)}</small>
                </div>
              ))}
            </div>
            <p>Returned acquisitions per day · UTC · up to 30 catalog records</p>
          </div>
        ) : (
          <ChartEmpty>
            {searched
              ? "No acquisitions returned for these dates."
              : "Search a study area to chart actual acquisition dates."}
          </ChartEmpty>
        )}
      </section>
      <section className="chart-panel">
        <div className="chart-heading">
          <div>
            <span className="eyebrow">
              {sensor === "optical" ? "OPTICAL CONDITIONS" : "RADAR PLATFORM MIX"}
            </span>
            <h2>{sensor === "optical" ? "Scene cloud cover" : "Returned platforms"}</h2>
          </div>
          <Layers3 size={18} />
        </div>
        {sensor === "optical" ? (
          <TimelineChart
            points={optical.map((s) => ({
              id: s.id,
              date: s.datetime,
              value: s.cloud_cover!,
              label: s.platform || s.id,
            }))}
            unit="% cloud"
            empty="Scene cloud metadata appears after an optical search."
          />
        ) : (
          <Distribution
            items={Array.from(
              new Set(scenes.map((s) => s.platform || "Sentinel-1")),
            ).map((name, i) => ({
              name,
              value: scenes.filter((s) => (s.platform || "Sentinel-1") === name).length,
              color: CHART_COLORS[i % 5],
            }))}
            totalLabel="scenes"
          />
        )}
      </section>
    </div>
  );
}

export function CandidateCharts({
  alerts,
  onFilter,
}: {
  alerts: Alert[];
  onFilter?: (status: string) => void;
}) {
  const statuses = ["new", "investigating", "confirmed", "dismissed"];
  const bins = [0, 0, 0, 0, 0];
  for (const a of alerts) {
    const i = Math.max(0, Math.min(4, Math.floor(a.score * 5)));
    bins[i]++;
  }
  const max = Math.max(1, ...bins);
  return (
    <div className="analytics-grid candidate-analytics">
      <section className="chart-panel">
        <div className="chart-heading">
          <div>
            <span className="eyebrow">INVESTIGATION STATUS</span>
            <h2>The review picture</h2>
          </div>
          <Crosshair size={18} />
        </div>
        <Distribution
          items={statuses.map((name, i) => ({
            name,
            id: name,
            value: alerts.filter((a) => a.status === name).length,
            color: CHART_COLORS[i],
          }))}
          totalLabel="candidates"
          onSelect={onFilter}
        />
      </section>
      <section className="chart-panel">
        <div className="chart-heading">
          <div>
            <span className="eyebrow">MEASURED EVIDENCE</span>
            <h2>Evidence index distribution</h2>
          </div>
          <BarChart3 size={18} />
        </div>
        {alerts.length ? (
          <div className="acquisition-histogram">
            <div className="histogram-bars">
              {bins.map((n, i) => (
                <div key={i}>
                  <span>{n}</span>
                  <i
                    style={{ height: `${(n / max) * 145}px` }}
                    role="img"
                    aria-label={`Evidence ${i / 5} to ${(i + 1) / 5}: ${n} candidates`}
                  />
                  <small>
                    {(i / 5).toFixed(1)}–{((i + 1) / 5).toFixed(1)}
                  </small>
                </div>
              ))}
            </div>
            <p>Uncalibrated evidence index · not a mining probability</p>
          </div>
        ) : (
          <ChartEmpty>Measured candidates will populate the distribution.</ChartEmpty>
        )}
      </section>
    </div>
  );
}

export function JobVisual({ job }: { job: Job }) {
  if (!job.result) return null;
  return (
    <div className="job-visual">
      <div className="chart-heading">
        <div>
          <span className="eyebrow">OBSERVATION QUALITY</span>
          <h2>What the sensors could see</h2>
        </div>
        <Activity size={18} />
      </div>
      <QualityBars jobs={[job]} />
      <p className="panel-footnote">
        Overlap is calculated from the actual cloud and radar validity masks. Analysis
        grid: {job.result.resolution_m}m ·{" "}
        {job.result.radar_source.replaceAll("-", " ")}
      </p>
    </div>
  );
}
