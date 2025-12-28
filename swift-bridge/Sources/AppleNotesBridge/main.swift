import Foundation
import ArgumentParser
import CommonCrypto
import SQLite3

// MARK: - Main Command

@main
struct NotesBridge: ParsableCommand {
    static var configuration = CommandConfiguration(
        commandName: "notes-bridge",
        abstract: "Bridge to Apple Notes via AppleScript",
        subcommands: [
            ListFolders.self, ListNotes.self, ExportNote.self, ExportAll.self,
            UpdateNote.self, DeleteNote.self, CreateFolder.self, GetFolderByName.self,
            MoveNote.self, BackupAll.self, CreateNote.self
        ]
    )
}

// MARK: - Error Handling

struct BridgeError: Error, CustomStringConvertible {
    let message: String
    let code: String

    var description: String {
        return message
    }

    func toJSON() -> String {
        let data: [String: String] = ["error": message, "code": code]
        if let jsonData = try? JSONSerialization.data(withJSONObject: data),
           let jsonString = String(data: jsonData, encoding: .utf8) {
            return jsonString
        }
        return "{\"error\": \"\(message)\", \"code\": \"\(code)\"}"
    }
}

// MARK: - Output Helpers

func outputJSON(_ object: Any) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    if let string = String(data: data, encoding: .utf8) {
        print(string)
    }
}

func outputError(_ error: BridgeError) {
    FileHandle.standardError.write(Data(error.toJSON().utf8))
}

// MARK: - AppleScript Execution

func runAppleScript(_ script: String) throws -> String {
    let appleScript = NSAppleScript(source: script)
    var errorDict: NSDictionary?

    guard let output = appleScript?.executeAndReturnError(&errorDict) else {
        let errorMessage = (errorDict?[NSAppleScript.errorMessage] as? String) ?? "Unknown AppleScript error"
        throw BridgeError(message: errorMessage, code: "APPLESCRIPT_ERROR")
    }

    return output.stringValue ?? ""
}

// MARK: - Notes Access

class NotesAccess {
    static let shared = NotesAccess()

    private let tempDir: String

    // Cached folder hierarchy for building full paths
    private var folderNames: [String: String] = [:]  // id -> name
    private var folderParents: [String: String] = [:] // id -> parentId
    private var folderPathCache: [String: String] = [:] // id -> full path
    private var hierarchyLoaded = false

    private init() {
        // Create temp directory for attachment exports
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("notes-bridge-attachments")
        tempDir = tempPath.path
        try? FileManager.default.createDirectory(atPath: tempDir, withIntermediateDirectories: true)
    }

    /// Load folder hierarchy for building full paths
    private func loadFolderHierarchy() {
        if hierarchyLoaded { return }

        let script = """
        tell application "Notes"
            set folderList to {}
            repeat with anAccount in accounts
                repeat with aFolder in folders of anAccount
                    set folderId to id of aFolder
                    set folderName to name of aFolder
                    set containerId to ""
                    try
                        set containerId to id of container of aFolder
                    end try
                    set end of folderList to folderId & "|||" & folderName & "|||" & containerId
                end repeat
            end repeat
            set AppleScript's text item delimiters to ":::"
            return folderList as string
        end tell
        """

        if let result = try? runAppleScript(script), !result.isEmpty {
            let folderStrings = result.components(separatedBy: ":::")
            for folderStr in folderStrings {
                let parts = folderStr.components(separatedBy: "|||")
                if parts.count >= 2 {
                    let folderId = parts[0]
                    let folderName = parts[1]
                    let parentId = parts.count >= 3 ? parts[2] : ""

                    folderNames[folderId] = folderName
                    if !parentId.isEmpty {
                        folderParents[folderId] = parentId
                    }
                }
            }
        }

        hierarchyLoaded = true
    }

    /// Build full path for a folder by traversing up the hierarchy
    func getFullFolderPath(folderId: String) -> String {
        loadFolderHierarchy()

        // Check cache
        if let cached = folderPathCache[folderId] {
            return cached
        }

        // Build path by traversing up
        var pathParts: [String] = []
        var currentId = folderId
        var visited = Set<String>()  // Prevent infinite loops

        while let name = folderNames[currentId], !visited.contains(currentId) {
            visited.insert(currentId)
            pathParts.insert(name, at: 0)

            if let parentId = folderParents[currentId], folderNames[parentId] != nil {
                currentId = parentId
            } else {
                break
            }
        }

        let fullPath = pathParts.joined(separator: "/")
        folderPathCache[folderId] = fullPath
        return fullPath
    }

