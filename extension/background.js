/* Heimdall Sentinel — background service worker.
 *
 * Minimal: just tracks install + manages chrome.storage defaults. Future:
 * sync custom rules with the user's Heimdall account.
 */

chrome.runtime.onInstalled.addListener(async () => {
  const cur = await chrome.storage.local.get(["enabled", "blockHighSeverity"]);
  if (cur.enabled === undefined) {
    await chrome.storage.local.set({ enabled: true, blockHighSeverity: true });
  }
});
