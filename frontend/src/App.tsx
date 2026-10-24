import { lazy, Suspense, useEffect } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
  Link,
} from "react-router";
import { Loader2 } from "lucide-react";
import Landing from "./pages/Landing";
import Auth from "./pages/Auth";
const Workspace = lazy(() => import("./Workspace"));
function ScrollReset() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
    if (!pathname.startsWith("/app/"))
      document.title =
        pathname === "/"
          ? "GeoMine — Earth intelligence, in focus."
          : `${pathname === "/login" ? "Log in" : pathname === "/forgot-password" ? "Reset password" : "Create workspace"} · GeoMine`;
  }, [pathname]);
  return null;
}
export default function App() {
  return (
    <BrowserRouter>
      <ScrollReset />
      <Suspense
        fallback={
          <div className="app-loading" role="status">
            <Loader2 className="spin" /> Opening GeoMine…
          </div>
        }
      >
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Auth key="login" mode="login" />} />
          <Route path="/signup" element={<Auth key="register" mode="register" />} />
          <Route path="/forgot-password" element={<Auth key="reset" mode="reset" />} />
          <Route path="/app" element={<Navigate to="/app/overview" replace />} />
          <Route path="/app/*" element={<Workspace />} />
          <Route
            path="*"
            element={
              <main className="not-found">
                <h1>A little off course.</h1>
                <p>This page does not exist.</p>
                <Link to="/" className="button primary">
                  Return to Earth
                </Link>
              </main>
            }
          />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