    /// Extract attachments from a note using AppleScript
    func getAttachments(noteId: String) throws -> [[String: Any]] {
        // First get attachment count and basic info
        let listScript = """
        tell application "Notes"
            try
                set theNote to note id "\(noteId)"
                set attachmentList to {}
                repeat with anAttachment in attachments of theNote
                    set attachId to id of anAttachment
                    set attachName to name of anAttachment
                    set attachContentId to ""
                    try
                        set attachContentId to content identifier of anAttachment
                    end try
                    set end of attachmentList to attachId & "|||" & attachName & "|||" & attachContentId
                end repeat
                set AppleScript's text item delimiters to ":::"
                return attachmentList as string
            on error
                return ""
            end try
        end tell
        """

        let result = try runAppleScript(listScript)
        var attachments: [[String: Any]] = []

        if !result.isEmpty {
            let attachmentStrings = result.components(separatedBy: ":::")
            for attachStr in attachmentStrings where !attachStr.isEmpty {
                let parts = attachStr.components(separatedBy: "|||")
                if parts.count >= 2 {
                    let attachId = parts[0]
                    let attachName = parts[1]
                    let contentId = parts.count >= 3 ? parts[2] : ""

                    // Determine if it's a PDF based on extension
                    let isPDF = attachName.lowercased().hasSuffix(".pdf")

                    var attachment: [String: Any] = [
                        "id": attachId,
                        "name": attachName,
                        "contentIdentifier": contentId,
                        "isPDF": isPDF
                    ]

                    // If it's a PDF, try to export it to temp directory
                    if isPDF {
                        let safeFileName = attachName.replacingOccurrences(of: "/", with: "_")
                        let exportPath = "\(tempDir)/\(noteId.replacingOccurrences(of: "/", with: "_"))_\(safeFileName)"

                        // Try to save the attachment using AppleScript
                        let saveScript = """
                        tell application "Notes"
                            try
                                set theNote to note id "\(noteId)"
                                repeat with anAttachment in attachments of theNote
                                    if id of anAttachment is "\(attachId)" then
                                        -- Save attachment to file using Finder
                                        tell application "Finder"
                                            set attachFile to (POSIX file "\(exportPath)") as alias
                                        end tell
                                        return "saved"
                                    end if
                                end repeat
                                return "not_found"
                            on error errMsg
                                return "error: " & errMsg
                            end try
                        end tell
                        """

                        // Note: Direct AppleScript save doesn't work well for attachments.
                        // We'll use an alternative approach - the attachment URL
                        let urlScript = """
                        tell application "Notes"
                            try
                                set theNote to note id "\(noteId)"
                                repeat with anAttachment in attachments of theNote
                                    if id of anAttachment is "\(attachId)" then
                                        try
                                            return URL of anAttachment
                                        on error
                                            return ""
                                        end try
                                    end if
                                end repeat
                                return ""
                            on error
                                return ""
                            end try
                        end tell
                        """

                        var sourcePath: String? = nil

                        // First try AppleScript URL (works for some attachments)
                        if let attachmentURL = try? runAppleScript(urlScript), !attachmentURL.isEmpty {
                            attachment["url"] = attachmentURL

                            if attachmentURL.hasPrefix("file://") {
                                let urlPath = attachmentURL
                                    .replacingOccurrences(of: "file://", with: "")
                                    .removingPercentEncoding ?? ""

                                if FileManager.default.fileExists(atPath: urlPath) {
                                    sourcePath = urlPath
                                }
                            }
                        }

                        // Fallback: Query NoteStore.sqlite database directly
                        if sourcePath == nil && !contentId.isEmpty {
                            if let dbPath = NoteStoreDatabase.shared.findPDFPath(contentIdentifier: contentId) {
                                sourcePath = dbPath
                                attachment["sourceMethod"] = "database_contentId"
                            }
                        }

                        // Second fallback: Search by filename
                        if sourcePath == nil {
                            if let dbPath = NoteStoreDatabase.shared.findPDFByName(attachmentName: attachName) {
                                sourcePath = dbPath
                                attachment["sourceMethod"] = "database_filename"
                            }
                        }

                        // Copy file to temp location if found
                        if let source = sourcePath {
                            try? FileManager.default.removeItem(atPath: exportPath)
                            do {
                                try FileManager.default.copyItem(atPath: source, toPath: exportPath)
                                attachment["exportedPath"] = exportPath
                            } catch {
                                attachment["exportError"] = error.localizedDescription
                            }
                        }
                    }

                    attachments.append(attachment)
                }
            }
        }

        return attachments
    }

