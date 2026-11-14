/// How often the watch sends a check-in (06 §3, UC-13): every 15 minutes, every minute in the demo,
/// as Wear OS `CHECK_IN_MINUTES`. The watch sends on it and the phone judges the watch's silence by
/// it, so both read it here. The package has no `DEMO` flag: each target passes its own.
public enum CheckInInterval {
    public static func minutes(demo: Bool) -> Int { demo ? 1 : 15 }

    public static func seconds(demo: Bool) -> Double { Double(minutes(demo: demo) * 60) }
}
