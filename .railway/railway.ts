// EchoCare on Railway (ADR-001): one file for every environment.
// Railway never reads this file during a deploy; a person applies it from .railway/:
//   railway config plan --environment staging
//   railway config apply --environment staging
import { bucket, defineRailway, github, postgres, preserve, project, service } from "railway/iac";

const REPO = "paulhondola/EchoCare";
const REGION = "europe-west4-drams3a"; // EU West
// Each environment deploys from its own branch; promotion is a PR from main into release.
const BRANCH: Record<string, string> = { staging: "main", production: "release" };
// Public hosts, written out instead of ${{...RAILWAY_PUBLIC_DOMAIN}}: Railway resolved that reference to the
// pre-rename domain after the Sentinela → EchoCare rename. Generate the domains with `railway domain` (README),
// and change a host here when you change its domain; apply then redeploys the service that reads it.
const HOSTS: Record<string, { api: string; dashboard: string }> = {
  staging: { api: "echocare-api-staging.up.railway.app", dashboard: "echocare-dashboard-staging.up.railway.app" },
  production: { api: "echocare-api-prod.up.railway.app", dashboard: "echocare-dashboard-prod.up.railway.app" },
};
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
  const host = env && HOSTS[env];
  if (!env || !branch || !host) throw new Error(`No branch or hosts for Railway environment "${env}"`);

  // Postgres database pinned to EU West (europe-west4-drams3a)
  const db = postgres("Postgres", { region: REGION });
  db.deploy = { ...db.deploy, sleepApplication: true };
  // S3-compatible storage bucket in Europe (Amsterdam)
  const storage = bucket("storage", { region: "ams" });

  const api = service("api", {
    // checkSuites: Wait for CI, so a red workflow never deploys
    source: github(REPO, { branch, rootDirectory: "/backend", checkSuites: true }),
    // watch paths: only backend changes redeploy the API and drop live calls
    build: { builder: "DOCKERFILE", dockerfilePath: "/backend/Dockerfile", watchPatterns: ["/backend/**"] },
    // run DB migrations
    preDeploy: "alembic upgrade head",
    // Health Endpoint
    healthcheck: "/api/health",
    replicas: { [REGION]: 1 },
    // Enable serverless
    deploy: { sleepApplication: true },
    env: {
      APP_ENV: env,
      DATABASE_URL: db.env.DATABASE_URL,
      PUBLIC_BASE_URL: `https://${host.api}`,
      ALLOWED_ORIGIN: `https://${host.dashboard}`,
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
      // DeepInfra, the agent's model (04 §5), set by a person; apply keeps it
      DEEPINFRA_API_KEY: preserve(),
      // Firebase push (04 §6): a Google credential's JSON, set by a person; unset sends none
      FIREBASE_PUSH_CREDENTIALS: preserve(),
    },
  });

  const dashboard = service("dashboard", {
    source: github(REPO, { branch, rootDirectory: "/dashboard", checkSuites: true }),
    build: { builder: "DOCKERFILE", dockerfilePath: "/dashboard/Dockerfile", watchPatterns: ["/dashboard/**"] },
    replicas: { [REGION]: 1 },
    // Enable Serverless
    deploy: { sleepApplication: true },
    // Vite writes this into the bundle at build time (an ARG in the Dockerfile)
    env: { VITE_API_URL: `https://${host.api}`, ...FIREBASE_WEB },
  });

  return project("EchoCare", { resources: [api, dashboard, db, storage] });
});
