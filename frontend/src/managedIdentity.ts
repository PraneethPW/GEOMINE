import { initializeApp, getApps } from "firebase/app";
import type { FirebaseOptions } from "firebase/app";
import {
  getAuth,
  setPersistence,
  browserSessionPersistence,
  signOut,
} from "firebase/auth";
import type { Auth } from "firebase/auth";
import { API } from "./api";
let pending: Promise<Auth> | undefined;
export async function managedAuth(config?: FirebaseOptions): Promise<Auth> {
  if (!pending)
    pending = (async () => {
      if (!config) {
        const response = await fetch(`${API}/api/auth/config`);
        if (!response.ok) throw new Error("Unable to check the identity service.");
        const body = await response.json();
        if (body.provider !== "firebase")
          throw new Error("Managed sign-in is unavailable.");
        config = body.firebase;
      }
      const app =
        getApps().find((a) => a.name === "geomine-identity") ||
        initializeApp(config!, "geomine-identity");
      const auth = getAuth(app);
      await setPersistence(auth, browserSessionPersistence);
      await auth.authStateReady();
      return auth;
    })().catch((error) => {
      pending = undefined;
      throw error;
    });
  return pending;
}
export async function freshManagedToken() {
  const auth = await managedAuth();
  return auth.currentUser ? auth.currentUser.getIdToken() : "";
}
export async function managedSignOut() {
  if (pending) await signOut(await pending);
}
