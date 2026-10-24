import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import {
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  reload,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  updateProfile,
} from "firebase/auth";
import type { FirebaseOptions } from "firebase/app";
import type { Auth } from "firebase/auth";
import { ArrowLeft, ArrowRight, Fingerprint, Loader2, Mail } from "lucide-react";
import { api, ApiError, setToken } from "../api";
import { managedAuth } from "../managedIdentity";
import Brand from "../components/Brand";

type Mode = "login" | "register" | "reset";
function message(error: unknown) {
  const code =
    typeof error === "object" && error && "code" in error ? String(error.code) : "";
  const messages: Record<string, string> = {
    "auth/invalid-credential": "Email or password is incorrect.",
    "auth/invalid-email": "Enter a valid email address.",
    "auth/email-already-in-use":
      "This sign-in already exists. Log in or reset your password.",
    "auth/popup-closed-by-user": "Google sign-in was closed before completing.",
    "auth/popup-blocked": "Allow the sign-in popup, then try again.",
    "auth/too-many-requests": "Too many attempts. Wait a little before retrying.",
    "auth/network-request-failed":
      "The identity service could not be reached. Please retry.",
    "auth/weak-password": "Choose a stronger password with at least 12 characters.",
    "auth/account-exists-with-different-credential":
      "Sign in using your existing method for this email first.",
  };
  return (
    messages[code] ||
    (error instanceof ApiError
      ? error.message
      : "Sign-in could not be completed. Please retry.")
  );
}
export default function ManagedAuth({
  mode,
  config,
}: {
  mode: Mode;
  config: FirebaseOptions;
}) {
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const requested = search.get("next");
  const next =
    requested?.startsWith("/app/") && !requested.includes("\\")
      ? requested
      : "/app/overview";
  const [auth, setAuth] = useState<Auth | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [verify, setVerify] = useState(false);
  const [linking, setLinking] = useState(false);
  useEffect(() => {
    let active = true;
    managedAuth(config)
      .then((value) => {
        if (!active) return;
        setAuth(value);
        if (value.currentUser && !value.currentUser.emailVerified && mode !== "reset")
          setVerify(true);
      })
      .catch((e) => {
        if (active) setError(message(e));
      });
    return () => {
      active = false;
    };
  }, [config, mode]);
  async function finish(legacyPassword?: string) {
    if (!auth?.currentUser) throw new Error("Sign in first.");
    await reload(auth.currentUser);
    if (!auth.currentUser.emailVerified) {
      setVerify(true);
      return;
    }
    const idToken = await auth.currentUser.getIdToken(true);
    try {
      await api("/auth/firebase", {
        method: "POST",
        body: JSON.stringify({
          id_token: idToken,
          ...(legacyPassword ? { legacy_password: legacyPassword } : {}),
        }),
      });
      setToken(idToken);
      navigate(next, { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setLinking(true);
      throw e;
    }
  }
  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void act(async () => {
      if (!auth) throw new Error("Identity service is loading.");
      if (linking) {
        await finish(String(data.get("legacy_password")));
        return;
      }
      const email = String(data.get("email"));
      if (mode === "reset") {
        await sendPasswordResetEmail(auth, email);
        setNotice(
          "If a managed sign-in exists for this email, a password-reset message will arrive. Check your spam folder too.",
        );
        return;
      }
      if (mode === "register") {
        const result = await createUserWithEmailAndPassword(
          auth,
          email,
          String(data.get("password")),
        );
        await updateProfile(result.user, { displayName: String(data.get("name")) });
        setVerify(true);
        await sendEmailVerification(result.user);
        setNotice("Verification email sent. Open the link, then return here.");
      } else {
        await signInWithEmailAndPassword(auth, email, String(data.get("password")));
        await finish();
      }
    });
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
            {verify
              ? "CONFIRM YOUR EMAIL"
              : linking
                ? "PRESERVE YOUR WORKSPACE"
                : mode === "reset"
                  ? "RECOVER YOUR SIGN-IN"
                  : signup
                    ? "START YOUR OBSERVATORY"
                    : "WELCOME BACK"}
          </span>
          <h2>
            {linking
              ? "Connect your existing observations."
              : verify
                ? "One final check."
                : mode === "reset"
                  ? "Find your way back."
                  : signup
                    ? "A place to look closer."
                    : "Return to your workspace."}
          </h2>
          <p>
            {linking
              ? "Enter your previous GeoMine password to prove ownership. Your areas, analyses, and review history stay with this account."
              : verify
                ? `Verify ${auth?.currentUser?.email || "your email address"} using the link in your inbox.`
                : mode === "reset"
                  ? "Enter the email used for your managed sign-in."
                  : "Secure sign-in and account recovery, managed by Firebase."}
          </p>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="auth-notice" role="status">
              {notice}
            </p>
          )}
          {verify && !linking ? (
            <div className="auth-verification-actions">
              <button
                className="button primary full"
                disabled={busy || !auth}
                onClick={() =>
                  void act(async () => {
                    await finish();
                    if (auth?.currentUser && !auth.currentUser.emailVerified)
                      setNotice(
                        "This email has not been verified yet. Open the link in your inbox first.",
                      );
                  })
                }
              >
                {busy ? (
                  <Loader2 className="spin" size={16} />
                ) : (
                  <ArrowRight size={16} />
                )}{" "}
                I’ve verified my email
              </button>
              <button
                className="button secondary full"
                disabled={busy || !auth?.currentUser}
                onClick={() =>
                  void act(async () => {
                    await sendEmailVerification(auth!.currentUser!);
                    setNotice("A new verification email was sent.");
                  })
                }
              >
                <Mail size={16} /> Resend verification email
              </button>
              <button
                className="inline-link"
                disabled={busy}
                onClick={() =>
                  void act(async () => {
                    await auth?.signOut();
                    setToken("");
                    setVerify(false);
                  })
                }
              >
                Use another account
              </button>
            </div>
          ) : (
            <>
              {!linking && mode !== "reset" && (
                <>
                  <button
                    className="button secondary full google-signin"
                    disabled={busy || !auth}
                    onClick={() =>
                      void act(async () => {
                        await signInWithPopup(auth!, new GoogleAuthProvider());
                        await finish();
                      })
                    }
                  >
                    Continue with Google
                  </button>
                  <p className="auth-divider">or use email</p>
                </>
              )}
              <form onSubmit={submit}>
                {linking ? (
                  <label>
                    Previous GeoMine password
                    <input
                      name="legacy_password"
                      type="password"
                      required
                      minLength={12}
                      maxLength={128}
                      autoComplete="current-password"
                    />
                  </label>
                ) : (
                  <>
                    {signup && (
                      <label>
                        Your name
                        <input
                          name="name"
                          required
                          maxLength={80}
                          autoComplete="name"
                        />
                      </label>
                    )}
                    <label>
                      Email address
                      <input name="email" type="email" required autoComplete="email" />
                    </label>
                    {mode !== "reset" && (
                      <label>
                        Password
                        <input
                          name="password"
                          type="password"
                          minLength={signup ? 12 : undefined}
                          maxLength={128}
                          required
                          autoComplete={signup ? "new-password" : "current-password"}
                        />
                      </label>
                    )}
                  </>
                )}
                <button className="button primary full" disabled={busy || !auth}>
                  {busy ? (
                    <Loader2 className="spin" size={17} />
                  ) : (
                    <ArrowRight size={17} />
                  )}{" "}
                  {busy
                    ? "Connecting…"
                    : linking
                      ? "Link my workspace"
                      : mode === "reset"
                        ? "Send reset email"
                        : signup
                          ? "Create workspace"
                          : "Log in"}
                </button>
              </form>
              {!signup && mode !== "reset" && !linking && (
                <Link className="inline-link auth-recovery" to="/forgot-password">
                  Forgot your password?
                </Link>
              )}
              <p className="auth-alternate">
                {mode === "reset"
                  ? "Remember your sign-in?"
                  : signup
                    ? "Already have a sign-in?"
                    : "New to GeoMine?"}{" "}
                <Link to={mode === "reset" || signup ? "/login" : "/signup"}>
                  {mode === "reset" || signup ? "Log in" : "Create an account"}
                </Link>
              </p>
              <p className="panel-footnote">
                Existing GeoMine workspace? Create a managed sign-in with the same
                email, verify it, then link with your previous GeoMine password.{" "}
                <Link to="/login?legacy=1">
                  Use your existing login during migration.
                </Link>
              </p>
            </>
          )}
        </div>
        <small className="auth-footer-note">GEOMINE-XNET · EARTH INTELLIGENCE</small>
      </section>
    </main>
  );
}
