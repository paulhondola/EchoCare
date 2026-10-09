// Sentinela on Railway (ADR-001): one file for every environment.
// Railway never reads this file during a deploy; a person applies it from .railway/:
//   railway config plan --environment staging
//   railway config apply --environment staging
import { defineRailway, github, postgres, project, service } from "railway/iac";

const REPO = "paulhondola/Sentinela-Test";
const REGION = "europe-west4-drams3a"; // EU West
// Each environment deploys from its own branch; promotion is a PR from main into release.
const BRANCH: Record<string, string> = { staging: "main", production: "release" };
// Firebase web config: public identifiers that ship in the browser bundle, not secrets.
// One Firebase project serves every environment (ADR-001). Same values as dashboard/.env.
const FIREBASE_WEB = {
  VITE_FIREBASE_API_KEY: "AIzaSyBWFvTyqk904SsoT_uFXIzXgyHBBxhz5m0",
  VITE_FIREBASE_AUTH_DOMAIN: "sentinela-8f474.firebaseapp.com",
  VITE_FIREBASE_PROJECT_ID: "sentinela-8f474",
  VITE_FIREBASE_APP_ID: "1:994957703097:web:2bbc70f74e432f74af6868",
};

const unset = Object.entries(FIREBASE_WEB).filter(([, v]) => !v || v === "TODO");
if (unset.length) throw new Error(`Fill in ${unset.map(([k]) => k).join(", ")} in railway.ts`);

export default defineRailway((ctx) => {
  const env = ctx.environment;
  const branch = env && BRANCH[env];
  if (!env || !branch) throw new Error(`No branch for Railway environment "${env}"`);

  const db = postgres("Postgres");

  const api = service("api", {
    // checkSuites: Wait for CI, so a red workflow never deploys
    source: github(REPO, { branch, rootDirectory: "/backend", checkSuites: true }),
    // watch paths: only backend changes redeploy the API and drop live calls
    build: { builder: "DOCKERFILE", watchPatterns: ["/backend/**"] },
    preDeploy: "alembic upgrade head",
    healthcheck: "/health",
    replicas: { [REGION]: 1 },
    // drainingSeconds: an old copy keeps its calls (3 min limit) after SIGTERM
    deploy: { sleepApplication: false, drainingSeconds: 200 },
    env: {
      APP_ENV: env,
      DATABASE_URL: db.env.DATABASE_URL,
      // ${{...}} is Railway's own reference syntax, resolved at deploy time
      PUBLIC_BASE_URL: "https://${{RAILWAY_PUBLIC_DOMAIN}}",
      ALLOWED_ORIGIN: "https://${{dashboard.RAILWAY_PUBLIC_DOMAIN}}",
    },
  });

  const dashboard = service("dashboard", {
    source: github(REPO, { branch, rootDirectory: "/dashboard", checkSuites: true }),
    build: { builder: "DOCKERFILE", watchPatterns: ["/dashboard/**"] },
    replicas: { [REGION]: 1 },
    // Vite writes this into the bundle at build time (an ARG in the Dockerfile)
    env: { VITE_API_URL: "https://${{api.RAILWAY_PUBLIC_DOMAIN}}", ...FIREBASE_WEB },
  });

  return project("Sentinela", { resources: [api, dashboard, db] });
});
