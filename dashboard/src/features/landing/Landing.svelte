<script lang="ts">
  import Icon, { type IconName } from "../../ui/Icon.svelte";

  // What a signed-out visitor sees at the dashboard's address: the system that watches and
  // reacts on its own (UC-09, UC-07, UC-11), with sign-in one button away (auth-layer §7.1).
  let { onSignIn }: { onSignIn: () => void } = $props();

  type Source = "ceas" | "agent" | "senior" | "reguli" | "das";

  // One illustrative incident, step by step: UC-09 into UC-07, then the hand-over of UC-11.
  const STEPS: { at: string; source: Source; text: string; quote?: boolean; delta?: string }[] = [
    { at: "14:20:03", source: "ceas", text: "Puls 128, fără mișcare" },
    { at: "14:20:04", source: "ceas", text: "Vibrează și întreabă „Sunteți bine?”" },
    {
      at: "14:20:34",
      source: "ceas",
      text: "Niciun răspuns. Trimite alerta prin telefon",
      delta: "+30s",
    },
    { at: "14:20:36", source: "agent", text: "Sună pe numărul lui", delta: "+2s" },
    {
      at: "14:20:51",
      source: "agent",
      text: "Domnule Pavel, ceasul arată un puls mare. Cum vă simțiți?",
      quote: true,
    },
    { at: "14:20:58", source: "senior", text: "Mă apasă pe piept…", quote: true },
    { at: "14:20:58", source: "reguli", text: "Frază de alarmă recunoscută. Cod roșu." },
    { at: "14:21:01", source: "das", text: "Apelul trece la dispecerul de serviciu", delta: "+3s" },
  ];

  const SOURCE_LABEL: Record<Source, string> = {
    ceas: "CEAS",
    agent: "AGENT",
    senior: "SENIOR",
    reguli: "REGULI",
    das: "DAS",
  };

  const SOURCE_TONE: Record<Source, string> = {
    ceas: "text-link",
    agent: "text-fg",
    senior: "text-fg-muted",
    reguli: "text-rosu-fg",
    das: "text-verde-fg",
  };

  // What starts a call without anyone asking (UC-09, UC-10, UC-08)
  const TRIGGERS: [string, string][] = [
    ["CEASUL", "Puls mare în repaus, sau „Nu mă simt bine” apăsat pe ecran"],
    ["TELEFONUL", "Seniorul apasă „Sunați-mă” în aplicație"],
    ["APELUL", "Nu răspunde? Agentul sună din nou, apoi anunță familia"],
  ];

  const DOES: { icon: IconName; tone: string; title: string; text: string; sample: string }[] = [
    {
      icon: "watch",
      tone: "text-link",
      title: "Observă",
      text: "Ceasul compară pulsul cu cel obișnuit al purtătorului și cu mișcarea. O plimbare nu declanșează nimic.",
      sample: "puls 128 · repaus · 14:20",
    },
    {
      icon: "phone",
      tone: "text-fg",
      title: "Sună",
      text: "Agentul sună în câteva secunde, vorbește românește și pune trei întrebări simple.",
      sample: "apel · 00:42 · română",
    },
    {
      icon: "scale",
      tone: "text-rosu-fg",
      title: "Decide",
      text: "Codul îl pun reguli fixe; modelul îl poate doar ridica. O frază de alarmă gravă duce direct la roșu.",
      sample: "„mă apasă pe piept” → roșu",
    },
    {
      icon: "headset",
      tone: "text-verde-fg",
      title: "Predă",
      text: "La roșu, apelul trece pe loc la dispecerul DAS, cu dosarul seniorului deschis.",
      sample: "preluat · dispecer · +3s",
    },
  ];

  const STEP_MS = 900;
  const HOLD_MS = 4200;

  // How many steps are showing; STEPS.length + 1 also shows the closing code. A replay is a
  // fresh {#key} for the trace, so its drawing restarts with the steps.
  let shown = $state(0);
  let replay = $state(0);

  $effect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      shown = STEPS.length + 1;
      return;
    }
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      if (shown > STEPS.length) {
        shown = 0;
        replay += 1;
        timer = setTimeout(tick, 500);
      } else {
        shown += 1;
        timer = setTimeout(tick, shown > STEPS.length ? HOLD_MS : STEP_MS);
      }
    };
    timer = setTimeout(tick, 500);
    return () => clearTimeout(timer);
  });
</script>

