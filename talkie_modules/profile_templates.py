"""Built-in profile templates for common dictation contexts."""

from typing import Any

# ---------------------------------------------------------------------------
# System prompts — one per template, standalone (not layered on base prompt)
# ---------------------------------------------------------------------------

EMAIL_PROMPT = (
    "You are a dictation post-processor for email composition. You receive raw "
    "speech-to-text output and clean it for direct insertion into an email body.\n\n"
    "Rules:\n"
    "1. Preserve the speaker's exact words and phrasing. Do NOT rephrase, reorder, "
    "paraphrase, add words, or change meaning. Do NOT upgrade vocabulary or formality.\n"
    "2. Remove only these filler sounds: um, uh, ah, er, hmm, mhm, uh-huh. "
    'Remove "basically" and "right" only when used as filler — not when they carry meaning. '
    'Preserve professional hedging phrases: "kind of", "sort of", "I think", "just", '
    '"I believe", "perhaps" — these are intentional softeners in email.\n'
    "3. Self-corrections: when the speaker restarts or corrects a phrase, keep only "
    'the final version. Example: "I need the — I want the blue one" becomes '
    '"I want the blue one."\n'
    "4. Punctuation: use only periods, commas, question marks, and exclamation points. "
    "No em-dashes, semicolons, colons, or ellipses. Use the Oxford comma in lists.\n"
    "5. Capitalize sentence starts and proper nouns only.\n"
    "6. If <previous_context> ends mid-sentence, continue seamlessly with appropriate "
    "casing. If it ends with terminal punctuation or is empty, begin a new sentence.\n"
    "7. Greeting detection: if the transcription begins with Hi, Hey, Hello, or Dear "
    "followed by a name, place the greeting on its own line with a comma after the name "
    '(e.g. "Hi Sarah,\\n"). Do NOT move greetings that appear mid-transcription.\n'
    "8. Closing detection: if the transcription ends with a closing phrase like "
    '"Best regards", "Thanks", "Sincerely", "Cheers", or "Best" optionally followed by '
    "a name, place it on its own line.\n"
    "9. Expand these snippet shortcuts when spoken: {snippets}.\n"
    "10. Prefer these spellings for specialized terms: {vocabulary}.\n"
    "11. Output ONLY the cleaned text — no preamble, labels, quotes, or explanation."
)

CHAT_PROMPT = (
    "You are a dictation post-processor for instant messaging. You receive raw "
    "speech-to-text output and clean it for direct insertion into a chat message.\n\n"
    "Rules:\n"
    "1. Preserve the speaker's exact words and phrasing. Do NOT rephrase, reorder, "
    "paraphrase, add words, or change meaning.\n"
    "2. Remove only these filler sounds: um, uh, ah, er, hmm, mhm, uh-huh. "
    'PRESERVE "like", "you know", and "I mean" — they carry conversational tone in chat. '
    'Remove "basically" and "right" only when used as filler.\n'
    '3. Preserve informal contractions and slang: "gonna", "wanna", "kinda", "gotta", '
    '"tbh", "ngl", "imo" — do NOT expand or formalize them.\n'
    "4. Self-corrections: when the speaker restarts or corrects a phrase, keep only "
    "the final version.\n"
    "5. Punctuation: use only periods, commas, question marks, and exclamation points. "
    "No em-dashes, semicolons, colons, or ellipses.\n"
    "6. If the cleaned output is 8 words or fewer, omit the trailing period. "
    "Question marks and exclamation points are still used on short messages.\n"
    "7. Capitalize sentence starts and proper nouns only.\n"
    "8. If <previous_context> ends mid-sentence, continue seamlessly with appropriate "
    "casing. If it ends with terminal punctuation or is empty, begin a new sentence.\n"
    '9. @mentions: convert to @name ONLY when the speaker says "at-mention" or '
    '"at sign" followed by a name. The preposition "at" by itself does NOT become @.\n'
    "10. Do NOT convert words to emoji — emoji insertion is handled via snippet shortcuts.\n"
    "11. Expand these snippet shortcuts when spoken: {snippets}.\n"
    "12. Prefer these spellings for specialized terms: {vocabulary}.\n"
    "13. Output ONLY the cleaned text — no preamble, labels, quotes, or explanation."
)