    func getAllFolders() throws -> [[String: Any]] {
        // AppleScript to get all folders with their properties
        let script = """
        tell application "Notes"
            set folderList to {}
            repeat with anAccount in accounts
                repeat with aFolder in folders of anAccount
                    set folderId to id of aFolder
                    set folderName to name of aFolder
                    set containerId to ""
                    try
                        set containerId to id of container of aFolder
                    end try
                    set end of folderList to folderId & "|||" & folderName & "|||" & containerId
                end repeat
            end repeat
            set AppleScript's text item delimiters to ":::"
            return folderList as string
        end tell
        """

        let result = try runAppleScript(script)
        var folders: [[String: Any]] = []

        if !result.isEmpty {
            let folderStrings = result.components(separatedBy: ":::")
            for folderStr in folderStrings {
                let parts = folderStr.components(separatedBy: "|||")
                if parts.count >= 2 {
                    var folder: [String: Any] = [
                        "id": parts[0],
                        "name": parts[1]
                    ]
                    if parts.count >= 3 && !parts[2].isEmpty {
                        folder["parentId"] = parts[2]
                    } else {
                        folder["parentId"] = NSNull()
                    }
                    folders.append(folder)
                }
            }
        }

        return folders
    }

    func getAllNotes(includeHTML: Bool = false, includeAttachments: Bool = false) throws -> [[String: Any]] {
        // First get basic note info (excluding shared notes)
        let basicScript = """
        tell application "Notes"
            set noteList to {}
            repeat with aNote in notes
                -- Skip shared notes
                try
                    if shared of aNote then
                        -- Skip this note
                    else
                        set noteId to id of aNote
                        set noteName to name of aNote
                        set noteCreated to creation date of aNote as string
                        set noteModified to modification date of aNote as string

                        -- Get folder info (must save container to variable first)
                        set folderId to ""
                        set folderName to ""
                        set theContainer to missing value
                        try
                            set theContainer to container of aNote
                        end try
                        if theContainer is not missing value then
                            try
                                set folderId to id of theContainer
                                set folderName to name of theContainer
                            end try
                        end if

                        set end of noteList to noteId & "|||" & noteName & "|||" & folderId & "|||" & folderName & "|||" & noteCreated & "|||" & noteModified
                    end if
                on error
                    -- If we can't check shared status, include the note
                    set noteId to id of aNote
                    set noteName to name of aNote
                    set noteCreated to creation date of aNote as string
                    set noteModified to modification date of aNote as string

                    -- Get folder info (must save container to variable first)
                    set folderId to ""
                    set folderName to ""
                    set theContainer to missing value
                    try
                        set theContainer to container of aNote
                    end try
                    if theContainer is not missing value then
                        try
                            set folderId to id of theContainer
                            set folderName to name of theContainer
                        end try
                    end if

                    set end of noteList to noteId & "|||" & noteName & "|||" & folderId & "|||" & folderName & "|||" & noteCreated & "|||" & noteModified
                end try
            end repeat
            set AppleScript's text item delimiters to ":::"
            return noteList as string
        end tell
        """

        let result = try runAppleScript(basicScript)
        var notes: [[String: Any]] = []

        if !result.isEmpty {
            let noteStrings = result.components(separatedBy: ":::")
            for noteStr in noteStrings {
                let parts = noteStr.components(separatedBy: "|||")
                if parts.count >= 6 {
                    let noteId = parts[0]
                    let noteName = parts[1]
                    let folderId = parts[2]
                    let folderName = parts[3]
                    let creationDate = parts[4]
                    let modificationDate = parts[5]

                    // Build full folder path from hierarchy
                    let fullFolderPath = folderId.isEmpty ? "" : getFullFolderPath(folderId: folderId)

                    var note: [String: Any] = [
                        "id": noteId,
                        "name": noteName,
                        "folderId": folderId,
                        "folderPath": fullFolderPath,
                        "folderName": folderName,  // Keep immediate folder name too
                        "creationDate": creationDate,
                        "modificationDate": modificationDate
                    ]

                    // Get plaintext for each note
                    let plaintextScript = """
                    tell application "Notes"
                        set theNote to note id "\(noteId)"
                        return plaintext of theNote
                    end tell
                    """

                    if let plaintext = try? runAppleScript(plaintextScript) {
                        note["bodyPlainText"] = plaintext
                    } else {
                        note["bodyPlainText"] = ""
                    }

                    if includeHTML {
                        let bodyScript = """
                        tell application "Notes"
                            set theNote to note id "\(noteId)"
                            return body of theNote
                        end tell
                        """

                        if let body = try? runAppleScript(bodyScript) {
                            note["bodyHTML"] = body
                        } else {
                            note["bodyHTML"] = ""
                        }
                    }

                    // Include attachments if requested
                    if includeAttachments {
                        if let attachments = try? getAttachments(noteId: noteId) {
                            note["attachments"] = attachments
                        } else {
                            note["attachments"] = []
                        }
                    }

                    // Compute content hash
                    let plainText = note["bodyPlainText"] as? String ?? ""
                    let hashContent = "\(noteName)|\(plainText)|\(modificationDate)"
                    note["contentHash"] = "sha256:\(hashContent.sha256())"

                    notes.append(note)
                }
            }
        }

        return notes
    }

