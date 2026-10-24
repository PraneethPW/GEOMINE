// Vercel must call the real Railway API; never publish a localhost or unset API URL.
const value = process.env.VITE_API_URL?.trim();
if (!value) {
  throw new Error(
    "Set VITE_API_URL to the HTTPS origin of the deployed Railway API in Vercel project environment variables.",
  );
}
let url;
try {
  url = new URL(value);
} catch {
  throw new Error("VITE_API_URL must be a valid HTTPS origin.");
}
const host = url.hostname.toLowerCase();
if (
  url.protocol !== "https:" ||
  url.username ||
  url.password ||
  url.search ||
  url.hash ||
  (url.pathname !== "/" && url.pathname !== "")
) {
  throw new Error(
    "VITE_API_URL must contain only an HTTPS origin, without credentials, path, query, or fragment.",
  );
}
if (
  host === "localhost" ||
  host.endsWith(".localhost") ||
  host.endsWith(".local") ||
  host.endsWith(".internal") ||
  host === "[::1]" ||
  /^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host)
) {
  throw new Error(
    "VITE_API_URL must be reachable by a public browser; a loopback or private address cannot be used.",
  );
}
console.log("Deployment API origin is configured.");
