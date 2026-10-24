import { lazy, Suspense, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ArrowLeft, ArrowRight, Fingerprint, Loader2 } from "lucide-react";
import { API, api, ApiError, setToken, token } from "../api";
import type { FirebaseOptions } from "firebase/app";
import type { System, User } from "../api";
import Brand from "../components/Brand";

const ManagedAuth = lazy(() => import("./ManagedAuth"));
export default function Auth({ mode }: { mode: "login" | "register" | "reset" }) {
  const [search] = useSearchParams();
  const [configuration, setConfiguration] = useState<{
    provider: string;
    firebase: FirebaseOptions | null;
  } | null>(null);
  const [failure, setFailure] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API}/api/auth/config`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Identity service unavailable");
        setConfiguration(await response.json());
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailure(true);
      });
    return () => controller.abort();
  }, []);
  if (failure)
    return (
      <main className="app-loading">
        <div>
          <h1>Sign-in is temporarily unavailable.</h1>
          <p role="alert">The identity service could not be reached.</p>
          <button className="button primary" onClick={() => window.location.reload()}>
            Retry connection
          </button>
        </div>
      </main>
    );
  if (!configuration)
    return (
      <div className="app-loading" role="status">
        <Loader2 className="spin" /> Checking sign-in…
      </div>
    );
  if (
    configuration.provider === "firebase" &&
    configuration.firebase &&
    search.get("legacy") !== "1"
  )
    return (
      <Suspense
        fallback={
          <div className="app-loading" role="status">
            Opening secure sign-in…
          </div>
        }
      >
        <ManagedAuth mode={mode} config={configuration.firebase} />
      </Suspense>
    );
  if (mode === "reset")
    return (
      <main className="app-loading">
        <div>
          <h1>Recovery setup is pending.</h1>
          <p>
            Managed authentication must be activated before password recovery is
            available.
          </p>
          <Link className="button primary" to="/login">
            Return to login
          </Link>
        </div>
      </main>
    );
  return <LegacyAuth mode={mode} />;
}
function LegacyAuth({ mode }: { mode: "login" | "register" }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [registration, setRegistration] = useState<boolean | null>(null);
  const navigate = useNavigate(),
    [search] = useSearchParams();
  const requested = search.get("next"),
    next =
      requested?.startsWith("/app/") && !requested.includes("\\")
        ? requested
        : "/app/overview";
  useEffect(() => {
    let active = true;
    if (token())
      api<User>("/auth/me")
        .then(() => {
          if (active) navigate(next, { replace: true });
        })
        .catch((error) => {
          if (error instanceof ApiError && error.status === 401) setToken("");
          else if (active)
            setError("Unable to check your existing session. Please retry shortly.");
        });
    if (mode === "register")
      api<System>("/system")
        .then((s) => {
          if (active) setRegistration(s.registration);
        })
        .catch(() => {
          if (active)
            setError("The service is temporarily unavailable. Please try again.");
        });
    return () => {
      active = false;
    };
  }, [mode, navigate, next]);
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      const result = await api<{ token: string; user: User }>(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({
          name: data.get("name") || "Analyst",
          email: data.get("email"),
          password: data.get("password"),
        }),
      });
      setToken(result.token);
      navigate(next, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to connect. Please try again.");
    } finally {
      setBusy(false);
    }
  };
  const signup = mode === "register";
  return (
    <main className="auth-page">
      <section className="auth-story">
        <Brand />
        <div>
          <span className="eyebrow">A PRIVATE PERSPECTIVE</span>
          <h1>
            A little closer.
            <br />
            <span>A lot clearer.</span>
          </h1>
          <p>
            Your study areas. Your observations.
            <br />A continuous record of what changes.
          </p>
        </div>
        <div className="auth-contours" aria-hidden="true" />
        <span className="auth-story-foot">
          <Fingerprint size={16} /> Evidence belongs in context.
        </span>
      </section>
      <section className="auth-form-section">
        <Link to="/" className="auth-back">
          <ArrowLeft size={15} /> Back to Earth
        </Link>
        <div className="auth-form-wrap">
          <span className="eyebrow">
            {signup ? "START YOUR OBSERVATORY" : "WELCOME BACK"}
          </span>
          <h2>{signup ? "A place to look closer." : "Return to your workspace."}</h2>
          <p>
            {signup
              ? "Create an account to save areas, run analyses, and follow the evidence."
              : "Sign in to your observations, investigations, and reports."}
          </p>
          <form onSubmit={submit}>
            {signup && (
              <label>
                Your name
                <input
                  name="name"
                  required
                  maxLength={80}
                  autoComplete="name"
                  placeholder="Full name"
                />
              </label>
            )}
            <label>
              Email address
              <input
                type="email"
                name="email"
                required
                autoComplete="email"
                placeholder="you@organization.com"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                name="password"
                minLength={12}
                maxLength={128}
                required
                autoComplete={signup ? "new-password" : "current-password"}
                placeholder={signup ? "At least 12 characters" : "Your password"}
              />
            </label>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            {signup && registration === false && (
              <p className="form-error">
                Registration is currently closed. Contact your workspace operator.
              </p>
            )}
            <button
              className="button primary full"
              disabled={busy || (signup && registration === false)}
            >
              {busy ? <Loader2 size={17} className="spin" /> : <ArrowRight size={17} />}{" "}
              {busy ? "Connecting…" : signup ? "Create workspace" : "Log in"}
            </button>
          </form>
          <p className="auth-alternate">
            {signup ? "Already have a workspace?" : "New to GeoMine?"}{" "}
            <Link
              to={`${signup ? "/login" : "/signup"}${requested ? `?next=${encodeURIComponent(next)}` : ""}`}
            >
              {signup ? "Log in" : "Create an account"} <ArrowRight size={13} />
            </Link>
          </p>
          <div className="auth-privacy">
            <Fingerprint size={16} /> Your saved observations are private to your
            account.
          </div>
        </div>
        <small className="auth-footer-note">GEOMINE-XNET · EARTH INTELLIGENCE</small>
      </section>
    </main>
  );
}
