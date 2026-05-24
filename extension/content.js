/* Heimdall Sentinel — content script.
 *
 * Hooks paste + Enter on the chat textareas of popular AI sites. When the
 * scanner finds anything noteworthy, we show a non-blocking floating warning
 * and (for high-severity items: secrets, PII, jailbreaks) prevent the action
 * unless the user explicitly clicks "Send anyway".
 *
 * No network calls, ever. Optional: future versions can sync settings with
 * the user's Heimdall account via the popup.
 */

(function () {
  "use strict";

  const HIGH_SEVERITY = ["secret::", "invisible_unicode"];

  function isHighSeverity(violations) {
    return violations.some((v) => HIGH_SEVERITY.some((p) => v.rule.startsWith(p)));
  }

  // ---- Floating warning UI ----
  function ensureBanner() {
    let banner = document.getElementById("__heimdall_banner");
    if (banner) return banner;
    banner = document.createElement("div");
    banner.id = "__heimdall_banner";
    banner.style.cssText = `
      position: fixed; bottom: 24px; right: 24px; z-index: 2147483647;
      max-width: 380px; padding: 14px 16px; border-radius: 12px;
      background: rgba(20, 18, 30, 0.96); color: #fff;
      box-shadow: 0 10px 40px -10px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.08);
      font: 13px/1.45 system-ui, sans-serif; display: none;
      backdrop-filter: blur(10px) saturate(140%);
    `;
    document.body.appendChild(banner);
    return banner;
  }

  function showWarning(result, onContinue) {
    const banner = ensureBanner();
    const list = result.violations
      .map((v) => `<li style="margin-top:4px"><b style="color:#ffd166">${v.rule}</b> · ${v.snippet}</li>`)
      .join("");
    banner.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <strong style="color:#ff6b9b">⚠ Heimdall Sentinel</strong>
        <button id="__h_close" style="all:unset;cursor:pointer;color:#aaa;padding:2px 6px">✕</button>
      </div>
      <p style="margin:6px 0 4px;color:#bbb">Your prompt looks risky for a public LLM:</p>
      <ul style="margin:4px 0 0;padding-left:20px">${list}</ul>
      ${onContinue ? `
      <div style="margin-top:10px;display:flex;gap:8px;justify-content:flex-end">
        <button id="__h_cancel" style="all:unset;cursor:pointer;padding:5px 10px;border-radius:6px;background:rgba(255,255,255,0.06)">Cancel</button>
        <button id="__h_send" style="all:unset;cursor:pointer;padding:5px 10px;border-radius:6px;background:#ff6b9b;color:#1a0c14;font-weight:600">Send anyway</button>
      </div>` : ""}
    `;
    banner.style.display = "block";
    banner.querySelector("#__h_close").onclick = () => (banner.style.display = "none");
    if (onContinue) {
      banner.querySelector("#__h_cancel").onclick = () => (banner.style.display = "none");
      banner.querySelector("#__h_send").onclick = () => {
        banner.style.display = "none";
        onContinue();
      };
    }
    if (!onContinue) {
      setTimeout(() => (banner.style.display = "none"), 6000);
    }
  }

  // ---- Hooks ----
  document.addEventListener(
    "paste",
    (e) => {
      const text = (e.clipboardData || window.clipboardData)?.getData("text") || "";
      const result = self.HeimdallScanner.scan(text);
      if (!result.safe) showWarning(result);
    },
    true,
  );

  // Intercept the Enter key on chat boxes. If high-severity, we block,
  // capture the original handler chain, and re-fire only if the user clicks
  // "Send anyway". For low-severity we just warn (toast-style).
  let pendingAllowed = false;
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key !== "Enter" || e.shiftKey) return;
      const target = e.target;
      if (!target || !(target instanceof HTMLElement)) return;
      const tag = target.tagName.toLowerCase();
      const text =
        tag === "textarea"
          ? target.value
          : target.isContentEditable
          ? target.innerText
          : "";
      if (!text) return;
      const result = self.HeimdallScanner.scan(text);
      if (result.safe) return;
      if (pendingAllowed) {
        pendingAllowed = false;
        return;
      }
      if (!isHighSeverity(result.violations)) {
        showWarning(result);
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      showWarning(result, () => {
        pendingAllowed = true;
        // Refire as a synthetic keydown so the page's own listeners pick it up.
        target.focus();
        target.dispatchEvent(
          new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }),
        );
      });
    },
    true,
  );
})();