    func getNote(id: String, includeHTML: Bool = false, includeAttachments: Bool = false) throws -> [String: Any]? {
        // Get specific note by ID (excluding shared notes)
        let script = """
        tell application "Notes"
            try
                set theNote to note id "\(id)"
                -- Check if note is shared and skip if so
                try
                    if shared of theNote then
                        return "SHARED_NOTE"
                    end if
                end try
                set noteId to id of theNote
                set noteName to name of theNote
                set noteCreated to creation date of theNote as string
                set noteModified to modification date of theNote as string
                set notePlaintext to plaintext of theNote

                -- Get folder info (must save container to variable first)
                set folderId to ""
                set folderName to ""
                set theContainer to missing value
                try
                    set theContainer to container of theNote
                end try
                if theContainer is not missing value then
                    try
                        set folderId to id of theContainer
                        set folderName to name of theContainer
                    end try
                end if

                return noteId & "|||" & noteName & "|||" & folderId & "|||" & folderName & "|||" & noteCreated & "|||" & noteModified & "|||" & notePlaintext
            on error
                return ""
            end try
        end tell
        """

        let result = try runAppleScript(script)

        if result.isEmpty || result == "SHARED_NOTE" {
            return nil
        }

        let parts = result.components(separatedBy: "|||")
        if parts.count >= 7 {
            let folderId = parts[2]
            let folderName = parts[3]
            let fullFolderPath = folderId.isEmpty ? "" : getFullFolderPath(folderId: folderId)

            var note: [String: Any] = [
                "id": parts[0],
                "name": parts[1],
                "folderId": folderId,
                "folderPath": fullFolderPath,
                "folderName": folderName,
                "creationDate": parts[4],
                "modificationDate": parts[5],
                "bodyPlainText": parts[6]
            ]

            if includeHTML {
                let bodyScript = """
                tell application "Notes"
                    set theNote to note id "\(id)"
                    return body of theNote
                end tell
                """

                if let body = try? runAppleScript(bodyScript) {
                    note["bodyHTML"] = body
                } else {
                    note["bodyHTML"] = ""
                }
            }

            // Include attachments if requested
            if includeAttachments {
                let attachments = try getAttachments(noteId: id)
                note["attachments"] = attachments
            }

            // Compute content hash
            let noteName = parts[1]
            let plainText = parts[6]
            let modificationDate = parts[5]
            let hashContent = "\(noteName)|\(plainText)|\(modificationDate)"
            note["contentHash"] = "sha256:\(hashContent.sha256())"

            return note
        }

        return nil
    }
}

// MARK: - NoteStore Database Access

class NoteStoreDatabase {
    static let shared = NoteStoreDatabase()

    private let dbPath: String
    private let accountId: String?
    private let notesContainerPath: String

    private init() {
        // Find the NoteStore.sqlite database
        let homeDir = FileManager.default.homeDirectoryForCurrentUser.path
        notesContainerPath = "\(homeDir)/Library/Group Containers/group.com.apple.notes"
        dbPath = "\(notesContainerPath)/NoteStore.sqlite"

        // Find the account ID from the Accounts directory
        let accountsPath = "\(notesContainerPath)/Accounts"
        if let accounts = try? FileManager.default.contentsOfDirectory(atPath: accountsPath) {
            // Find the first UUID-formatted account folder
            accountId = accounts.first { name in
                // UUID format check (simple heuristic)
                name.count == 36 && name.contains("-")
            }
        } else {
            accountId = nil
        }
    }

    /// Extract UUID from content identifier format like "cid:UUID@icloud.apple.com"
    private func extractUUID(from contentIdentifier: String) -> String {
        var uuid = contentIdentifier
        // Remove cid: prefix
        if uuid.hasPrefix("cid:") {
            uuid = String(uuid.dropFirst(4))
        }
        // Remove @icloud.apple.com suffix
        if let atIndex = uuid.firstIndex(of: "@") {
            uuid = String(uuid[..<atIndex])
        }
        return uuid
    }

