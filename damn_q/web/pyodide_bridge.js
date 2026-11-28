/* Non-blocking Web Worker bridge for static (Pyodide) deployments of the DAMN-Q workbench.
 *
 * Load this script before app.js on static hosts (e.g., GitHub Pages) with
 * `window.DAMNQ_PYODIDE_CONFIG = { workerUrl, bundleUrl, examplesBaseUrl, examplesIndex }`.
 * It intercepts `/api/manifest`, `/api/validate`, `/api/run`, and `/api/examples/*`
 * and dispatches all Python execution to `pyodide_worker.js` so the main UI thread
 * stays completely responsive during long simulations.
 */

(function installDamnQWorkerBridge() {
  const cfg = window.DAMNQ_PYODIDE_CONFIG;
  if (!cfg) return;

  const workerUrl = cfg.workerUrl || "./pyodide_worker.js";
  const worker = new Worker(workerUrl);
  let nextId = 1;
  const pending = new Map();

  worker.onmessage = (event) => {
    const { id, ok, data, error } = event.data || {};
    const entry = pending.get(id);
    if (!entry) return;
    pending.delete(id);
    if (ok) entry.resolve(data);
    else entry.reject(new Error(error || "DAMN-Q worker error"));
  };

  worker.onerror = (err) => {
    for (const entry of pending.values()) {
      entry.reject(new Error(err.message || "DAMN-Q worker crashed"));
    }
    pending.clear();
  };

  function callWorker(action, payload) {
    const id = nextId++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      worker.postMessage({ id, action, payload: Object.assign({ config: cfg }, payload || {}) });
    });
  }

  function jsonResponse(obj, status = 200) {
    return new Response(JSON.stringify(obj), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }

  const origFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input.url;

    if (url === "/api/manifest") {
      const data = await callWorker("manifest");
      return jsonResponse(data);
    }
    if (url === "/api/examples") {
      if (Array.isArray(cfg.examplesIndex)) {
        return jsonResponse({ examples: cfg.examplesIndex });
      }
      return origFetch((cfg.examplesBaseUrl || "./experiments/") + "index.json");
    }
    if (url.startsWith("/api/examples/")) {
      const name = decodeURIComponent(url.slice("/api/examples/".length));
      return origFetch((cfg.examplesBaseUrl || "./experiments/") + name);
    }
    if (url === "/api/validate") {
      const exp = JSON.parse((init && init.body) || "{}");
      const data = await callWorker("validate", { experiment: exp });
      return jsonResponse(data, data.valid ? 200 : 400);
    }
    if (url === "/api/run") {
      const exp = JSON.parse((init && init.body) || "{}");
      try {
        const data = await callWorker("run", { experiment: exp });
        if (!data.ok) return jsonResponse({ ok: false, errors: data.errors || ["Run failed"] }, 400);
        return jsonResponse({ ok: true, result: data.result });
      } catch (err) {
        return jsonResponse({ ok: false, error: err.message }, 400);
      }
    }
    return origFetch(input, init);
  };

  // Warm up Pyodide in the background immediately without blocking the UI
  callWorker("init").catch(() => {});
})();
