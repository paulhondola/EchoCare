# ADR-006: DAS sees the watch's health data, with 24 hours of readings

**Status:** Proposed
**Date:** 2026-11-13
**Deciders:** the team of four (owners of backend, dashboard, Android, Wear OS)
**Amends:** [01-architecture.md](../specs/echocare/01-architecture.md) §6 (who sees how much), [05-data-model.md](../specs/echocare/05-data-model.md) §4 and §5 (latest check-in only)

## Context

The watch sends a check-in every minute: battery, worn or not, last pulse (04 §3). FastAPI kept only the latest one, and only the senior's caregivers, their medic and the senior could see it. The DAS dashboard showed nothing about the watch.

A dispatcher who opens a senior after a red, or before calling a family, asks the same three questions: is the watch on, when did it last speak, and what has the pulse done. The caregiver's phone could answer these questions, but the dispatcher's screen could not.

## Decision

1. **DAS sees the watch state** like a caregiver and the medic do: `watch_state`, `last_pulse`, and the new `GET /seniors/{id}/watch` (04 §1). The scoping is the same as for every other DAS read, a senior past `draft`.
2. **The check-in carries more**, every field optional: `resting_pulse` (the watch's resting baseline), `steps_today` (since local midnight on the watch), `minutes_without_steps`. `worn` comes from the watch's off-body sensor instead of being always true.
3. **Readings are kept 24 hours** in `watch_readings`, one row per check-in, and the scheduler deletes older ones. `GET /seniors/{id}/watch/readings` returns them in 5-minute buckets, at most 288 points, for a pulse line on the dashboard card.

## Consequences

- More health data is stored, for a short time: a day of minute-by-minute pulse per senior, about 1,440 rows. The retention is the limit; nothing older survives the next scheduler tick.
- Pushes do not change: a watch state change still refreshes the caregivers, the medic and the senior (04 §6), and a check-in that changes no state sends none. The dashboard needs no push; it re-reads the watch on a timer (01 §7).
- Old phones keep working: the new check-in fields are optional, and an old watch simply omits them.

## Not done

- **ECG and SpO2.** On Wear OS, ECG runs only inside the vendor's own app (Samsung Health Monitor), and the Samsung Health Sensor SDK requires partner approval. Neither `SensorManager` nor Health Services gives a third-party app either signal. On iOS, the iPhone sends both from Apple Health ([ADR-008](ADR-008-ios-apple-health-oxygen-and-ecg.md), proposed).
- **Exact daily steps after a restart.** The watch counts steps from the moment its service starts on a given day. Health Services' `STEPS_DAILY` would fix this if it matters.