    /// Find the file path for a PDF attachment using its content identifier
    func findPDFPath(contentIdentifier: String) -> String? {
        guard let accountId = accountId else { return nil }

        // Extract the UUID from the full content identifier
        let uuid = extractUUID(from: contentIdentifier)

        var db: OpaquePointer?
        guard sqlite3_open_v2(dbPath, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else {
            return nil
        }
        defer { sqlite3_close(db) }

        // Query to find media info for this attachment
        // The UUID from contentIdentifier corresponds to ZIDENTIFIER in the attachment record
        let query = """
            SELECT m.ZIDENTIFIER, m.ZFILENAME
            FROM ZICCLOUDSYNCINGOBJECT a
            JOIN ZICCLOUDSYNCINGOBJECT m ON a.ZMEDIA = m.Z_PK
            WHERE a.ZIDENTIFIER = ? AND a.Z_ENT = 4 AND m.Z_ENT = 10
            LIMIT 1;
        """

        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, query, -1, &stmt, nil) == SQLITE_OK else {
            return nil
        }
        defer { sqlite3_finalize(stmt) }

        // Bind the UUID parameter
        let uuidData = Data(uuid.utf8)
        _ = uuidData.withUnsafeBytes { ptr in
            sqlite3_bind_text(stmt, 1, ptr.baseAddress?.assumingMemoryBound(to: CChar.self), Int32(uuid.count), nil)
        }

        guard sqlite3_step(stmt) == SQLITE_ROW else {
            return nil
        }

        guard let mediaIdPtr = sqlite3_column_text(stmt, 0),
              let filenamePtr = sqlite3_column_text(stmt, 1) else {
            return nil
        }

        let mediaId = String(cString: mediaIdPtr)
        let filename = String(cString: filenamePtr)

        return resolveMediaPath(mediaId: mediaId, filename: filename, accountId: accountId)
    }

    /// Resolve the file path from media ID and filename
    private func resolveMediaPath(mediaId: String, filename: String, accountId: String) -> String? {
        // The path structure is: /Accounts/{accountID}/Media/{mediaID}/1_{someUUID}/{filename}
        let mediaDir = "\(notesContainerPath)/Accounts/\(accountId)/Media/\(mediaId)"

        // Find the inner directory (1_*)
        guard let contents = try? FileManager.default.contentsOfDirectory(atPath: mediaDir) else {
            return nil
        }

        guard let innerDir = contents.first(where: { $0.hasPrefix("1_") }) else {
            return nil
        }

        let fullPath = "\(mediaDir)/\(innerDir)/\(filename)"

        if FileManager.default.fileExists(atPath: fullPath) {
            return fullPath
        }

        return nil
    }

    /// Alternative: Find PDF by searching for attachment name in database
    func findPDFByName(attachmentName: String) -> String? {
        guard let accountId = accountId else { return nil }

        var db: OpaquePointer?
        guard sqlite3_open_v2(dbPath, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else {
            return nil
        }
        defer { sqlite3_close(db) }

        // Query to find media info by filename
        let query = """
            SELECT m.ZIDENTIFIER, m.ZFILENAME
            FROM ZICCLOUDSYNCINGOBJECT m
            WHERE m.ZFILENAME = ? AND m.Z_ENT = 10
            LIMIT 1;
        """

        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, query, -1, &stmt, nil) == SQLITE_OK else {
            return nil
        }
        defer { sqlite3_finalize(stmt) }

        sqlite3_bind_text(stmt, 1, attachmentName, -1, nil)

        guard sqlite3_step(stmt) == SQLITE_ROW else {
            return nil
        }

        guard let mediaIdPtr = sqlite3_column_text(stmt, 0),
              let filenamePtr = sqlite3_column_text(stmt, 1) else {
            return nil
        }

        let mediaId = String(cString: mediaIdPtr)
        let filename = String(cString: filenamePtr)

        return resolveMediaPath(mediaId: mediaId, filename: filename, accountId: accountId)
    }
}

// MARK: - String Extension for Hashing

extension String {
    func sha256() -> String {
        let data = Data(self.utf8)
        var hash = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
        data.withUnsafeBytes {
            _ = CC_SHA256($0.baseAddress, CC_LONG(data.count), &hash)
        }
        return hash.map { String(format: "%02x", $0) }.joined()
    }
}

// MARK: - Commands

