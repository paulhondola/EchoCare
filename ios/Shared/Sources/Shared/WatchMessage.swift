import Foundation

/// Wire types for the watch → phone messages (04 §3, UC-09, UC-13). WatchConnectivity carries
/// them as a dictionary with the snake_case JSON in `"json"` and the message kind in `"kind"`.

public struct CheckInMessage: Codable, Equatable, Sendable {
    public var measuredAt: String
    public var battery: Int?
    public var worn: Bool
    public var lastPulse: Int?
    // Added by ADR-006; an older watch leaves them out, an older phone ignores them
    public var restingPulse: Int?
    public var stepsToday: Int?
    public var minutesWithoutSteps: Int?

    public init(
        measuredAt: String,
        battery: Int?,
        worn: Bool,
        lastPulse: Int?,
        restingPulse: Int? = nil,
        stepsToday: Int? = nil,
        minutesWithoutSteps: Int? = nil
    ) {
        self.measuredAt = measuredAt
        self.battery = battery
        self.worn = worn
        self.lastPulse = lastPulse
        self.restingPulse = restingPulse
        self.stepsToday = stepsToday
        self.minutesWithoutSteps = minutesWithoutSteps
    }
}

public struct EventSnapshot: Codable, Equatable, Sendable {
    public var pulse: Int?
    public var restingBaseline: Int?
    public var moving: Bool?
    public var minutesWithoutSteps: Int?
    public var battery: Int?

    public static let empty = EventSnapshot(
        pulse: nil, restingBaseline: nil, moving: nil, minutesWithoutSteps: nil, battery: nil)

    public init(
        pulse: Int?, restingBaseline: Int?, moving: Bool?, minutesWithoutSteps: Int?, battery: Int?
    ) {
        self.pulse = pulse
        self.restingBaseline = restingBaseline
        self.moving = moving
        self.minutesWithoutSteps = minutesWithoutSteps
        self.battery = battery
    }
}

public struct EventMessage: Codable, Equatable, Sendable {
    public var id: String
    public var type: String
    public var measuredAt: String
    public var snapshot: EventSnapshot?

    public init(id: String, type: String, measuredAt: String, snapshot: EventSnapshot? = nil) {
        self.id = id
        self.type = type
        self.measuredAt = measuredAt
        self.snapshot = snapshot
    }
}

public enum WatchMessage {
    // The `"kind"` values, the counterparts of Android's three Data Layer paths
    public static let event = "event"
    public static let checkIn = "check-in"
    public static let received = "received"

    private static let jsonKey = "json"

    /// The dictionary to hand to WatchConnectivity: the snake_case JSON under `"json"`. The caller
    /// adds `"kind"`.
    public static func encode<T: Encodable>(_ value: T) throws -> [String: Any] {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(value)
        return [jsonKey: String(decoding: data, as: UTF8.self)]
    }

    public static func decode<T: Decodable>(_ type: T.Type, from message: [String: Any]) throws -> T
    {
        guard let json = message[jsonKey] as? String else {
            throw DecodingError.dataCorrupted(
                .init(codingPath: [], debugDescription: "message has no \"json\" string"))
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }
}
