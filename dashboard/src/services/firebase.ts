import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

// The public web config (auth-layer §7.1). getAuth's default persistence keeps a desk session across reloads.
const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
});

export const auth = getAuth(app);

// Dev server only, like Android debug builds (auth-layer §8.2): Firebase test numbers sign in
// without a reCAPTCHA challenge. Real numbers still fail without one; the production bundle never sets it.
if (import.meta.env.DEV) auth.settings.appVerificationDisabledForTesting = true;
