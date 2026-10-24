import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  CloudSun,
  Code2,
  Compass,
  FileJson,
  FileText,
  Fingerprint,
  Layers3,
  Loader2,
  LogOut,
  MapPin,
  Menu,
  LayoutDashboard,
  Map as MapIcon,
  RefreshCw,
  Orbit,
  Plus,
  Radar,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquareArrowOutUpRight,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import {
  API,
  accessToken,
  endSession,
  api,
  ApiError,
  center,
  dateOffset,
  downloadJob,
  setToken,
  token,
} from "./api";
import type {
  Alert,
  Area,
  Audit,
  Brief,
  Concession,
  Geometry,
  Job,
  Scene,
  System,
  User,
} from "./api";
import { Link, NavLink, Navigate, useLocation, useNavigate } from "react-router";
import Brand from "./components/Brand";
import Dashboard from "./components/Dashboard";
import BriefNarrative from "./components/BriefNarrative";
import OperationsPanel from "./components/OperationsPanel";
import { CatalogCharts, CandidateCharts, JobVisual } from "./components/Analytics";
const MapView = lazy(() => import("./components/MapView"));
const EvidenceCompare = lazy(() => import("./components/EvidenceCompare"));
type Tab =
  | "Overview"
  | "Observatory"
  | "Catalog"
  | "Analyses"
  | "Candidates"
  | "Concessions"
  | "Reports"
  | "System";
