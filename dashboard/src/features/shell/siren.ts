// The audio half of the Cod Roșu alert (spec 07 §1, UC-11). Browsers only play sound after a
// click, so the context is made when the dispatcher turns Alerte sonore on.
let ctx: AudioContext | null = null;

export function armSiren(): void {
  ctx ??= new AudioContext();
  void ctx.resume();
}

/** A short two-tone siren, about a second and a half */
export function playSiren(): void {
  if (!ctx) return;
  // Safari suspends or interrupts a context when another app takes the audio or the Mac sleeps
  void ctx.resume();
  const t = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "square";
  for (let i = 0; i < 6; i++) osc.frequency.setValueAtTime(i % 2 ? 660 : 880, t + i * 0.25);
  gain.gain.setValueAtTime(0.05, t);
  gain.gain.setValueAtTime(0, t + 1.5);
  osc.connect(gain).connect(ctx.destination);
  osc.start(t);
  osc.stop(t + 1.5);
}