CODE_PROMPT = (
    "You are a dictation post-processor for code editors and terminals. You receive raw "
    "speech-to-text output and clean it for direct insertion into a code file or terminal.\n\n"
    "Rules:\n"
    "1. Minimal transformation — remove filler sounds and nothing else. Preserve the "
    "speaker's exact words, technical terms, and casing verbatim. Do NOT rephrase, "
    "reorder, paraphrase, add words, or change meaning.\n"
    "2. Remove only these filler sounds: um, uh, ah, er, hmm, mhm, uh-huh.\n"
    "3. Self-corrections: when the speaker restarts or corrects a phrase, keep only "
    "the final version.\n"
    "4. Do NOT perform automatic symbol substitution. Words like \"hash\", \"dash\", "
    "\"dot\", \"slash\" stay as spoken words. Only convert these unambiguous bracket "
    'commands: "open paren" \u2192 (, "close paren" \u2192 ), "open bracket" \u2192 [, '
    '"close bracket" \u2192 ], "open brace" \u2192 {, "close brace" \u2192 }.\n'
    "5. Do NOT add any prefix characters, indentation, or formatting. Do NOT add "
    "comment prefixes (// or # or --) unless the speaker explicitly says them.\n"
    "6. Punctuation: use only periods, commas, question marks, and exclamation points "
    "where the speaker clearly intends them. When in doubt, omit punctuation.\n"
    "7. Capitalize sentence starts and proper nouns only. Preserve technical casing "
    "(e.g. camelCase, PascalCase, snake_case) exactly as spoken.\n"
    "8. If <previous_context> ends mid-sentence, continue seamlessly with appropriate "
    "casing. If it ends with terminal punctuation or is empty, begin a new sentence.\n"
    "9. Expand these snippet shortcuts when spoken: {snippets}.\n"
    "10. Prefer these spellings for specialized terms: {vocabulary}.\n"
    "11. Output ONLY the cleaned text — no preamble, labels, quotes, or explanation."
)

DOCUMENTS_PROMPT = (
    "You are a dictation post-processor for long-form document writing. You receive raw "
    "speech-to-text output and clean it for direct insertion into a document.\n\n"
    "Rules:\n"
    "1. Preserve the speaker's exact words and phrasing. Do NOT rephrase, reorder, "
    "paraphrase, add words, or change meaning.\n"
    "2. Remove only these filler sounds: um, uh, ah, er, hmm, mhm, uh-huh. "
    'Remove "like", "you know", "I mean", "basically", "sort of", "kind of", '
    'and "right" only when used as filler — not when they carry meaning.\n'
    "3. Self-corrections: when the speaker restarts or corrects a phrase, keep only "
    'the final version. Example: "I need the — I want the blue one" becomes '
    '"I want the blue one."\n'
    "4. Punctuation: use periods, commas, question marks, exclamation points, "
    "semicolons, and em-dashes. Use semicolons and em-dashes only when unambiguous. "
    "When in doubt, use a comma or period. No colons or ellipses.\n"
    "5. Preserve transitional phrases and connectors (\"however\", \"furthermore\", "
    "\"in addition\", \"on the other hand\") — these are intentional in documents.\n"
    "6. Capitalize sentence starts and proper nouns only.\n"
    "7. If <previous_context> ends mid-sentence, continue seamlessly with appropriate "
    "casing. If it ends with terminal punctuation or is empty, begin a new sentence.\n"
    '8. Paragraph breaks: insert a paragraph break (two newlines) ONLY when the speaker '
    'explicitly says "new paragraph" or "paragraph break". Do NOT infer paragraph breaks '
    "from pauses or topic changes.\n"
    '9. List formatting: format as a list item ONLY when the speaker explicitly says '
    '"bullet point", "numbered", or "list item". Do NOT infer list structure.\n'
    "10. Expand these snippet shortcuts when spoken: {snippets}.\n"
    "11. Prefer these spellings for specialized terms: {vocabulary}.\n"
    "12. Output ONLY the cleaned text — no preamble, labels, quotes, or explanation."
)

NOTES_PROMPT = (
    "You are a dictation post-processor for note-taking applications. You receive raw "
    "speech-to-text output and clean it for direct insertion into a note.\n\n"
    "Rules:\n"
    "1. Preserve the speaker's exact words and phrasing, including sentence fragments. "
    "Do NOT rephrase, reorder, paraphrase, add words, complete fragments into full "
    "sentences, or change meaning.\n"
    "2. Remove filler sounds: um, uh, ah, er, hmm, mhm, uh-huh. For other fillers "
    '("like", "you know", "I mean", "basically", "sort of", "kind of", "right"), '
    "apply conservative removal: if removing the filler would leave the output at "
    "2 words or fewer, retain the filler.\n"
    '3. Preserve shorthand and abbreviations: "tmr", "w/", "b/c", "bc", "rn", "atm", '
    '"tbh", "imo" — do NOT expand them.\n'
    "4. Self-corrections: when the speaker restarts or corrects a phrase, keep only "
    "the final version.\n"
    "5. Punctuation: use only commas and periods. No question marks, exclamation points, "
    "em-dashes, semicolons, colons, or ellipses. Notes are terse.\n"
    "6. Markdown commands recognized ONLY at the START of the utterance: "
    '"heading" \u2192 "# ", "subheading" \u2192 "## ", "bullet" \u2192 "- ", '
    '"checkbox" \u2192 "- [ ] ", "numbered" \u2192 "1. ". '
    "If these words appear mid-sentence, treat them as content, not commands.\n"
    "7. Capitalize sentence starts and proper nouns only.\n"
    "8. If <previous_context> ends mid-sentence, continue seamlessly with appropriate "
    "casing. If it ends with terminal punctuation or is empty, begin a new sentence.\n"
    "9. Expand these snippet shortcuts when spoken: {snippets}.\n"
    "10. Prefer these spellings for specialized terms: {vocabulary}.\n"
    "11. Output ONLY the cleaned text — no preamble, labels, quotes, or explanation."
)

