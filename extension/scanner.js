/* Heimdall Sentinel — L1 deterministic scanner, ported to vanilla JS.
 *
 * Runs entirely in the page (no network call). Mirrors the patterns in
 * app/scanners/deterministic.py so blocks here line up with what the
 * server-side proxy would do.
 *
 * Exports a global `HeimdallScanner.scan(text)` that returns:
 *   { safe: boolean, sanitized: string, violations: [{rule, category, snippet}] }
 */

(function () {
  "use strict";

  const INVISIBLE_RANGES = [
    [0x200B, 0x200B], [0x200C, 0x200C], [0x200D, 0x200D],
    [0x2060, 0x2060], [0xFEFF, 0xFEFF],
    [0x202A, 0x202E], [0x2066, 0x2069],
    [0xE0020, 0xE007F], // Tags block (ASCII smuggling)
    [0x180E, 0x180E],   // Mongolian Vowel Separator
  ];

  function isInvisible(cp) {
    for (const [lo, hi] of INVISIBLE_RANGES) {
      if (cp >= lo && cp <= hi) return true;
    }
    return false;
  }

  function stripInvisible(text) {
    let out = "";
    let count = 0;
    const codepoints = new Set();
    for (const ch of text) {
      const cp = ch.codePointAt(0);
      if (isInvisible(cp)) {
        count++;
        codepoints.add(cp);
      } else {
        out += ch;
      }
    }
    return { sanitized: out.normalize("NFKC"), count, codepoints: [...codepoints] };
  }

  const JAILBREAK = [
    ["ignore_previous", /ignore\s+(?:all\s+|the\s+|your\s+|any\s+)?(?:previous|prior|earlier|above)\s+(?:instructions?|prompts?|rules?|directives?)/i],
    ["disregard_previous", /disregard\s+(?:all\s+|the\s+|your\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|rules?)/i],
    ["forget_everything", /forget\s+(?:everything|all|what)\s+(?:you|i)\s+(?:were\s+told|said|know)/i],
    ["dan_persona", /\b(?:do\s+anything\s+now|you\s+are\s+DAN|act\s+as\s+DAN|enter\s+DAN\s+mode)\b/i],
    ["developer_mode", /\b(?:developer\s+mode\s+(?:enabled|on|activated)|enable\s+developer\s+mode|dev[\s-]?mode\s+on)\b/i],
    ["jailbreak_keyword", /\b(?:jailbreak|jailbroken|unfiltered\s+mode|no\s+restrictions?)\b/i],
    ["role_reveal", /\b(?:reveal|print|show|repeat|output)\s+(?:your\s+)?(?:system\s+prompt|initial\s+prompt|hidden\s+instructions?)\b/i],
  ];

  const SECRETS = [
    ["aws_access_key_id", /\b(?:AKIA|ASIA|AIDA|AGPA|AROA|AIPA|ANPA|ANVA)[A-Z0-9]{16}\b/, "AWS access key"],
    ["github_token", /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b/, "GitHub token"],
    ["openai_api_key", /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/, "OpenAI key"],
    ["anthropic_api_key", /\bsk-ant-[A-Za-z0-9_-]{20,}\b/, "Anthropic key"],
    ["google_api_key", /\bAIza[0-9A-Za-z_-]{35}\b/, "Google key"],
    ["slack_token", /\bxox[abpr]-[0-9A-Za-z-]{10,}\b/, "Slack token"],
    ["private_key_block", /-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED) PRIVATE KEY-----/, "Private key"],
    ["us_ssn", /\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b/, "US SSN"],
  ];

  const CC_RE = /\b(?:\d[ -]?){13,19}\b/g;

  function luhn(digits) {
    let total = 0;
    const parity = digits.length % 2;
    for (let i = 0; i < digits.length; i++) {
      let d = digits.charCodeAt(i) - 48;
      if (i % 2 === parity) {
        d *= 2;
        if (d > 9) d -= 9;
      }
      total += d;
    }
    return total % 10 === 0;
  }

  function scan(text) {
    if (!text) return { safe: true, sanitized: "", violations: [] };

    const { sanitized, count: invisCount, codepoints } = stripInvisible(text);
    const violations = [];

    if (invisCount > 0) {
      violations.push({
        rule: "invisible_unicode",
        category: "LLM01: Prompt Injection",
        snippet: `${invisCount} invisible char(s): ${codepoints.map((c) => "U+" + c.toString(16).toUpperCase()).join(", ")}`,
      });
    }

    for (const [name, re] of JAILBREAK) {
      const m = sanitized.match(re);
      if (m) {
        violations.push({
          rule: `jailbreak::${name}`,
          category: "LLM01: Prompt Injection",
          snippet: m[0].slice(0, 120),
        });
      }
    }

    for (const [name, re, label] of SECRETS) {
      const m = sanitized.match(re);
      if (m) {
        const snippet = m[0].length > 12 ? m[0].slice(0, 4) + "…" + m[0].slice(-4) : m[0];
        violations.push({
          rule: `secret::${name}`,
          category: "LLM02: Sensitive Information Disclosure",
          snippet: `${label}: ${snippet}`,
        });
      }
    }

    let m;
    CC_RE.lastIndex = 0;
    while ((m = CC_RE.exec(sanitized)) !== null) {
      const digits = m[0].replace(/\D/g, "");
      if (digits.length >= 13 && digits.length <= 19 && luhn(digits)) {
        violations.push({
          rule: "secret::credit_card",
          category: "LLM02: Sensitive Information Disclosure",
          snippet: `Card: ${digits.slice(0, 4)}****${digits.slice(-4)}`,
        });
      }
    }

    return {
      safe: violations.length === 0,
      sanitized,
      violations,
    };
  }

  self.HeimdallScanner = { scan };
})();