<div class="landing relative min-h-screen overflow-hidden bg-canvas text-fg">
  <div class="grid-bg" aria-hidden="true"></div>
  <div class="glow" aria-hidden="true"></div>

  <header
    class="relative z-10 flex items-center justify-between border-b border-line px-4 py-3.5 sm:px-8"
  >
    <div class="flex items-center gap-2.5">
      <img src="/favicon.svg" alt="" width="28" height="28" class="size-7" />
      <span class="text-[16px] leading-none font-extrabold tracking-[-0.015em]">ECHOCARE</span>
    </div>
    <button class="sn-btn sn-btn-outline" onclick={onSignIn}>Intrați în cont</button>
  </header>

  <main class="relative z-10">
    <section
      class="mx-auto grid max-w-[1200px] items-start gap-12 px-4 pt-14 pb-14 sm:px-8 lg:grid-cols-[1fr_520px] lg:gap-14 lg:pt-20 lg:pb-16"
    >
      <div>
        <h1 class="hero-title">Nimeni nu trebuie să observe <em>primul.</em></h1>
        <p class="mb-8 max-w-[40ch] text-[17px] leading-normal text-fg-soft">
          EchoCare urmărește semnalele de la ceas și telefon, sună singur seniorul în câteva secunde
          și cheamă un om doar când e nevoie de el.
        </p>
        <dl class="max-w-[460px] border-t border-line">
          {#each TRIGGERS as [what, when] (what)}
            <div class="grid grid-cols-[96px_1fr] gap-3.5 border-b border-line py-2.5">
              <dt
                class="font-mono text-[11px] leading-[1.7] font-bold tracking-[0.06em] text-fg-muted"
              >
                {what}
              </dt>
              <dd class="text-[14px] text-fg-soft">{when}</dd>
            </div>
          {/each}
        </dl>
      </div>

      <figure class="panel m-0" aria-label="Exemplu: de la un puls mare la dispecerul DAS">
        <div
          class="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5 text-[12.5px] text-fg-soft"
        >
          <span>Exemplu · Gheorghe Pavel, 84</span>
          <span class="live">ÎN DESFĂȘURARE</span>
        </div>
        <div class="relative border-b border-line px-4 pt-2 pb-1">
          {#key replay}
            <svg class="trace" viewBox="0 0 480 92" preserveAspectRatio="none" aria-hidden="true">
              <path
                class="trace-base"
                d="M0 60 L120 60 L130 52 L138 64 L146 60 L210 60 L220 54 L228 63 L236 60"
              />
              <path
                class="trace-hot"
                d="M236 60 L262 60 L270 40 L278 70 L290 12 L302 84 L312 60 L332 60 L340 34 L348 74 L358 18 L368 80 L378 60 L404 60 L412 38 L420 72 L430 22 L440 78 L450 60 L480 60"
              />
            </svg>
          {/key}
          <span class="absolute top-3 left-4 font-mono text-[22px] leading-none font-bold">
            128<small class="ml-1 text-[11px] font-medium text-fg-muted">BPM · repaus</small>
          </span>
        </div>
        <ol class="m-0 list-none py-2 pl-0">
          {#each STEPS as step, i (i)}
            <li class={["step", i < shown && "on"]}>
              <span class="font-mono text-[11.5px] leading-[1.6] text-fg-muted tabular-nums"
                >{step.at}</span
              >
              <span
                class={[
                  "font-mono text-[11px] leading-[1.6] font-bold tracking-[0.06em]",
                  SOURCE_TONE[step.source],
                ]}
              >
                {SOURCE_LABEL[step.source]}
              </span>
              <span class={step.quote ? "text-fg" : "text-fg-soft"}>
                {step.quote ? `„${step.text}”` : step.text}
                {#if step.delta}
                  <span class="ml-1.5 font-mono text-[11px] text-fg-muted">{step.delta}</span>
                {/if}
              </span>
            </li>
          {/each}
        </ol>
        <figcaption class={["verdict", shown > STEPS.length && "on"]}>
          <span class="size-[9px] flex-none bg-rosu"></span>
          <b class="font-mono text-[12px] tracking-[0.05em] text-rosu-fg">COD ROȘU</b>
          <span class="verdict-note"
            >De la puls la un om: 58 de secunde. Familia și medicul, anunțați.</span
          >
        </figcaption>
      </figure>
    </section>

    <section aria-labelledby="does-title" class="border-t border-line">
      <h2 id="does-title" class="sr-only">Ce face EchoCare singur</h2>
      <div class="mx-auto grid max-w-[1200px] sm:grid-cols-2 lg:grid-cols-4">
        {#each DOES as item (item.title)}
          <div class="does border-line px-4 pt-7 pb-8 sm:px-7">
            <span class={item.tone}><Icon name={item.icon} size={26} stroke={1.75} /></span>
            <h3 class="mt-4 mb-1.5 text-[17px] font-extrabold tracking-[-0.01em]">{item.title}</h3>
            <p class="mb-3 text-[14px] text-fg-muted">{item.text}</p>
            <code
              class="inline-block border border-line bg-subtle px-1.5 py-0.5 font-mono text-[11.5px] text-fg-soft"
            >
              {item.sample}
            </code>
          </div>
        {/each}
      </div>
    </section>

    <footer class="border-t border-line">
      <div
        class="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-3 px-4 py-5 text-[13px] text-fg-muted sm:px-8"
      >
        <span>Conturile le creează medicul de familie și DAS.</span>
        <button class="sn-btn sn-btn-link" onclick={onSignIn}>Intrați în cont</button>
      </div>
    </footer>
  </main>
</div>

<style>
  .grid-bg {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image:
      linear-gradient(var(--color-line) 1px, transparent 1px),
      linear-gradient(90deg, var(--color-line) 1px, transparent 1px);
    background-size: 48px 48px;
    opacity: 0.32;
    mask-image: radial-gradient(ellipse 70% 60% at 70% 20%, #000 10%, transparent 70%);
  }
  .glow {
    position: absolute;
    pointer-events: none;
    width: 720px;
    height: 720px;
    right: -180px;
    top: -260px;
    background: radial-gradient(
      circle,
      color-mix(in srgb, var(--color-rosu) 16%, transparent),
      transparent 62%
    );
  }

  .hero-title {
    margin: 0 0 24px;
    font-size: clamp(42px, 6.4vw, 72px);
    line-height: 0.96;
    letter-spacing: -0.04em;
    font-weight: 800;
    text-wrap: balance;
  }
  .hero-title em {
    font-style: normal;
    color: var(--color-rosu-fg);
  }

  .panel {
    background: color-mix(in srgb, var(--color-inset) 88%, transparent);
    border: 1px solid var(--color-line);
    box-shadow: 0 30px 80px -20px rgb(0 0 0 / 0.7);
    backdrop-filter: blur(6px);
  }

  .live {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font: 600 11px/1 var(--font-mono);
    letter-spacing: 0.04em;
    color: var(--color-rosu-fg);
  }
  .live::before {
    content: "";
    width: 7px;
    height: 7px;
    background: var(--color-rosu);
    animation: blink 1.2s steps(2) infinite;
  }
  @keyframes blink {
    50% {
      opacity: 0.2;
    }
  }

  .trace {
    display: block;
    width: 100%;
    height: 92px;
  }
  .trace-base {
    fill: none;
    stroke: var(--color-line-strong);
    stroke-width: 2;
  }
  .trace-hot {
    fill: none;
    stroke: var(--color-rosu);
    stroke-width: 2.4;
    stroke-linejoin: round;
    stroke-linecap: round;
    stroke-dasharray: 900;
    stroke-dashoffset: 900;
    animation: draw 2.4s cubic-bezier(0.16, 1, 0.3, 1) 0.4s forwards;
  }
  @keyframes draw {
    to {
      stroke-dashoffset: 0;
    }
  }

  .step {
    display: grid;
    grid-template-columns: 66px 58px 1fr;
    gap: 10px;
    align-items: baseline;
    padding: 7px 16px;
    font-size: 13.5px;
    opacity: 0.14;
    transform: translateY(4px);
    transition:
      opacity 0.5s cubic-bezier(0.16, 1, 0.3, 1),
      transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .step.on {
    opacity: 1;
    transform: none;
  }

  .verdict {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    padding: 13px 16px;
    border-top: 2px solid var(--color-rosu);
    background: color-mix(in srgb, var(--color-rosu) 12%, transparent);
    font-size: 13px;
    opacity: 0;
    transition: opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .verdict.on {
    opacity: 1;
  }
  .verdict-note {
    color: color-mix(in srgb, var(--color-rosu-fg) 35%, var(--color-fg));
  }

  .does {
    border-bottom-width: 1px;
  }
  @media (min-width: 640px) {
    .does:nth-child(odd) {
      border-right-width: 1px;
    }
  }
  @media (min-width: 1024px) {
    .does {
      border-bottom-width: 0;
      border-right-width: 1px;
    }
    .does:last-child {
      border-right-width: 0;
    }
  }

  @media (max-width: 480px) {
    .step {
      grid-template-columns: 58px 1fr;
    }
    .step > :nth-child(2) {
      display: none;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .live::before,
    .trace-hot {
      animation: none;
      stroke-dashoffset: 0;
    }
    .step,
    .verdict {
      transition: none;
    }
  }
</style>