struct ListFolders: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "List all folders in Apple Notes"
    )

    func run() throws {
        do {
            let folders = try NotesAccess.shared.getAllFolders()
            try outputJSON(["folders": folders])
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}

struct ListNotes: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "List all notes, optionally filtered by folder"
    )

    @Option(name: .long, help: "Filter by folder name")
    var folder: String?

    @Flag(name: .long, help: "Include HTML body")
    var html: Bool = false

    @Flag(name: .long, help: "Include attachments (extracts PDFs to temp directory)")
    var attachments: Bool = false

    func run() throws {
        do {
            var notes = try NotesAccess.shared.getAllNotes(includeHTML: html, includeAttachments: attachments)

            if let folderFilter = folder {
                notes = notes.filter { note in
                    (note["folderPath"] as? String)?.lowercased() == folderFilter.lowercased()
                }
            }

            try outputJSON(["notes": notes])
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}

struct ExportNote: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "Export a single note by ID"
    )

    @Argument(help: "Note ID")
    var noteId: String

    @Flag(name: .long, help: "Include HTML body")
    var html: Bool = false

    @Flag(name: .long, help: "Include attachments (extracts PDFs to temp directory)")
    var attachments: Bool = false

    func run() throws {
        do {
            if let note = try NotesAccess.shared.getNote(id: noteId, includeHTML: html, includeAttachments: attachments) {
                try outputJSON(note)
            } else {
                let error = BridgeError(message: "Note not found: \(noteId)", code: "NOT_FOUND")
                outputError(error)
                throw ExitCode.failure
            }
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}

struct ExportAll: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "Export all notes as JSON"
    )

    @Option(name: .long, help: "Output file path (stdout if not specified)")
    var output: String?

    @Flag(name: .long, help: "Include HTML body")
    var html: Bool = false

    @Flag(name: .long, help: "Include attachments (extracts PDFs to temp directory)")
    var attachments: Bool = false

    func run() throws {
        do {
            let folders = try NotesAccess.shared.getAllFolders()
            let notes = try NotesAccess.shared.getAllNotes(includeHTML: html, includeAttachments: attachments)

            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]

            let exportData: [String: Any] = [
                "exportedAt": formatter.string(from: Date()),
                "folders": folders,
                "notes": notes
            ]

            let jsonData = try JSONSerialization.data(withJSONObject: exportData, options: [.prettyPrinted, .sortedKeys])

            if let outputPath = output {
                try jsonData.write(to: URL(fileURLWithPath: outputPath))
                print("Exported to: \(outputPath)")
            } else {
                if let jsonString = String(data: jsonData, encoding: .utf8) {
                    print(jsonString)
                }
            }
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}

// MARK: - Write Commands

