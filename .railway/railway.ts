// EchoCare on Railway (ADR-001): one file for every environment.
// Railway never reads this file during a deploy; a person applies it from .railway/:
//   railway config plan --environment staging
//   railway config apply --environment staging
import { bucket, defineRailway, github, postgres, preserve, project, service } from "railway/iac";

const REPO = "paulhondola/EchoCare";
const REGION = "europe-west4-drams3a"; // EU West
// Each environment deploys from its own branch; promotion is a PR from main into release.
const BRANCH: Record<string, string> = { staging: "main", production: "release" };
// Firebase web config: public identifiers that ship in the browser bundle, not secrets.
// One Firebase project serves every environment (ADR-001). Same values as dashboard/.env.
const FIREBASE_WEB = {
  VITE_FIREBASE_API_KEY: "AIzaSyC1a4PXcIBmNCvKb5W3us7WWwoD7xjPWkw",
  VITE_FIREBASE_AUTH_DOMAIN: "echocare-app.firebaseapp.com",
  VITE_FIREBASE_PROJECT_ID: "echocare-app",
  VITE_FIREBASE_APP_ID: "1:171353703999:web:39b0a68d03a8c8e0391a8a",
};

const unset = Object.entries(FIREBASE_WEB).filter(([, v]) => !v || v === "TODO");
if (unset.length) throw new Error(`Fill in ${unset.map(([k]) => k).join(", ")} in railway.ts`);

export default defineRailway((ctx) => {
  const env = ctx.environment;
  const branch = env && BRANCH[env];
  if (!env || !branch) throw new Error(`No branch for Railway environment "${env}"`);

  // Postgres database pinned to EU West (europe-west4-drams3a)
  const db = postgres("Postgres", { region: REGION });
  // S3-compatible storage bucket in Europe (Amsterdam)
  const storage = bucket("storage", { region: "ams" });

  const api = service("api", {
    // checkSuites: Wait for CI, so a red workflow never deploys
    source: github(REPO, { branch, rootDirectory: "/backend", checkSuites: true }),
    // watch paths: only backend changes redeploy the API and drop live calls
    build: { builder: "DOCKERFILE", dockerfilePath: "/backend/Dockerfile", watchPatterns: ["/backend/**"] },
    preDeploy: "alembic upgrade head",
    healthcheck: "/api/health",
    replicas: { [REGION]: 1 },
    // drainingSeconds: an old copy keeps its calls (3 min limit) after SIGTERM
    deploy: { sleepApplication: true, drainingSeconds: 200 },
    env: {
      APP_ENV: env,
      DATABASE_URL: db.env.DATABASE_URL,
      // ${{...}} is Railway's own reference syntax, resolved at deploy time
      PUBLIC_BASE_URL: "https://${{RAILWAY_PUBLIC_DOMAIN}}",
      ALLOWED_ORIGIN: "https://${{dashboard.RAILWAY_PUBLIC_DOMAIN}}",
      // S3-compatible bucket storage
      S3_BUCKET_NAME: "${{storage.BUCKET_NAME}}",
      S3_ENDPOINT: "${{storage.BUCKET_ENDPOINT}}",
      S3_ACCESS_KEY_ID: "${{storage.BUCKET_ACCESS_KEY_ID}}",
      S3_SECRET_ACCESS_KEY: "${{storage.BUCKET_SECRET_ACCESS_KEY}}",
      S3_REGION: "ams",
      // Twilio (04 §4), set by a person with `railway variable set`; apply keeps them
      TWILIO_ACCOUNT_SID: preserve(),
      TWILIO_AUTH_TOKEN: preserve(),
      TWILIO_FROM_NUMBER: preserve(),
    },
  });

  const dashboard = service("dashboard", {
    source: github(REPO, { branch, rootDirectory: "/dashboard", checkSuites: true }),
    build: { builder: "DOCKERFILE", watchPatterns: ["/dashboard/**"] },
    replicas: { [REGION]: 1 },
    deploy: { sleepApplication: true },
    // Vite writes this into the bundle at build time (an ARG in the Dockerfile)
    env: { VITE_API_URL: "https://${{api.RAILWAY_PUBLIC_DOMAIN}}", ...FIREBASE_WEB },
  });

  return project("EchoCare", { resources: [api, dashboard, db, storage] });
});
