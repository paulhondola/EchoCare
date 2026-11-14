import Foundation
import Shared
import os

/// Pending events to resend until the phone acks them (04 §3: "the watch keeps events and resends
/// them"). One JSON file per event, named after its id, as `EventQueue.kt`. `Monitor` resends
/// `pending()` every minute and `PhoneLink` when the phone comes back; the phone's `received`
/// message clears the file.
///
/// Used from the main actor only (`Monitor`, `PhoneLink`); file I/O is a few hundred bytes.
final class EventQueue {
    private let folder: URL
    private let files = FileManager.default
    private let log = Logger(subsystem: "ro.echocare.watch", category: "queue")

    init(directory: URL) {
        folder = directory
        do {
            try files.createDirectory(at: directory, withIntermediateDirectories: true)
        } catch {
            log.error("can't create the queue folder: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// The app's queue, in Application Support, so it outlives a relaunch.
    static func standard() -> EventQueue {
        EventQueue(directory: URL.applicationSupportDirectory.appending(path: "events", directoryHint: .isDirectory))
    }

    func enqueue(_ msg: EventMessage) {
        guard let file = file(for: msg.id) else {
            log.error("event with an unusable id not queued")
            return
        }
        do {
            let encoder = JSONEncoder()
            encoder.keyEncodingStrategy = .convertToSnakeCase
            try encoder.encode(msg).write(to: file, options: .atomic)
        } catch {
            log.error("event \(msg.id, privacy: .public) not queued: \(error.localizedDescription, privacy: .public)")
        }
    }

    func ack(id: String) {
        guard let file = file(for: id) else { return }
        try? files.removeItem(at: file)
    }

    /// Every queued event, oldest first. A file that doesn't decode is skipped, as on Wear OS.
    func pending() -> [EventMessage] {
        let urls = (try? files.contentsOfDirectory(
            at: folder, includingPropertiesForKeys: [.contentModificationDateKey])) ?? []
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return urls
            .filter { $0.pathExtension == "json" }
            .map { url in
                (url, (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast)
            }
            .sorted { $0.1 < $1.1 }
            .compactMap { url, _ in
                guard let data = try? Data(contentsOf: url) else { return nil }
                return try? decoder.decode(EventMessage.self, from: data)
            }
    }

    /// The file for an id, or nil for one that would name a path outside the folder. Ids are UUIDs
    /// the watch made; an ack from the phone is checked before it deletes anything.
    private func file(for id: String) -> URL? {
        guard !id.isEmpty, !id.contains("/"), !id.hasPrefix(".") else { return nil }
        return folder.appending(path: "\(id).json", directoryHint: .notDirectory)
    }
}