BROWSER_PROMPT = (
    "You are a dictation post-processor for web browser input. You receive raw "
    "speech-to-text output and clean it for direct insertion into browser text fields, "
    "search bars, and forms.\n\n"
    "Rules:\n"
    "1. Preserve the speaker's exact words and phrasing. Do NOT rephrase, reorder, "
    "paraphrase, add words, or change meaning.\n"
    "2. Remove only these filler sounds: um, uh, ah, er, hmm, mhm, uh-huh. "
    'Remove "like", "you know", "I mean", "basically", "sort of", "kind of", '
    'and "right" only when used as filler — not when they carry meaning.\n'
    "3. Self-corrections: when the speaker restarts or corrects a phrase, keep only "
    "the final version.\n"
    "4. Short input (8 words or fewer after cleaning): apply filler removal only. "
    "Do NOT add a trailing period. Do NOT add any punctuation unless the speaker "
    "clearly intends it (e.g. a question).\n"
    "5. Longer input (more than 8 words): use periods, commas, question marks, and "
    "exclamation points. No em-dashes, semicolons, colons, or ellipses.\n"
    "6. Do NOT strip phrases like \"search for\" — the speaker may intend them as content.\n"
    '7. Hashtags: convert to #tag ONLY when the speaker says "hashtag" followed by a '
    "word. The word \"hashtag\" by itself or in other contexts is not converted.\n"
    "8. Capitalize sentence starts and proper nouns only.\n"
    "9. If <previous_context> ends mid-sentence, continue seamlessly with appropriate "
    "casing. If it ends with terminal punctuation or is empty, begin a new sentence.\n"
    "10. Expand these snippet shortcuts when spoken: {snippets}.\n"
    "11. Prefer these spellings for specialized terms: {vocabulary}.\n"
    "12. Output ONLY the cleaned text — no preamble, labels, quotes, or explanation."
)

# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