struct UpdateNote: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "Update a note's body content"
    )

    @Argument(help: "Note ID to update")
    var noteId: String

    @Option(name: .long, help: "Path to file containing HTML body")
    var htmlFile: String?

    @Option(name: .long, help: "HTML body content directly")
    var htmlBody: String?

    func run() throws {
        var htmlContent: String

        if let filePath = htmlFile {
            do {
                htmlContent = try String(contentsOfFile: filePath, encoding: .utf8)
            } catch {
                let bridgeError = BridgeError(message: "Could not read file: \(filePath)", code: "FILE_ERROR")
                outputError(bridgeError)
                throw ExitCode.failure
            }
        } else if let body = htmlBody {
            htmlContent = body
        } else {
            let bridgeError = BridgeError(message: "Either --html-file or --html-body is required", code: "MISSING_PARAM")
            outputError(bridgeError)
            throw ExitCode.failure
        }

        // Escape the HTML for AppleScript
        let escapedHTML = htmlContent
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\r", with: "\\r")

        let script = """
        tell application "Notes"
            try
                set theNote to note id "\(noteId)"
                set body of theNote to "\(escapedHTML)"
                return "success"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        """

        do {
            let result = try runAppleScript(script)
            if result.hasPrefix("error:") {
                let bridgeError = BridgeError(message: result, code: "UPDATE_ERROR")
                outputError(bridgeError)
                throw ExitCode.failure
            }
            try outputJSON(["success": true, "noteId": noteId])
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}

struct DeleteNote: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "Delete a note (moves to trash)"
    )

    @Argument(help: "Note ID to delete")
    var noteId: String

    func run() throws {
        let script = """
        tell application "Notes"
            try
                set theNote to note id "\(noteId)"
                delete theNote
                return "success"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        """

        do {
            let result = try runAppleScript(script)
            if result.hasPrefix("error:") {
                let bridgeError = BridgeError(message: result, code: "DELETE_ERROR")
                outputError(bridgeError)
                throw ExitCode.failure
            }
            try outputJSON(["success": true, "noteId": noteId, "action": "deleted"])
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}

struct CreateFolder: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "Create a new folder"
    )

    @Argument(help: "Folder name")
    var name: String

    @Option(name: .long, help: "Account name (default: first account)")
    var account: String?

    func run() throws {
        let accountPart = account != nil ? "account \"\(account!)\"" : "first account"

        let script = """
        tell application "Notes"
            try
                tell \(accountPart)
                    set newFolder to make new folder with properties {name:"\(name)"}
                    return id of newFolder & "|||" & name of newFolder
                end tell
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        """

        do {
            let result = try runAppleScript(script)
            if result.hasPrefix("error:") {
                let bridgeError = BridgeError(message: result, code: "CREATE_FOLDER_ERROR")
                outputError(bridgeError)
                throw ExitCode.failure
            }

            let parts = result.components(separatedBy: "|||")
            if parts.count >= 2 {
                try outputJSON(["success": true, "id": parts[0], "name": parts[1]])
            } else {
                try outputJSON(["success": true, "result": result])
            }
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}

struct GetFolderByName: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "Find a folder by name"
    )

    @Argument(help: "Folder name to find")
    var name: String

    func run() throws {
        let script = """
        tell application "Notes"
            try
                repeat with anAccount in accounts
                    repeat with aFolder in folders of anAccount
                        if name of aFolder is "\(name)" then
                            return id of aFolder & "|||" & name of aFolder & "|||" & name of anAccount
                        end if
                    end repeat
                end repeat
                return "not_found"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        """

        do {
            let result = try runAppleScript(script)
            if result.hasPrefix("error:") {
                let bridgeError = BridgeError(message: result, code: "FIND_FOLDER_ERROR")
                outputError(bridgeError)
                throw ExitCode.failure
            }

            if result == "not_found" {
                try outputJSON(["found": false, "name": name])
            } else {
                let parts = result.components(separatedBy: "|||")
                if parts.count >= 3 {
                    try outputJSON([
                        "found": true,
                        "id": parts[0],
                        "name": parts[1],
                        "account": parts[2]
                    ])
                } else {
                    try outputJSON(["found": false, "name": name])
                }
            }
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}

struct MoveNote: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "Move a note to a different folder"
    )

    @Argument(help: "Note ID to move")
    var noteId: String

    @Option(name: .long, help: "Destination folder ID")
    var toFolderId: String?

    @Option(name: .long, help: "Destination folder name (will find or create)")
    var toFolderName: String?

    func run() throws {
        guard toFolderId != nil || toFolderName != nil else {
            let bridgeError = BridgeError(message: "Either --to-folder-id or --to-folder-name is required", code: "MISSING_PARAM")
            outputError(bridgeError)
            throw ExitCode.failure
        }

        var script: String

        if let folderId = toFolderId {
            script = """
            tell application "Notes"
                try
                    set theNote to note id "\(noteId)"
                    set destFolder to folder id "\(folderId)"
                    move theNote to destFolder
                    return "success|||" & id of destFolder & "|||" & name of destFolder
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            """
        } else if let folderName = toFolderName {
            // Find or create folder, then move
            script = """
            tell application "Notes"
                try
                    set theNote to note id "\(noteId)"
                    set destFolder to missing value

                    -- Find folder by name
                    repeat with anAccount in accounts
                        repeat with aFolder in folders of anAccount
                            if name of aFolder is "\(folderName)" then
                                set destFolder to aFolder
                                exit repeat
                            end if
                        end repeat
                        if destFolder is not missing value then exit repeat
                    end repeat

                    -- Create folder if not found
                    if destFolder is missing value then
                        tell first account
                            set destFolder to make new folder with properties {name:"\(folderName)"}
                        end tell
                    end if

                    move theNote to destFolder
                    return "success|||" & id of destFolder & "|||" & name of destFolder
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            """
        } else {
            fatalError("Unreachable")
        }

        do {
            let result = try runAppleScript(script)
            if result.hasPrefix("error:") {
                let bridgeError = BridgeError(message: result, code: "MOVE_ERROR")
                outputError(bridgeError)
                throw ExitCode.failure
            }

            let parts = result.components(separatedBy: "|||")
            if parts.count >= 3 {
                try outputJSON([
                    "success": true,
                    "noteId": noteId,
                    "destinationFolderId": parts[1],
                    "destinationFolderName": parts[2]
                ])
            } else {
                try outputJSON(["success": true, "result": result])
            }
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}

struct BackupAll: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "Create a full backup of all notes to JSON"
    )

    @Option(name: .long, help: "Output directory for backup")
    var outputDir: String

    func run() throws {
        do {
            // Create output directory if needed
            try FileManager.default.createDirectory(atPath: outputDir, withIntermediateDirectories: true)

            // Get all data
            let folders = try NotesAccess.shared.getAllFolders()
            let notes = try NotesAccess.shared.getAllNotes(includeHTML: true, includeAttachments: false)

            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]

            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd_HHmmss"
            let timestamp = dateFormatter.string(from: Date())

            let backupData: [String: Any] = [
                "backupVersion": "1.0",
                "createdAt": formatter.string(from: Date()),
                "noteCount": notes.count,
                "folderCount": folders.count,
                "folders": folders,
                "notes": notes
            ]

            let jsonData = try JSONSerialization.data(withJSONObject: backupData, options: [.prettyPrinted, .sortedKeys])

            let backupPath = "\(outputDir)/apple_notes_backup_\(timestamp).json"
            try jsonData.write(to: URL(fileURLWithPath: backupPath))

            try outputJSON([
                "success": true,
                "backupPath": backupPath,
                "noteCount": notes.count,
                "folderCount": folders.count
            ])
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        } catch {
            let bridgeError = BridgeError(message: error.localizedDescription, code: "BACKUP_ERROR")
            outputError(bridgeError)
            throw ExitCode.failure
        }
    }
}

