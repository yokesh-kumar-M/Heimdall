# Heimdall Sentinel — browser extension

A Manifest V3 extension that runs the **Heimdall L1 deterministic scanner**
locally on the chat textareas of:

- chatgpt.com
- claude.ai
- gemini.google.com
- copilot.microsoft.com
- perplexity.ai

When you're about to paste or send a prompt that contains a secret, an API
key, PII, invisible Unicode, or a jailbreak phrase, Sentinel pops a small
warning in the corner of the page. For high-severity hits (secrets / PII)
the send is blocked until you click "Send anyway".

**No network calls.** Everything runs in your browser. The scanner is a
direct JS port of `app/scanners/deterministic.py` from the server-side
Heimdall proxy, so rules stay in sync with what the gateway would block.

## Install (developer mode)

1. Open `chrome://extensions` (or `edge://extensions`).
2. Toggle **Developer mode** on.
3. Click **Load unpacked**.
4. Pick this `extension/` folder.

## Icons

PNG icons live in `icons/`. If they're missing, the extension still works —
Chrome will use a placeholder. To replace, swap in 16×16, 48×48, 128×128 PNGs.

## Roadmap

- Optional: sync custom rules from your Heimdall account (`sk_hd_…` key).
- Optional: forward warnings to the cloud telemetry as anonymous events.