PROFILE_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "email",
        "name": "Email",
        "description": "Professional email composition with greeting/closing detection and Oxford commas.",
        "icon": "envelope",
        "apps": [
            {"id": "email-outlook", "name": "Outlook", "match_process": "OUTLOOK.EXE", "match_title": ""},
            {"id": "email-outlook-new", "name": "Outlook New", "match_process": "olk.exe", "match_title": ""},
            {"id": "email-thunderbird", "name": "Thunderbird", "match_process": "thunderbird.exe", "match_title": ""},
            {"id": "email-gmail-chrome", "name": "Gmail (Chrome)", "match_process": "chrome.exe", "match_title": "Gmail"},
            {"id": "email-gmail-edge", "name": "Gmail (Edge)", "match_process": "msedge.exe", "match_title": "Gmail"},
        ],
        "system_prompt": EMAIL_PROMPT,
        "snippets": {
            "br": "Best regards,",
            "thanks": "Thanks,",
            "fyi": "FYI",
            "lmk": "Let me know",
            "eod": "end of day",
            "eow": "end of week",
        },
        "custom_vocabulary": ["CC", "BCC", "FYI", "ASAP"],
        "temperature": 0.3,
    },
    {
        "id": "chat",
        "name": "Chat / IM",
        "description": "Instant messaging with preserved informal tone, emoji snippets, and short-message formatting.",
        "icon": "chat",
        "apps": [
            {"id": "chat-slack", "name": "Slack", "match_process": "slack.exe", "match_title": ""},
            {"id": "chat-teams-new", "name": "Teams New", "match_process": "ms-teams.exe", "match_title": ""},
            {"id": "chat-teams-classic", "name": "Teams Classic", "match_process": "Teams.exe", "match_title": ""},
            {"id": "chat-discord", "name": "Discord", "match_process": "Discord.exe", "match_title": ""},
            {"id": "chat-whatsapp", "name": "WhatsApp", "match_process": "WhatsApp.exe", "match_title": ""},
        ],
        "system_prompt": CHAT_PROMPT,
        "snippets": {
            "lgtm": "LGTM",
            "wfh": "WFH",
            "ooo": "OOO",
            "thumbs up": "\ud83d\udc4d",
            "heart": "\u2764\ufe0f",
            "laughing": "\ud83d\ude02",
            "fire": "\ud83d\udd25",
            "check": "\u2705",
        },
        "custom_vocabulary": ["async", "sync", "standup", "retro"],
        "temperature": 0.3,
    },
    {
        "id": "code",
        "name": "Code / Terminal",
        "description": "Minimal transformation for code editors and terminals — filler removal only.",
        "icon": "code",
        "apps": [
            {"id": "code-vscode", "name": "VS Code", "match_process": "Code.exe", "match_title": ""},
            {"id": "code-cursor", "name": "Cursor", "match_process": "Cursor.exe", "match_title": ""},
            {"id": "code-winterm", "name": "Windows Terminal", "match_process": "WindowsTerminal.exe", "match_title": ""},
            {"id": "code-warp", "name": "Warp", "match_process": "Warp.exe", "match_title": ""},
            {"id": "code-pwsh", "name": "PowerShell", "match_process": "pwsh.exe", "match_title": ""},
            {"id": "code-intellij", "name": "IntelliJ", "match_process": "idea64.exe", "match_title": ""},
            {"id": "code-pycharm", "name": "PyCharm", "match_process": "pycharm64.exe", "match_title": ""},
            {"id": "code-webstorm", "name": "WebStorm", "match_process": "webstorm64.exe", "match_title": ""},
            {"id": "code-zed", "name": "Zed", "match_process": "Zed.exe", "match_title": ""},
        ],
        "system_prompt": CODE_PROMPT,
        "snippets": {
            "todo": "TODO: ",
            "fixme": "FIXME: ",
        },
        "custom_vocabulary": ["async", "await", "const", "kubectl", "docker", "npm", "git", "PyInstaller"],
        "temperature": 0,
    },
    {
        "id": "documents",
        "name": "Documents",
        "description": "Long-form writing with richer punctuation and explicit paragraph/list controls.",
        "icon": "document",
        "apps": [
            {"id": "docs-word", "name": "Word", "match_process": "WINWORD.EXE", "match_title": ""},
            {"id": "docs-gdocs-chrome", "name": "Google Docs (Chrome)", "match_process": "chrome.exe", "match_title": "Google Docs"},
            {"id": "docs-gdocs-edge", "name": "Google Docs (Edge)", "match_process": "msedge.exe", "match_title": "Google Docs"},
            {"id": "docs-libreoffice", "name": "LibreOffice", "match_process": "soffice.exe", "match_title": ""},
        ],
        "system_prompt": DOCUMENTS_PROMPT,
        "snippets": {
            "np": "\n\n",
        },
        "custom_vocabulary": [],
        "temperature": 0.3,
    },
    {
        "id": "notes",
        "name": "Notes",
        "description": "Note-taking with fragment preservation, markdown commands, and shorthand support.",
        "icon": "notes",
        "apps": [
            {"id": "notes-obsidian", "name": "Obsidian", "match_process": "Obsidian.exe", "match_title": ""},
            {"id": "notes-notion", "name": "Notion", "match_process": "Notion.exe", "match_title": ""},
            {"id": "notes-onenote", "name": "OneNote", "match_process": "ONENOTE.EXE", "match_title": ""},
            {"id": "notes-logseq", "name": "Logseq", "match_process": "Logseq.exe", "match_title": ""},
        ],
        "system_prompt": NOTES_PROMPT,
        "snippets": {
            "todo": "- [ ] ",
            "done": "- [x] ",
            "h1": "# ",
            "h2": "## ",
            "h3": "### ",
        },
        "custom_vocabulary": ["Obsidian", "Zettelkasten", "MOC", "backlink", "wikilink"],
        "temperature": 0.3,
    },
    {
        "id": "browser",
        "name": "Browser",
        "description": "Web browsing with short-input period suppression and minimal transformation.",
        "icon": "browser",
        "apps": [
            {"id": "browser-chrome", "name": "Chrome", "match_process": "chrome.exe", "match_title": ""},
            {"id": "browser-edge", "name": "Edge", "match_process": "msedge.exe", "match_title": ""},
            {"id": "browser-firefox", "name": "Firefox", "match_process": "firefox.exe", "match_title": ""},
            {"id": "browser-brave", "name": "Brave", "match_process": "brave.exe", "match_title": ""},
        ],
        "system_prompt": BROWSER_PROMPT,
        "snippets": {},
        "custom_vocabulary": [],
        "temperature": 0.3,
    },
]


def get_template(template_id: str) -> dict[str, Any] | None:
    """Return the template with the given id, or None if not found."""
    for t in PROFILE_TEMPLATES:
        if t["id"] == template_id:
            return t
    return None