struct CreateNote: ParsableCommand {
    static var configuration = CommandConfiguration(
        abstract: "Create a new note in Apple Notes"
    )

    @Option(name: .long, help: "Note title/name")
    var name: String

    @Option(name: .long, help: "HTML body content")
    var htmlBody: String?

    @Option(name: .long, help: "Path to file containing HTML body")
    var htmlFile: String?

    @Option(name: .long, help: "Folder ID to create note in")
    var folderId: String?

    @Option(name: .long, help: "Folder name to create note in")
    var folderName: String?

    func run() throws {
        var htmlContent = ""

        if let filePath = htmlFile {
            do {
                htmlContent = try String(contentsOfFile: filePath, encoding: .utf8)
            } catch {
                let bridgeError = BridgeError(message: "Could not read file: \(filePath)", code: "FILE_ERROR")
                outputError(bridgeError)
                throw ExitCode.failure
            }
        } else if let body = htmlBody {
            htmlContent = body
        }

        // Escape for AppleScript
        let escapedHTML = htmlContent
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\r", with: "\\r")

        let escapedName = name
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")

        var script: String

        if let folderId = folderId {
            script = """
            tell application "Notes"
                try
                    set destFolder to folder id "\(folderId)"
                    set newNote to make new note at destFolder with properties {name:"\(escapedName)", body:"\(escapedHTML)"}
                    return id of newNote & "|||" & name of newNote
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            """
        } else if let folderName = folderName {
            script = """
            tell application "Notes"
                try
                    set destFolder to missing value

                    -- Find folder by name
                    repeat with anAccount in accounts
                        repeat with aFolder in folders of anAccount
                            if name of aFolder is "\(folderName)" then
                                set destFolder to aFolder
                                exit repeat
                            end if
                        end repeat
                        if destFolder is not missing value then exit repeat
                    end repeat

                    -- Create folder if not found
                    if destFolder is missing value then
                        tell first account
                            set destFolder to make new folder with properties {name:"\(folderName)"}
                        end tell
                    end if

                    set newNote to make new note at destFolder with properties {name:"\(escapedName)", body:"\(escapedHTML)"}
                    return id of newNote & "|||" & name of newNote
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            """
        } else {
            // Create in default location
            script = """
            tell application "Notes"
                try
                    set newNote to make new note with properties {name:"\(escapedName)", body:"\(escapedHTML)"}
                    return id of newNote & "|||" & name of newNote
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            """
        }

        do {
            let result = try runAppleScript(script)
            if result.hasPrefix("error:") {
                let bridgeError = BridgeError(message: result, code: "CREATE_NOTE_ERROR")
                outputError(bridgeError)
                throw ExitCode.failure
            }

            let parts = result.components(separatedBy: "|||")
            if parts.count >= 2 {
                try outputJSON(["success": true, "id": parts[0], "name": parts[1]])
            } else {
                try outputJSON(["success": true, "result": result])
            }
        } catch let error as BridgeError {
            outputError(error)
            throw ExitCode.failure
        }
    }
}
