const fields = ["enabled", "blockHighSeverity"];

async function load() {
  const cur = await chrome.storage.local.get(fields);
  for (const k of fields) {
    const el = document.getElementById(k);
    el.checked = cur[k] !== false;
    el.addEventListener("change", async () => {
      await chrome.storage.local.set({ [k]: el.checked });
    });
  }
}

load();