const PAGES = [
  {
    name: "Overview",
    path: "overview",
    icon: LayoutDashboard,
    description: "Your observations, connected across time.",
  },
  {
    name: "Observatory",
    path: "map",
    icon: MapIcon,
    description: "Define study areas and investigate change on the satellite map.",
  },
  {
    name: "Catalog",
    path: "catalog",
    icon: Orbit,
    description: "Search dated acquisitions and examine source coverage.",
  },
  {
    name: "Analyses",
    path: "analyses",
    icon: Activity,
    description: "Run comparisons. Follow processing. Inspect the results.",
  },
  {
    name: "Candidates",
    path: "candidates",
    icon: ShieldCheck,
    description: "Review measured disturbance and record your findings.",
  },
  {
    name: "Concessions",
    path: "concessions",
    icon: Layers3,
    description: "Manage the authoritative boundaries behind legal context.",
  },
  {
    name: "Reports",
    path: "reports",
    icon: FileText,
    description: "Grounded analyst briefs and exportable evidence.",
  },
  {
    name: "System",
    path: "system",
    icon: Settings2,
    description: "Source readiness, monitoring schedules, and your audit trail.",
  },
] as const;
const formatDate = (value: string) =>
  new Date(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
const fade = {
  initial: { opacity: 0, y: 15 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.15 },
  transition: { duration: 0.5 },
};
function Empty({
  icon: Icon = Orbit,
  title,
  children,
  action,
}: {
  icon?: typeof Orbit;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Icon size={28} />
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Modal({
  title,
  description,
  onClose,
  children,
}: {
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const old = document.activeElement as HTMLElement;
    ref.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const nodes = Array.from(
          ref.current?.querySelectorAll<HTMLElement>(
            "button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),a[href]",
          ) || [],
        ).filter((node) => node.getClientRects().length > 0);
        if (!nodes?.length) return;
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", key);
      document.body.style.overflow = overflow;
      old?.focus();
    };
  }, [onClose]);
  return (
    <motion.div
      className="modal-backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <motion.div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={ref}
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
      >
        <button
          className="modal-close icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
        <span className="eyebrow">
          <span className="mini-mark" /> GEOMINE WORKSPACE
        </span>
        <h2>{title}</h2>
        {description && <p className="modal-description">{description}</p>}
        {children}
      </motion.div>
    </motion.div>
  );
}
export default function Workspace() {
  const [narrowNav, setNarrowNav] = useState(
    () => window.matchMedia("(max-width: 800px)").matches,
  );
  const navigationRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 800px)");
    const changed = () => setNarrowNav(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  const navigate = useNavigate(),
    location = useLocation();
  const route = location.pathname.split("/")[2] || "overview";
  const page = PAGES.find((p) => p.path === route);
  const tab: Tab = page?.name || "Overview";
  const detailId = tab === "Analyses" ? location.pathname.split("/")[3] : undefined;
  const [checkingAuth, setCheckingAuth] = useState(!!token());
  const [loadError, setLoadError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [lastEvent, setLastEvent] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null),
    [system, setSystem] = useState<System | null>(null);
  const [areas, setAreas] = useState<Area[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [alerts, setAlerts] = useState<Alert[]>([]),
    [concessions, setConcessions] = useState<Concession[]>([]),
    [briefs, setBriefs] = useState<Brief[]>([]),
    [audit, setAudit] = useState<Audit[]>([]);
  const [selected, setSelected] = useState<Area | null>(null),
    [scenes, setScenes] = useState<Scene[]>([]),
    [searching, setSearching] = useState(false),
    [sensor, setSensor] = useState<"optical" | "radar">("optical");
  const [modal, setModal] = useState<
      "area" | "analysis" | "concession" | "alert" | "brief" | null
    >(null),
    [activeAlert, setActiveAlert] = useState<Alert | null>(null),
    [activeBrief, setActiveBrief] = useState<Brief | null>(null);
  const [busy, setBusy] = useState(false),
    [toast, setToast] = useState(""),
    [formError, setFormError] = useState(""),
    [connected, setConnected] = useState(false),
    [connectionAttempted, setConnectionAttempted] = useState(false),
    [mobileNav, setMobileNav] = useState(false);
  const [draftGeometry, setDraftGeometry] = useState<Geometry | null>(null),
    [filter, setFilter] = useState("all"),
    [query, setQuery] = useState("");
  useEffect(() => {
    if (!mobileNav || !narrowNav) return;
    const previous = document.activeElement as HTMLElement | null;
    const panel = navigationRef.current;
    const links = () =>
      Array.from(
        panel?.querySelectorAll<HTMLElement>("a[href],button:not([disabled])") || [],
      );
    links()[0]?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileNav(false);
      if (event.key !== "Tab") return;
      const nodes = links(),
        first = nodes[0],
        last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [mobileNav, narrowNav]);
  const [areaQuery, setAreaQuery] = useState("");
  useEffect(() => {
    const expired = () => setUser(null);
    window.addEventListener("geomine:session-expired", expired);
    return () => window.removeEventListener("geomine:session-expired", expired);
  }, []);
  const [catalogStart, setCatalogStart] = useState(dateOffset(-30)),
    [catalogEnd, setCatalogEnd] = useState(dateOffset(0)),
    [catalogSearched, setCatalogSearched] = useState(false);
  const [compareJob, setCompareJob] = useState<string | null>(null);
  useEffect(() => {
    window.scrollTo(0, 0);
    document.title = `${page?.name || "Workspace"} · GeoMine`;
    setMobileNav(false);
    const frame = requestAnimationFrame(() =>
      headingRef.current?.focus({ preventScroll: true }),
    );
    return () => cancelAnimationFrame(frame);
  }, [location.pathname, page?.name]);
  useEffect(() => {
    setCompareJob(detailId || null);
  }, [detailId]);
  const notify = useCallback((message: string) => setToast(message), []);
  const refresh = useCallback(async () => {
    if (!token()) return;
    const [aa, jj, al, cc, bb, au] = await Promise.all([
      api<Area[]>("/areas"),
      api<Job[]>("/jobs"),
      api<Alert[]>("/alerts"),
      api<Concession[]>("/concessions"),
      api<Brief[]>("/briefs"),
      api<Audit[]>("/audit"),
    ]);
    setAreas(aa);
    setJobs(jj);
    setAlerts(al);
    setConcessions(cc);
    setBriefs(bb);
    setAudit(au);
    setLastUpdated(new Date().toISOString());
    setLoadError("");
    setSelected((old) => aa.find((a) => a.id === old?.id) || aa[0] || null);
  }, []);
  useEffect(() => {
    api<System>("/system")
      .then(setSystem)
      .catch(() => setSystem(null))
      .finally(() => setConnectionAttempted(true));
    let cancelled = false;
    if (token()) {
      api<User>("/auth/me")
        .then(async (value) => {
          if (cancelled) return;
          setUser(value);
          try {
            await refresh();
          } catch (e) {
            if (!cancelled)
              setLoadError(
                e instanceof Error ? e.message : "Workspace data could not be loaded.",
              );
          }
        })
        .catch((error) => {
          if (cancelled) return;
          if (error instanceof ApiError && error.status === 401) {
            setToken("");
            setUser(null);
          } else
            setLoadError(
              "Your session could not be checked. Please retry the connection.",
            );
        })
        .finally(() => {
          if (!cancelled) setCheckingAuth(false);
        });
    } else setCheckingAuth(false);
    return () => {
      cancelled = true;
    };
  }, [refresh]);
  useEffect(() => {
    if (toast) {
      const id = setTimeout(() => setToast(""), 6500);
      return () => clearTimeout(id);
    }
  }, [toast]);
  useEffect(() => {
    if (!user) return;
    const control = new AbortController();
    let cursor = 0;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const scheduleRefresh = () => {
      if (refreshTimer) return;
      refreshTimer = setTimeout(() => {
        refreshTimer = undefined;
        if (!control.signal.aborted)
          refresh().catch((e) => {
            setConnected(false);
            setLoadError(
              e instanceof Error ? e.message : "Unable to refresh observations.",
            );
          });
      }, 250);
    };
    const run = async () => {
      while (!control.signal.aborted) {
        try {
          const response = await fetch(`${API}/api/events?after=${cursor}`, {
            headers: { Authorization: `Bearer ${await accessToken()}` },
            signal: control.signal,
          });
          if (response.status === 401) {
            setToken("");
            setUser(null);
            return;
          }
          if (!response.ok) throw new Error("Event stream disconnected");
          setConnected(true);
          const reader = response.body!.getReader(),
            decoder = new TextDecoder();
          let buffer = "";
          while (!control.signal.aborted) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true }).replace(/\r/g, "");
            let boundary;
            while ((boundary = buffer.indexOf("\n\n")) >= 0) {
              const event = buffer.slice(0, boundary);
              buffer = buffer.slice(boundary + 2);
              const id = event.match(/^id: (\d+)/m);
              if (id) cursor = Number(id[1]);
              if (event.includes("event: update")) {
                setLastEvent(new Date().toISOString());
                scheduleRefresh();
              }
            }
          }
        } catch (error) {
          if (error instanceof ApiError && error.status === 401) {
            setToken("");
            setUser(null);
            return;
          }
          if (!control.signal.aborted) setConnected(false);
        }
        if (!control.signal.aborted) await new Promise((r) => setTimeout(r, 3500));
      }
    };
    run();
    return () => {
      control.abort();
      if (refreshTimer) clearTimeout(refreshTimer);
      setConnected(false);
    };
  }, [user, refresh]);
  const open = useCallback((value: typeof modal) => {
    setFormError("");
    setModal(value);
  }, []);
  const close = useCallback(() => {
    setModal(null);
    setFormError("");
  }, []);
  const requireAuth = (value: typeof modal) => open(value);
  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    setFormError("");
    try {
      await fn();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Something went wrong.";
      setFormError(message);
      notify(message);
    } finally {
      setBusy(false);
    }
  };
  const go = (next: Tab) =>
    navigate(`/app/${PAGES.find((p) => p.name === next)?.path || "overview"}`);
  const logout = () =>
    act(async () => {
      try {
        await api("/auth/logout", { method: "POST" });
      } finally {
        await endSession();
        setUser(null);
        navigate("/login", { replace: true });
      }
    });
  const searchCatalog = (formData: FormData) =>
    act(async () => {
      if (!selected) throw new Error("Choose a saved study area before searching.");
      const start = String(formData.get("start")),
        end = String(formData.get("end"));
      setCatalogStart(start);
      setCatalogEnd(end);
      setSearching(true);
      try {
        const response = await api<{ items: Scene[] }>("/catalog/search", {
          method: "POST",
          body: JSON.stringify({
            geometry: selected!.geometry,
            start,
            end,
            sensor,
          }),
        });
        setScenes(response.items);
        setCatalogSearched(true);
        notify(
          `${response.items.length} real ${sensor === "optical" ? "Sentinel-2" : "Sentinel-1"} acquisitions returned.`,
        );
      } finally {
        setSearching(false);
      }
    });
  const draw = (geometry: Geometry) => {
    setDraftGeometry(geometry);
    requireAuth("area");
  };
  const selectedAlerts = selected
    ? alerts.filter((a) => a.area_id === selected.id)
    : alerts;
  const visibleAlerts = alerts.filter(
    (a) =>
      (filter === "all" || a.status === filter) &&
      a.area_name.toLowerCase().includes(query.toLowerCase()),
  );
  if (checkingAuth)
    return (
      <div className="app-loading" role="status">
        <Loader2 className="spin" />
        <span>Opening your observatory…</span>
      </div>
    );
  if (loadError && !lastUpdated)
    return (
      <div className="app-loading">
        <h1>Workspace temporarily unavailable.</h1>
        <p role="alert">{loadError}</p>
        <button
          className="button primary"
          onClick={() => (user ? act(refresh) : window.location.reload())}
          disabled={busy}
        >
          Retry connection
        </button>
        <button className="inline-link" onClick={logout}>
          Sign out
        </button>
      </div>
    );
  if (!user)
    return (
      <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
    );
  if (!page) return <Navigate to="/app/overview" replace />;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Skip to page content
      </a>
      {mobileNav && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside
        ref={navigationRef}
        id="workspace-navigation"
        className={`app-sidebar ${mobileNav ? "is-open" : ""}`}
        inert={narrowNav && !mobileNav}
        role={narrowNav && mobileNav ? "dialog" : undefined}
        aria-modal={narrowNav && mobileNav ? true : undefined}
        aria-label="Workspace navigation"
      >
        <Brand to="/app/overview" />
        <button
          className="icon-button mobile-navigation-close"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        >
          <X size={18} />
        </button>
        <span className="sidebar-label">OBSERVATION WORKSPACE</span>
        <nav aria-label="Workspace navigation">
          {PAGES.map((p) => (
            <NavLink
              to={`/app/${p.path}`}
              key={p.path}
              onClick={() => setMobileNav(false)}
            >
              <p.icon size={18} />
              <span>{p.name === "Observatory" ? "Map explorer" : p.name}</span>
              {p.name === "Candidates" && alerts.some((a) => a.status === "new") && (
                <span className="sidebar-count">
                  {alerts.filter((a) => a.status === "new").length}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-source">
          <span className="live-dot" /> SENTINEL OBSERVATORY
          <small>
            {system?.radar_coverage || "Source-dependent coverage"} ·{" "}
            {system?.analysis_resolution_m || "—"}m grid
          </small>
        </div>
        <div className="sidebar-account">
          <span className="avatar">{user.name.slice(0, 1).toUpperCase()}</span>
          <span>
            <strong>{user.name}</strong>
            <small>{user.email}</small>
          </span>
          <button className="icon-button" title="Sign out" onClick={logout}>
            <LogOut size={16} />
          </button>
        </div>
        <Link className="back-to-site" to="/">
          Back to the website <ArrowUpRight size={12} />
        </Link>
      </aside>
      <div className="app-main" inert={narrowNav && mobileNav}>
        <header className="app-topbar">
          <div>
            <button
              className="icon-button app-menu"
              aria-label="Open navigation"
              aria-expanded={mobileNav}
              aria-controls="workspace-navigation"
              onClick={() => setMobileNav(!mobileNav)}
            >
              <Menu size={20} />
            </button>
            <span>
              Workspace <ChevronRight size={12} />{" "}
              <strong>{tab === "Observatory" ? "Map explorer" : tab}</strong>
              {detailId && (
                <>
                  <ChevronRight size={12} />
                  <span>Analysis detail</span>
                </>
              )}
            </span>
          </div>
          <div className="topbar-live">
            <span className={`connection ${connected ? "online" : ""}`}>
              <span />
              {connected ? "Live event stream" : "Reconnecting"}
            </span>
            <button
              className="icon-button"
              title="Refresh workspace"
              onClick={() => act(refresh)}
              disabled={busy}
            >
              <RefreshCw size={16} className={busy ? "spin" : ""} />
            </button>
          </div>
        </header>
        <main className="workspace app-workspace" id="workspace" tabIndex={-1}>
          <div className="app-page-heading">
            <div>
              <span className="eyebrow">
                {new Date().toLocaleDateString(undefined, {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                })}
              </span>
              <h1 ref={headingRef} tabIndex={-1}>
                {tab === "Overview"
                  ? `Your planet, in perspective.`
                  : detailId
                    ? "Inside the observation."
                    : tab === "Observatory"
                      ? "Map explorer."
                      : `${tab}.`}
              </h1>
              <p>{page.description}</p>
            </div>
            <div className="section-actions">
              {tab === "Overview" || tab === "Analyses" ? (
                <button
                  className="button primary small"
                  onClick={() => (areas.length ? open("analysis") : open("area"))}
                >
                  <Plus size={16} />
                  {areas.length ? "New analysis" : "Add first study area"}
                </button>
              ) : tab === "Observatory" ? (
                <button
                  className="button primary small"
                  onClick={() => {
                    setDraftGeometry(null);
                    open("area");
                  }}
                >
                  <Plus size={16} />
                  Add study area
                </button>
              ) : null}
            </div>
          </div>
          {loadError && (
            <div className="workspace-error" role="alert">
              <span>{loadError}</span>
              <button onClick={() => act(refresh)}>
                Retry <RefreshCw size={14} />
              </button>
            </div>
          )}
          {tab === "Overview" && (
            <Dashboard
              areas={areas}
              jobs={jobs}
              alerts={alerts}
              audit={audit}
              connected={connected}
              lastUpdated={lastUpdated}
              lastEvent={lastEvent}
              onCreateArea={() => {
                setDraftGeometry(null);
                open("area");
              }}
            />
          )}
          {tab === "Observatory" && (
            <>
              <motion.div className="explorer-layout" {...fade}>
                <aside className="area-panel">
                  <div className="panel-title">
                    <span>
                      <Compass size={16} /> Study areas
                    </span>
                    <Badge>{areas.length.toString().padStart(2, "0")}</Badge>
                  </div>
                  <div className="input-search">
                    <Search size={15} />
                    <input
                      aria-label="Search study areas"
                      placeholder="Find an area…"
                      value={areaQuery}
                      onChange={(e) => setAreaQuery(e.target.value)}
                    />
                    <kbd>⌕</kbd>
                  </div>
                  <div className="area-list">
                    {areas
                      .filter((a) =>
                        a.name.toLowerCase().includes(areaQuery.toLowerCase()),
                      )
                      .map((a) => (
                        <button
                          className={`area-card ${a.id === selected?.id ? "active" : ""}`}
                          key={a.id}
                          onClick={() => {
                            setSelected(a);
                            setScenes([]);
                            setCatalogSearched(false);
                          }}
                        >
                          <div>
                            <span className="area-icon">
                              <MapPin size={16} />
                            </span>
                            <span>
                              <strong>{a.name}</strong>
                              <small>
                                {Math.abs(center(a.geometry)[1]).toFixed(3)}°{" "}
                                {center(a.geometry)[1] < 0 ? "S" : "N"} ·{" "}
                                {Math.abs(center(a.geometry)[0]).toFixed(3)}°{" "}
                                {center(a.geometry)[0] < 0 ? "W" : "E"}
                              </small>
                            </span>
                            <ChevronRight size={15} />
                          </div>
                          <div className="area-meta">
                            <span>{a.area_km2.toFixed(1)} km²</span>
                            <span className={a.monitoring ? "lime-text" : ""}>
                              <span className="tiny-dot" />
                              {a.monitoring ? "Monitoring" : "On demand"}
                            </span>
                          </div>
                        </button>
                      ))}
                    {!areas.length && (
                      <Empty icon={MapPin} title="Your watch starts here">
                        Draw an area on the map or import a GeoJSON boundary.
                        <button
                          className="inline-link"
                          onClick={() => {
                            setDraftGeometry(null);
                            requireAuth("area");
                          }}
                        >
                          Create study area <Plus size={13} />
                        </button>
                      </Empty>
                    )}
                  </div>
                  <div className="area-panel-bottom">
                    <Layers3 size={15} />
                    <span>
                      Every observation has a source.
                      <br />
                      <strong>Every decision has a record.</strong>
                    </span>
                  </div>
                </aside>
                <Suspense
                  fallback={
                    <div className="map-loading">
                      <Loader2 className="spin" /> Loading satellite map
                    </div>
                  }
                >
                  <MapView
                    areas={areas}
                    alerts={selectedAlerts}
                    scenes={scenes}
                    selected={selected}
                    onSelect={(a) => {
                      setSelected(a);
                      setScenes([]);
                    }}
                    onDraw={draw}
                    onAlert={(a) => {
                      setActiveAlert(a);
                      open("alert");
                    }}
                  />
                </Suspense>
              </motion.div>
              <div className="explorer-footer">
                <span>
                  <CircleHelp size={14} /> Basemap imagery is for orientation. Analysis
                  uses dated Sentinel acquisitions.
                </span>
                <span>
                  WGS 84 <span className="dot-separator">·</span>{" "}
                  {system?.analysis_resolution_m
                    ? `${system.analysis_resolution_m} m analysis grid`
                    : "Source-dependent grid"}{" "}
                  <span className="dot-separator">·</span> ESA / COPERNICUS
                </span>
              </div>
              {selected && (
                <div className="map-next-action">
                  <span>
                    <strong>{selected.name}</strong> · {selected.area_km2.toFixed(2)}{" "}
                    km²
                  </span>
                  <button
                    className="button secondary small"
                    onClick={() => go("Catalog")}
                  >
                    Find acquisitions <Orbit size={14} />
                  </button>
                  <button
                    className="button primary small"
                    onClick={() => open("analysis")}
                  >
                    Compare time windows <ArrowRight size={14} />
                  </button>
                </div>
              )}
            </>
          )}
          {tab === "Catalog" && (
            <>
              <div className="catalog-area-select">
                <label>
                  Study area
                  <select
                    aria-label="Catalog study area"
                    value={selected?.id || ""}
                    onChange={(e) => {
                      setSelected(areas.find((a) => a.id === e.target.value) || null);
                      setScenes([]);
                      setCatalogSearched(false);
                    }}
                  >
                    <option value="" disabled>
                      Select a saved study area
                    </option>
                    {areas.map((a) => (
                      <option value={a.id} key={a.id}>
                        {a.name} · {a.area_km2.toFixed(2)} km²
                      </option>
                    ))}
                  </select>
                </label>
                <span>Acquisitions are queried from the source for this boundary.</span>
                {!areas.length && (
                  <button
                    className="button secondary small"
                    onClick={() => go("Observatory")}
                  >
                    Define an area <ArrowRight size={14} />
                  </button>
                )}
              </div>
              <motion.section className="panel catalog-panel" {...fade}>
                <div className="panel-title">
                  <span>
                    <Orbit size={17} /> Acquisition catalog
                  </span>
                  <Badge tone="green">LIVE SOURCE</Badge>
                </div>
                <p className="panel-subtitle">
                  Discover actual satellite scenes over{" "}
                  {selected?.name || "your selected study area"}.
                </p>
                <form
                  className="catalog-toolbar"
                  onSubmit={(e) => {
                    e.preventDefault();
                    searchCatalog(new FormData(e.currentTarget));
                  }}
                >
                  <div className="segmented">
                    <button
                      type="button"
                      className={sensor === "optical" ? "active" : ""}
                      onClick={() => {
                        setSensor("optical");
                        setScenes([]);
                        setCatalogSearched(false);
                      }}
                    >
                      Optical <small>S2</small>
                    </button>
                    <button
                      type="button"
                      className={sensor === "radar" ? "active" : ""}
                      onClick={() => {
                        setSensor("radar");
                        setScenes([]);
                        setCatalogSearched(false);
                      }}
                    >
                      Radar <small>S1</small>
                    </button>
                  </div>
                  <div className="date-pair">
                    <input
                      aria-label="Catalog start"
                      type="date"
                      name="start"
                      required
                      defaultValue={catalogStart}
                    />
                    <span>→</span>
                    <input
                      aria-label="Catalog end"
                      type="date"
                      name="end"
                      required
                      defaultValue={catalogEnd}
                      max={dateOffset(0)}
                    />
                  </div>
                  <button
                    className="button secondary small"
                    disabled={searching || !selected}
                    type="submit"
                  >
                    {searching ? (
                      <Loader2 className="spin" size={15} />
                    ) : (
                      <Search size={15} />
                    )}{" "}
                    Search
                  </button>
                </form>
                <div className="scene-list">
                  {scenes.map((s) => (
                    <div className="scene-row" key={s.id}>
                      <span className="sensor-icon">
                        {s.sensor === "optical" ? (
                          <CloudSun size={18} />
                        ) : (
                          <Radar size={18} />
                        )}
                      </span>
                      <div>
                        <strong>{s.platform || s.sensor}</strong>
                        <small title={s.id}>
                          {s.id.length > 48 ? s.id.slice(0, 48) + "…" : s.id}
                        </small>
                      </div>
                      <span>{formatDate(s.datetime)}</span>
                      <Badge>
                        {s.cloud_cover === null || s.cloud_cover === undefined
                          ? "SAR"
                          : `${s.cloud_cover.toFixed(1)}% cloud`}
                      </Badge>
                      <a
                        className="icon-button"
                        href={s.catalog_url}
                        target="_blank"
                        rel="noreferrer"
                        title="Open original STAC record"
                      >
                        <ArrowUpRight size={17} />
                      </a>
                    </div>
                  ))}
                  {!scenes.length && (
                    <Empty
                      icon={Orbit}
                      title={
                        catalogSearched
                          ? "No acquisitions in this window"
                          : "Follow the next observation"
                      }
                    >
                      {catalogSearched
                        ? "Try a wider date range or another area."
                        : "Search the live STAC catalog to see real acquisition dates, cloud coverage, and scene footprints."}
                    </Empty>
                  )}
                </div>
              </motion.section>

              <CatalogCharts
                scenes={scenes}
                searched={catalogSearched}
                sensor={sensor}
              />
            </>
          )}
          {tab === "Analyses" && (
            <>
              <div className="analysis-navigation">
                {detailId && (
                  <Link to="/app/analyses" className="inline-link">
                    ← All analyses
                  </Link>
                )}
              </div>
              <section className="panel">
                <div className="panel-title">
                  <span>
                    <Activity size={17} />{" "}
                    {detailId ? "Observation detail" : "Analysis history"}
                  </span>
                  <button
                    className="button secondary small"
                    onClick={() =>
                      selected ? requireAuth("analysis") : requireAuth("area")
                    }
                  >
                    <Plus size={15} /> New analysis
                  </button>
                </div>
                {!detailId && jobs.length > 0 ? (
                  <div className="table-wrap">
                    <table className="analysis-table">
                      <thead>
                        <tr>
                          <th>STUDY AREA / OBSERVATION</th>
                          <th>PROCESSING</th>
                          <th>OBSERVED CHANGE</th>
                          <th>CANDIDATES</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {jobs.map((j) => (
                          <tr key={j.id}>
                            <td>
                              <Link to={`/app/analyses/${j.id}`}>
                                <strong>{j.area_name || "Study area"}</strong>
                                <small>{formatDate(j.created_at)}</small>
                              </Link>
                            </td>
                            <td>
                              <Badge
                                tone={
                                  j.status === "completed"
                                    ? "green"
                                    : j.status === "failed"
                                      ? "red"
                                      : "neutral"
                                }
                              >
                                {j.status}
                              </Badge>
                              {["queued", "running"].includes(j.status) && (
                                <div className="table-progress">
                                  <progress max={100} value={j.progress} />
                                  <small>
                                    {j.stage} · {j.progress}%
                                  </small>
                                </div>
                              )}
                            </td>
                            <td>
                              {j.result ? `${j.result.area_ha.toFixed(2)} ha` : "—"}
                            </td>
                            <td>{j.result ? j.result.candidate_count : "—"}</td>
                            <td>
                              <Link
                                className="button secondary small"
                                to={`/app/analyses/${j.id}`}
                              >
                                Open observation <ArrowUpRight size={14} />
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : !jobs.length ||
                  (detailId && !jobs.some((j) => j.id === detailId)) ? (
                  <Empty
                    icon={Activity}
                    title={
                      detailId
                        ? "Observation not found"
                        : "A new perspective begins with a comparison"
                    }
                  >
                    Create a study area, choose two acquisition windows, and process the
                    actual satellite pixels.
                  </Empty>
                ) : (
                  <div className="jobs-list">
                    {jobs
                      .filter((j) => j.id === detailId)
                      .map((j) => (
                        <article className="job-card" key={j.id}>
                          <div className="job-heading">
                            <div>
                              <h3>{j.area_name || "Study area"}</h3>
                              <span>
                                {j.engine === "geomine"
                                  ? "GeoMine-XNet neural model"
                                  : "Physical change detector"}{" "}
                                <span className="dot-separator">·</span>{" "}
                                {formatDate(j.created_at)}
                              </span>
                            </div>
                            <Badge
                              tone={
                                j.status === "completed"
                                  ? "green"
                                  : j.status === "failed"
                                    ? "red"
                                    : "neutral"
                              }
                            >
                              {j.status}
                            </Badge>
                          </div>
                          <div className="job-windows">
                            <span>
                              <small>BEFORE</small>
                              {j.before_start} — {j.before_end}
                            </span>
                            <ArrowRight size={17} />
                            <span>
                              <small>AFTER</small>
                              {j.after_start} — {j.after_end}
                            </span>
                          </div>
                          {["queued", "running"].includes(j.status) && (
                            <div className="job-progress">
                              <div>
                                <span>{j.stage}</span>
                                <span>{j.progress}%</span>
                              </div>
                              <progress value={j.progress} max={100} />
                              <button
                                className="inline-link"
                                onClick={() =>
                                  act(async () => {
                                    await api(`/jobs/${j.id}/cancel`, {
                                      method: "POST",
                                    });
                                    await refresh();
                                  })
                                }
                              >
                                Cancel analysis
                              </button>
                            </div>
                          )}
                          {j.error && <p className="form-error">{j.error}</p>}
                          {j.result && (
                            <>
                              {j.result.engine === "physical" &&
                                j.result.quality.clear_optical_fraction < 0.5 && (
                                  <p className="coverage-notice" role="note">
                                    {j.result.quality.clear_optical_fraction === 0 ? (
                                      <>
                                        No clear optical overlap. The physical detector
                                        could not assess disturbance in this comparison.
                                        Choose different acquisition windows; zero
                                        candidates does not mean no disturbance.
                                      </>
                                    ) : (
                                      <>
                                        Clouds limit this comparison to{" "}
                                        {(
                                          j.result.quality.clear_optical_fraction * 100
                                        ).toFixed(1)}
                                        % clear optical overlap. Candidate measurements
                                        apply to usable pixels; they cannot rule out
                                        disturbance elsewhere in the area.
                                      </>
                                    )}
                                  </p>
                                )}
                              <div className="job-result">
                                <span>
                                  <strong>{j.result.candidate_count}</strong> candidates
                                </span>
                                <span>
                                  <strong>{j.result.area_ha.toFixed(2)}</strong> ha
                                  candidate area
                                </span>
                                <span>
                                  <strong>
                                    {(
                                      j.result.quality.clear_optical_fraction * 100
                                    ).toFixed(0)}
                                    %
                                  </strong>{" "}
                                  clear optical overlap
                                </span>
                                <span>
                                  <strong>
                                    {(
                                      j.result.quality.radar_valid_fraction * 100
                                    ).toFixed(0)}
                                    %
                                  </strong>{" "}
                                  valid radar
                                </span>
                              </div>
                              <JobVisual job={j} />
                              <details>
                                <summary>
                                  Source acquisitions and interpretation limits
                                </summary>
                                <ul>
                                  {j.result.scenes.map((s) => (
                                    <li key={s.id}>
                                      <a
                                        href={
                                          s.catalog_url ||
                                          `https://planetarycomputer.microsoft.com/api/stac/v1/collections/${s.collection}/items/${s.id}`
                                        }
                                        target="_blank"
                                        rel="noreferrer"
                                      >
                                        {s.collection} · {s.datetime.slice(0, 10)}{" "}
                                        <ArrowUpRight size={12} />
                                      </a>
                                    </li>
                                  ))}
                                </ul>
                                {j.result.limitations.map((l) => (
                                  <p key={l}>{l}</p>
                                ))}
                              </details>
                              <div className="job-actions">
                                <button
                                  className="button secondary small"
                                  onClick={() =>
                                    setCompareJob(compareJob === j.id ? null : j.id)
                                  }
                                >
                                  <Layers3 size={14} />{" "}
                                  {compareJob === j.id
                                    ? "Hide imagery"
                                    : "Compare source imagery"}
                                </button>
                                <button
                                  className="button secondary small"
                                  onClick={() =>
                                    act(async () => {
                                      await downloadJob(j.id);
                                    })
                                  }
                                >
                                  <ArrowDownToLine size={14} /> Export GeoJSON
                                </button>
                                <button
                                  className="button secondary small"
                                  disabled={busy}
                                  onClick={() =>
                                    act(async () => {
                                      const b = await api<Brief>(
                                        `/jobs/${j.id}/brief`,
                                        {
                                          method: "POST",
                                        },
                                      );
                                      setActiveBrief(b);
                                      await refresh();
                                      open("brief");
                                    })
                                  }
                                >
                                  <Sparkles size={14} /> Generate AI brief
                                </button>
                                <button
                                  className="inline-link"
                                  onClick={() => go("Candidates")}
                                >
                                  Review candidates <ArrowRight size={14} />
                                </button>
                              </div>
                              {compareJob === j.id && (
                                <Suspense
                                  fallback={
                                    <p className="panel-subtitle">
                                      Loading comparison…
                                    </p>
                                  }
                                >
                                  <EvidenceCompare job={j} />
                                </Suspense>
                              )}
                            </>
                          )}
                        </article>
                      ))}
                  </div>
                )}
              </section>
            </>
          )}
          {tab === "Candidates" && (
            <>
              <CandidateCharts alerts={alerts} onFilter={setFilter} />
              <section className="panel">
                <div className="panel-title">
                  <span>
                    <ShieldCheck size={17} /> Review queue
                  </span>
                  <div className="review-filters">
                    <input
                      className="compact-input"
                      placeholder="Search area…"
                      aria-label="Filter candidates by area"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                    <select
                      aria-label="Filter review status"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                    >
                      <option value="all">All statuses</option>
                      {["new", "investigating", "confirmed", "dismissed"].map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                </div>
                {!visibleAlerts.length ? (
                  <Empty icon={ShieldCheck} title="Room for the evidence">
                    Change candidates appear after an analysis completes. Every review
                    decision is saved to the audit log.
                  </Empty>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>STUDY AREA</th>
                          <th>CHANGE AREA</th>
                          <th>EVIDENCE INDEX</th>
                          <th>CONCESSION CONTEXT</th>
                          <th>REVIEW</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {visibleAlerts.map((a) => (
                          <tr key={a.id}>
                            <td>
                              <strong>{a.area_name}</strong>
                              <small>{formatDate(a.created_at)}</small>
                            </td>
                            <td>{a.area_ha.toFixed(2)} ha</td>
                            <td>
                              {a.score.toFixed(3)}
                              <small>Uncalibrated score</small>
                            </td>
                            <td>{a.legal_context.replaceAll("_", " ")}</td>
                            <td>
                              <Badge
                                tone={a.status === "confirmed" ? "green" : "neutral"}
                              >
                                {a.status}
                              </Badge>
                            </td>
                            <td>
                              <button
                                className="icon-button"
                                title="Review candidate"
                                onClick={() => {
                                  setActiveAlert(a);
                                  open("alert");
                                }}
                              >
                                <ArrowUpRight size={17} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="panel-footnote">
                  A disturbance candidate is not proof of illegal mining. Legal context
                  only reflects the boundaries you supplied.
                </p>
              </section>
            </>
          )}
          {tab === "Concessions" && (
            <section className="panel">
              <div className="panel-title">
                <span>
                  <FileJson size={17} /> Concession registry
                </span>
                <button
                  className="button secondary small"
                  onClick={() => requireAuth("concession")}
                >
                  <UploadCloud size={15} /> Import boundaries
                </button>
              </div>
              {!concessions.length ? (
                <Empty icon={Layers3} title="Context comes from the source">
                  Import authoritative GeoJSON with its issuing authority, source link,
                  and validity dates. The system will never assume a missing concession
                  means illegal activity.
                </Empty>
              ) : (
                <div className="concession-grid">
                  {concessions.map((c) => (
                    <article className="concession-card" key={c.id}>
                      <FileJson size={22} />
                      <h3>{c.name}</h3>
                      <p>{c.authority}</p>
                      <span>
                        {c.valid_from} → {c.valid_to}
                      </span>
                      <a href={c.source_url} target="_blank" rel="noreferrer">
                        Original source <SquareArrowOutUpRight size={13} />
                      </a>
                      <button
                        className="inline-link danger"
                        onClick={() =>
                          act(async () => {
                            await api(`/concessions/${c.id}`, {
                              method: "DELETE",
                            });
                            await refresh();
                            notify(
                              "Boundary removed. Existing analysis provenance is retained.",
                            );
                          })
                        }
                      >
                        <Trash2 size={13} /> Remove boundary
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}
          {tab === "System" && (
            <div className="system-grid">
              <OperationsPanel />
              <section className="panel">
                <div className="panel-title">
                  <span>
                    <Settings2 size={17} /> Connections & readiness
                  </span>
                  <button
                    className="icon-button"
                    title="Refresh service health"
                    onClick={() =>
                      act(async () => {
                        setSystem(await api<System>("/system"));
                        notify("Service configuration refreshed.");
                      })
                    }
                  >
                    <Activity size={17} />
                  </button>
                </div>
                {[
                  [
                    "Neon Postgres",
                    system?.database === "connected",
                    "Durable workspaces, jobs, decisions, and events.",
                  ],
                  [
                    "Sentinel-1 RTC source",
                    !!system?.radar_access,
                    system?.radar_provider === "digital-earth-africa"
                      ? "Public Digital Earth Africa · Africa coverage · 30m analysis."
                      : "Planetary Computer · configured provider access.",
                  ],
                  [
                    "OpenRouter analyst",
                    !!system?.ai,
                    "Free AI briefs grounded in completed observations.",
                  ],
                  [
                    "GeoMine-XNet checkpoint",
                    !!system?.model_available,
                    "Validated safetensors checkpoint and manifest.",
                  ],
                  [
                    "Realtime event stream",
                    connected,
                    "Authenticated event replay with reconnect.",
                  ],
                ].map(([name, ok, desc]) => (
                  <div className="connection-row" key={String(name)}>
                    <span className={`status-icon ${ok ? "ready" : ""}`}>
                      {ok ? <Check size={17} /> : <Code2 size={17} />}
                    </span>
                    <div>
                      <strong>{name}</strong>
                      <small>{desc}</small>
                    </div>
                    <Badge tone={ok ? "green" : "neutral"}>
                      {ok ? "Configured" : "Setup needed"}
                    </Badge>
                  </div>
                ))}
                {connectionAttempted && !system && (
                  <p className="form-error">
                    The observation service is unavailable. Try again or contact your
                    workspace operator.
                  </p>
                )}
                <p className="panel-footnote">
                  No training checkpoint is bundled. Model accuracy is reported only
                  from an actual held-out validation run.
                </p>
              </section>
              <section className="panel">
                <div className="panel-title">
                  <span>
                    <Fingerprint size={17} /> Activity trail
                  </span>
                  <Badge>{audit.length}</Badge>
                </div>
                {audit.length ? (
                  <div className="audit-list">
                    {audit.slice(0, 12).map((a) => (
                      <div key={a.id}>
                        <span className="audit-point" />
                        <div>
                          <strong>{a.action.replaceAll(".", " · ")}</strong>
                          <small>
                            {formatDate(a.created_at)} · {a.resource_id.slice(0, 8)}
                          </small>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Empty icon={Fingerprint} title="Decisions leave a trace">
                    Your workspace changes and candidate reviews will appear here.
                  </Empty>
                )}
              </section>
              <section className="panel">
                <div className="panel-title">
                  <span>
                    <Radar size={17} /> Monitoring controls
                  </span>
                </div>
                {areas.map((a) => (
                  <div className="monitor-row" key={a.id}>
                    <div>
                      <strong>{a.name}</strong>
                      <small>
                        {a.monitoring
                          ? `Every ${a.interval_hours} hours · next check ${a.next_run_at ? formatDate(a.next_run_at) : "pending"}`
                          : "On-demand analysis only"}
                      </small>
                    </div>
                    <button
                      className={`toggle ${a.monitoring ? "on" : ""}`}
                      role="switch"
                      aria-checked={a.monitoring}
                      aria-label={`Monitor ${a.name}`}
                      onClick={() =>
                        act(async () => {
                          await api(`/areas/${a.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({
                              monitoring: !a.monitoring,
                              interval_hours: 24,
                            }),
                          });
                          await refresh();
                        })
                      }
                    >
                      <span />
                    </button>
                  </div>
                ))}
                {!areas.length && (
                  <p className="panel-subtitle">
                    Add a study area to enable scheduled daily checks.
                  </p>
                )}
                <p className="panel-footnote">
                  Scheduled checks compare recent acquisition windows using the physical
                  detector. New observations depend on satellite revisits and catalog
                  availability.
                </p>
              </section>
            </div>
          )}
          {tab === "Reports" && (
            <div className="reports-layout">
              <section className="panel">
                <div className="panel-title">
                  <span>
                    <FileText size={17} /> Analyst briefs
                  </span>
                  <Badge>{briefs.length}</Badge>
                </div>
                {briefs.length ? (
                  briefs.map((b) => (
                    <button
                      className="brief-row"
                      key={b.id}
                      onClick={() => {
                        setActiveBrief(b);
                        open("brief");
                      }}
                    >
                      <Sparkles size={17} />
                      <span>
                        {jobs.find((j) => j.id === b.job_id)?.area_name ||
                          "Analysis brief"}
                        <small>
                          {formatDate(b.created_at)} · {b.model}
                        </small>
                      </span>
                      <ArrowUpRight size={16} />
                    </button>
                  ))
                ) : (
                  <Empty icon={FileText} title="An observation worth explaining">
                    Open a completed analysis to generate a brief grounded in its actual
                    results.
                    <Link to="/app/analyses" className="inline-link">
                      View analyses <ArrowRight size={14} />
                    </Link>
                  </Empty>
                )}
              </section>
              <section className="panel">
                <div className="panel-title">
                  <span>
                    <ArrowDownToLine size={17} /> Evidence exports
                  </span>
                </div>
                {jobs.some((j) => j.status === "completed") ? (
                  jobs
                    .filter((j) => j.status === "completed")
                    .map((j) => (
                      <div className="export-row" key={j.id}>
                        <div>
                          <strong>{j.area_name || "Study area"}</strong>
                          <small>
                            {formatDate(j.created_at)} ·{" "}
                            {j.result?.candidate_count ?? 0} candidates
                          </small>
                        </div>
                        <button
                          className="button secondary small"
                          onClick={() => act(() => downloadJob(j.id))}
                        >
                          GeoJSON <ArrowDownToLine size={14} />
                        </button>
                      </div>
                    ))
                ) : (
                  <Empty icon={ArrowDownToLine} title="The evidence travels with you">
                    Completed analyses can be exported with candidate geometry, source
                    acquisitions, and processing context.
                  </Empty>
                )}
              </section>
            </div>
          )}
        </main>
        <div className="app-status-footer">
          <span>GEOMINE-XNET · PRIVATE WORKSPACE</span>
          <span>
            {lastUpdated
              ? `Data refreshed ${new Date(lastUpdated).toLocaleTimeString()}`
              : "Waiting for workspace data"}
          </span>
        </div>
      </div>
      <AnimatePresence>
        {toast && (
          <motion.div
            className="toast"
            role="status"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
          >
            <Bell size={17} />
            <span>{toast}</span>
            <button
              className="icon-button"
              aria-label="Dismiss notification"
              onClick={() => setToast("")}
            >
              <X size={16} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {modal && (
          <Modal
            title={
              modal === "area"
                ? "A place worth watching."
                : modal === "analysis"
                  ? "Look at what changed."
                  : modal === "concession"
                    ? "Add the legal context."
                    : modal === "alert"
                      ? "Review the evidence."
                      : "The analyst’s perspective."
            }
            onClose={close}
          >
            {modal === "area" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  act(async () => {
                    const geometry =
                      draftGeometry || JSON.parse(String(data.get("geometry")));
                    const a = await api<Area>("/areas", {
                      method: "POST",
                      body: JSON.stringify({
                        name: data.get("name"),
                        geometry,
                      }),
                    });
                    await refresh();
                    setSelected(a);
                    setDraftGeometry(null);
                    close();
                    go("Observatory");
                    notify("Study area saved.");
                  });
                }}
              >
                <label>
                  Study area name
                  <input
                    name="name"
                    required
                    minLength={2}
                    maxLength={100}
                    placeholder="e.g. Upper watershed"
                  />
                </label>
                {draftGeometry ? (
                  <div className="geometry-ready">
                    <CheckCircle2 size={19} />
                    <span>
                      Map boundary selected
                      <small>
                        {center(draftGeometry)
                          .map((v) => v.toFixed(4))
                          .join(", ")}{" "}
                        · WGS 84
                      </small>
                    </span>
                    <button
                      type="button"
                      className="inline-link"
                      onClick={() => setDraftGeometry(null)}
                    >
                      Edit
                    </button>
                  </div>
                ) : (
                  <>
                    <label className="upload-label">
                      <UploadCloud size={22} />
                      <strong>Import a GeoJSON boundary</strong>
                      <span>
                        Polygon or MultiPolygon · WGS 84 · up to{" "}
                        {system?.max_aoi_km2 || 25} km²
                      </span>
                      <input
                        type="file"
                        accept=".geojson,.json,application/geo+json"
                        onChange={async (e) => {
                          try {
                            const f = e.target.files?.[0];
                            if (!f) return;
                            if (f.size > 2e6) throw new Error("File exceeds 2 MB.");
                            const g = JSON.parse(await f.text());
                            const geom = g.type === "Feature" ? g.geometry : g;
                            if (!["Polygon", "MultiPolygon"].includes(geom.type))
                              throw new Error(
                                "Choose a Polygon or MultiPolygon GeoJSON.",
                              );
                            setDraftGeometry(geom);
                          } catch (err) {
                            setFormError(String(err));
                          }
                        }}
                      />
                    </label>
                    <label>
                      Or paste GeoJSON
                      <textarea
                        name="geometry"
                        required
                        rows={5}
                        placeholder='{"type":"Polygon","coordinates":[…]}'
                      />
                    </label>
                  </>
                )}
                <FormError message={formError} />
                <button className="button primary full" disabled={busy}>
                  {busy ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}{" "}
                  Save study area
                </button>
              </form>
            )}
            {modal === "analysis" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = Object.fromEntries(new FormData(e.currentTarget));
                  act(async () => {
                    await api<Job>("/jobs", {
                      method: "POST",
                      body: JSON.stringify(data),
                    });
                    await refresh();
                    close();
                    go("Analyses");
                    notify(
                      "Analysis queued. Progress will arrive through the event stream.",
                    );
                  });
                }}
              >
                <label>
                  Study area
                  <select name="area_id" required defaultValue={selected?.id}>
                    {areas.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} · {a.area_km2.toFixed(1)} km²
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Analysis engine
                  <select name="engine">
                    <option value="physical">
                      Physical change detector · actual Sentinel pixels
                    </option>
                    <option
                      value="geomine"
                      disabled={
                        !system?.model_available || system.analysis_resolution_m !== 10
                      }
                    >
                      GeoMine-XNet ·{" "}
                      {system?.model_available
                        ? "validated checkpoint"
                        : "checkpoint required"}
                    </option>
                  </select>
                </label>
                <div className="form-dates">
                  <fieldset>
                    <legend>BEFORE WINDOW</legend>
                    <label>
                      From
                      <input
                        name="before_start"
                        type="date"
                        defaultValue={dateOffset(-90)}
                        required
                      />
                    </label>
                    <label>
                      To
                      <input
                        name="before_end"
                        type="date"
                        defaultValue={dateOffset(-60)}
                        required
                      />
                    </label>
                  </fieldset>
                  <fieldset>
                    <legend>AFTER WINDOW</legend>
                    <label>
                      From
                      <input
                        name="after_start"
                        type="date"
                        defaultValue={dateOffset(-30)}
                        required
                      />
                    </label>
                    <label>
                      To
                      <input
                        name="after_end"
                        type="date"
                        defaultValue={dateOffset(0)}
                        max={dateOffset(0)}
                        required
                      />
                    </label>
                  </fieldset>
                </div>
                <p className="setup-note">
                  <Radar size={17} />{" "}
                  {system?.radar_provider === "digital-earth-africa"
                    ? "Public Africa RTC needs no key and uses a 30m analysis grid. Areas outside its coverage return a data-availability error."
                    : "Using the configured Sentinel-1 RTC provider."}{" "}
                  The physical detector returns uncalibrated disturbance evidence for
                  human review.
                </p>
                <FormError message={formError} />
                <button className="button primary full" disabled={busy}>
                  {busy ? (
                    <Loader2 className="spin" size={16} />
                  ) : (
                    <Activity size={16} />
                  )}{" "}
                  Run analysis
                </button>
              </form>
            )}
            {modal === "concession" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = Object.fromEntries(new FormData(e.currentTarget));
                  act(async () => {
                    await api("/concessions", {
                      method: "POST",
                      body: JSON.stringify({
                        ...data,
                        geojson: JSON.parse(String(data.geojson)),
                      }),
                    });
                    await refresh();
                    close();
                    notify("Concession boundaries imported with source metadata.");
                  });
                }}
              >
                <label>
                  Registry or concession name
                  <input name="name" minLength={2} maxLength={100} required />
                </label>
                <label>
                  Issuing authority
                  <input
                    name="authority"
                    minLength={2}
                    maxLength={200}
                    required
                    placeholder="Official registry or authority"
                  />
                </label>
                <label>
                  Source URL
                  <input
                    name="source_url"
                    type="url"
                    required
                    placeholder="https://…"
                  />
                </label>
                <div className="two-col">
                  <label>
                    Valid from
                    <input name="valid_from" type="date" required />
                  </label>
                  <label>
                    Valid to
                    <input name="valid_to" type="date" required />
                  </label>
                </div>
                <label>
                  GeoJSON file
                  <input
                    type="file"
                    accept=".json,.geojson"
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      if (file.size > 2e6) {
                        setFormError("File exceeds 2 MB.");
                        return;
                      }
                      const text = await file.text();
                      const field = document.getElementById(
                        "concession-geojson",
                      ) as HTMLTextAreaElement;
                      if (field) field.value = text;
                    }}
                  />
                </label>
                <label>
                  GeoJSON
                  <textarea
                    id="concession-geojson"
                    name="geojson"
                    required
                    rows={4}
                    placeholder="Polygon, MultiPolygon, Feature, or FeatureCollection"
                  />
                </label>
                <FormError message={formError} />
                <button className="button primary full" disabled={busy}>
                  <UploadCloud size={16} /> Import boundaries
                </button>
              </form>
            )}
            {modal === "alert" && activeAlert && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = Object.fromEntries(new FormData(e.currentTarget));
                  act(async () => {
                    await api(`/alerts/${activeAlert.id}`, {
                      method: "PATCH",
                      body: JSON.stringify(data),
                    });
                    await refresh();
                    close();
                    notify("Review decision and note saved to the audit log.");
                  });
                }}
              >
                <div className="review-summary">
                  <strong>{activeAlert.area_name}</strong>
                  <span>
                    {activeAlert.area_ha.toFixed(2)} ha · evidence index{" "}
                    {activeAlert.score.toFixed(3)}
                  </span>
                  <Badge>{activeAlert.legal_context.replaceAll("_", " ")}</Badge>
                </div>
                <p className="setup-note">
                  <ShieldCheck size={18} /> This score is not a calibrated probability
                  of mining. Confirming records your review decision; it does not
                  establish a legal violation.
                </p>
                <label>
                  Review decision
                  <select name="status" defaultValue={activeAlert.status}>
                    {["new", "investigating", "confirmed", "dismissed"].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Evidence and notes
                  <textarea
                    name="note"
                    defaultValue={activeAlert.note}
                    maxLength={4000}
                    rows={5}
                    placeholder="What does the evidence support? What needs field verification?"
                  />
                </label>
                <FormError message={formError} />
                <button className="button primary full" disabled={busy}>
                  <Check size={16} /> Save review
                </button>
              </form>
            )}
            {modal === "brief" && activeBrief && (
              <div className="brief-content">
                <Badge tone="green">AI GENERATED · REVIEW REQUIRED</Badge>
                <BriefNarrative text={activeBrief.content} />
                <small>
                  {activeBrief.model} · {formatDate(activeBrief.created_at)}
                </small>
              </div>
            )}
          </Modal>
        )}
      </AnimatePresence>
    </div>
  );
}
function FormError({ message }: { message: string }) {
  return message ? (
    <p className="form-error" role="alert">
      {message}
    </p>
  ) : null;
}
