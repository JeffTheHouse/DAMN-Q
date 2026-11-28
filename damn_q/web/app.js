(() => {
  "use strict";

  const POS_SCALE_X = 2.08;
  const POS_SCALE_Y = 2;
  const MAX_FLOW_PULSES = 24;
  const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");
  const MODULE_STYLES = {
    source: ["Source", "✦"],
    quantum_memory: ["Memory", "▤"],
    entanglement_swapper: ["Bell swap", "⋈"],
    measurer: ["Measure", "⊙"],
    orchestrator: ["Swap control", "⇄"],
    pauli_corrector: ["Pauli correction", "±"],
    measurer_memory_paired: ["Triggered measure", "◈"],
    classic_data_reader: ["Outcome counter", "#"],
    detector_module: ["Arrival monitor", "≋"],
    endpoint_probe: ["State probe", "◎"],
  };
  const POS_OFFSET_X = 40;
  const POS_OFFSET_Y = 30;

  const state = {
    manifest: null,
    examples: [],
    doc: null,
    selected: null, // { type: "component", id } | { type: "connection", index } | null
    wiring: null,   // { component, port, kind } | null
    lastResult: null,
    pendingRun: false,
    undoRemoval: null,
    zoom: 1,
    flow: null,
    flowTimeout: null,
    graphRevision: 0,
  };

  const els = {
    versionBadge: document.getElementById("version-badge"),
    exampleSelect: document.getElementById("example-select"),
    btnLoadExample: document.getElementById("btn-load-example"),
    btnImport: document.getElementById("btn-import"),
    fileImport: document.getElementById("file-import"),
    btnExport: document.getElementById("btn-export"),
    runUntil: document.getElementById("run-until"),
    runSeed: document.getElementById("run-seed"),
    btnFit: document.getElementById("btn-fit"),
    zoomIn: document.getElementById("btn-zoom-in"),
    zoomOut: document.getElementById("btn-zoom-out"),
    zoomLabel: document.getElementById("zoom-label"),
    btnReplay: document.getElementById("btn-replay-flow"),
    canvasMessage: document.getElementById("canvas-message"),
    canvasMessageText: document.getElementById("canvas-message-text"),
    btnUndo: document.getElementById("btn-undo-delete"),
    btnDismiss: document.getElementById("btn-dismiss-message"),
    btnValidate: document.getElementById("btn-validate"),
    btnRun: document.getElementById("btn-run"),
    paletteList: document.getElementById("palette-list"),
    wiringBanner: document.getElementById("wiring-banner"),
    wiringText: document.getElementById("wiring-text"),
    btnCancelWire: document.getElementById("btn-cancel-wire"),
    canvasViewport: document.getElementById("canvas-viewport"),
    canvasWorld: document.getElementById("canvas-world"),
    edgeLayer: document.getElementById("edge-layer"),
    nodeLayer: document.getElementById("node-layer"),
    inspectorTitle: document.getElementById("inspector-title"),
    btnSelectExp: document.getElementById("btn-select-exp"),
    inspectorBody: document.getElementById("inspector-body"),
    statusPill: document.getElementById("status-pill"),
    resultsBody: document.getElementById("results-body"),
  };

  function toCanvasX(x) {
    return Math.round(x * POS_SCALE_X + POS_OFFSET_X);
  }
  function toCanvasY(y) {
    return Math.round(y * POS_SCALE_Y + POS_OFFSET_Y);
  }
  function fromCanvasX(cx) {
    return Math.round((cx - POS_OFFSET_X) / POS_SCALE_X);
  }
  function fromCanvasY(cy) {
    return Math.round((cy - POS_OFFSET_Y) / POS_SCALE_Y);
  }

  function getComp(id) {
    return state.doc ? state.doc.components.find((c) => c.id === id) : null;
  }

  function getSpec(ctype) {
    return state.manifest && state.manifest.components ? state.manifest.components[ctype] : null;
  }

  function setStatus(kind, label) {
    els.statusPill.className = `status-pill ${kind}`;
    els.statusPill.textContent = label;
  }

  function defaultParamsFor(ctype) {
    const spec = getSpec(ctype);
    const params = {};
    if (!spec) return params;
    for (const [k, p] of Object.entries(spec.parameters || {})) {
      params[k] = p.default;
    }
    return params;
  }

  function nextComponentId(ctype) {
    const existing = new Set((state.doc.components || []).map((c) => c.id));
    let n = 1;
    while (existing.has(`${ctype}_${n}`)) n += 1;
    return `${ctype}_${n}`;
  }

  function ensurePositions(doc) {
    const comps = doc.components || [];
    comps.forEach((c, idx) => {
      if (!c.position || typeof c.position.x !== "number" || typeof c.position.y !== "number") {
        const col = idx % 4;
        const row = Math.floor(idx / 4);
        c.position = { x: 100 + col * 200, y: 120 + row * 160 };
      }
      if (!c.params || typeof c.params !== "object") {
        c.params = defaultParamsFor(c.type);
      }
    });
    if (!Array.isArray(doc.connections)) doc.connections = [];
    if (!Array.isArray(doc.measurements)) doc.measurements = [];
    if (!doc.run || typeof doc.run !== "object") doc.run = { until: 150, seed: 42 };
  }

  function syncToolbarFromDoc() {
    els.runUntil.value = state.doc.run.until ?? "";
    els.runSeed.value = state.doc.run.seed ?? "";
  }

  function buildExportDocument() {
    // Deep-clean clone keeping schema 1.0 structure
    const doc = JSON.parse(JSON.stringify(state.doc));
    doc.schema_version = doc.schema_version || (state.manifest ? state.manifest.schema_version : "1.0");
    // Read Until and Seed from the toolbar at build time, so Run/Export always reflect what the user sees
    // (this does not depend on which DOM event fired). Empty Until is sent as null so validation reports it.
    const untilText = els.runUntil.value.trim();
    doc.run.until = untilText === "" ? null : Number(untilText);
    const seedText = els.runSeed.value.trim();
    doc.run.seed = seedText === "" ? null : parseInt(seedText, 10);
    return doc;
  }

  function setExperiment(doc) {
    dismissCanvasMessage();
    invalidateFlow();
    state.doc = JSON.parse(JSON.stringify(doc));
    ensurePositions(state.doc);
    state.selected = null;
    state.wiring = null;
    state.lastResult = null;
    syncToolbarFromDoc();
    setStatus("neutral", "Ready");
    els.resultsBody.innerHTML =
      '<p class="muted">Run the experiment to see its results and replay qubit flow.</p>';
    renderAll();
  }

  function renderPalette() {
    els.paletteList.innerHTML = "";
    const byCat = {};
    for (const [ctype, spec] of Object.entries(state.manifest.components)) {
      const cat = spec.category || "other";
      if (!byCat[cat]) byCat[cat] = [];
      byCat[cat].push([ctype, spec]);
    }
    const order = ["sources", "memories", "operations", "controllers", "diagnostics", "other"];
    for (const cat of order) {
      const entries = byCat[cat];
      if (!entries || !entries.length) continue;
      const section = document.createElement("div");
      section.className = "palette-category";
      const title = document.createElement("div");
      title.className = "palette-cat-title";
      title.textContent = cat;
      section.appendChild(title);

      for (const [ctype, spec] of entries) {
        const item = document.createElement("button");
        item.className = "palette-item";
        item.type = "button";
        item.draggable = true;
        item.dataset.ctype = ctype;
        item.dataset.family = cat;
        const [, icon] = MODULE_STYLES[ctype] || ["", "□"];
        item.innerHTML = `<span class="module-mark" aria-hidden="true">${icon}</span><span class="palette-item-name">${escapeHtml(spec.label)}</span><span class="palette-item-add" aria-hidden="true">+</span>`;
        item.setAttribute("aria-label", `Add ${spec.label}`);
        item.addEventListener("click", () => addComponent(ctype));
        item.addEventListener("dragstart", (e) => {
          e.dataTransfer.setData("text/plain", ctype);
        });
        section.appendChild(item);
      }
      els.paletteList.appendChild(section);
    }
  }

  function addComponent(ctype, canvasPos = null) {
    if (!state.doc) return;
    dismissCanvasMessage();
    invalidateFlow();
    const id = nextComponentId(ctype);
    let x = 220;
    let y = 180;
    if (canvasPos) {
      x = fromCanvasX(canvasPos.x);
      y = fromCanvasY(canvasPos.y);
    } else {
      const count = state.doc.components.length;
      x = 140 + (count % 5) * 160;
      y = 140 + Math.floor(count / 5) * 140;
    }
    state.doc.components.push({
      id,
      type: ctype,
      params: defaultParamsFor(ctype),
      position: { x, y },
    });
    state.selected = { type: "component", id };
    renderAll();
    focusComponent(id);
  }

  function summarizeComponent(comp) {
    const p = comp.params || {};
    if (comp.type === "quantum_memory") {
      return `${p.capacity ?? 100} slots · ${p.fifo === 0 ? "LIFO" : "FIFO"}`;
    }
    if (comp.type === "source") {
      return `${p.type === 1 ? "|0⟩" : "Bell pair"} · every ${p.delay ?? 1} ticks`;
    }
    if (comp.type === "entanglement_swapper" || comp.type === "pauli_corrector") {
      return `Output delay · ${p.delay ?? 0} ticks`;
    }
    if (comp.type === "measurer" || comp.type === "measurer_memory_paired") {
      return p.x_basis_p ? `X basis · ${Math.round(p.x_basis_p * 100)}%` : "Z basis";
    }
    if (comp.type === "detector_module") {
      return p.trace ? "Arrivals + trace" : "Arrivals only";
    }
    return "";
  }

  function isPortActive(comp, pspec) {
    if (!pspec || !pspec.active_when) return true;
    const spec = getSpec(comp.type);
    const paramsSpec = spec ? spec.parameters || {} : {};
    for (const [k, expected] of Object.entries(pspec.active_when)) {
      const actual = comp.params && comp.params[k] !== undefined
        ? comp.params[k]
        : (paramsSpec[k] ? paramsSpec[k].default : undefined);
      if (actual !== expected) return false;
    }
    return true;
  }

  function portConnectionCount(compId, portName, direction) {
    if (!state.doc) return 0;
    return state.doc.connections.filter((c) =>
      direction === "out"
        ? c.from.component === compId && c.from.port === portName
        : c.to.component === compId && c.to.port === portName
    ).length;
  }

  function classicalTypesCompatible(srcSpec, dstSpec) {
    const srcMt = srcSpec.message_type;
    if (!srcMt) return true;
    if (Array.isArray(dstSpec.accepts)) return dstSpec.accepts.includes(srcMt);
    if (dstSpec.message_type) return dstSpec.message_type === srcMt;
    return true;
  }

  function checkWireAllowed(srcCompId, srcPortName, dstCompId, dstPortName) {
    const srcComp = getComp(srcCompId);
    const dstComp = getComp(dstCompId);
    const srcSpec = srcComp ? getSpec(srcComp.type)?.ports?.[srcPortName] : null;
    const dstSpec = dstComp ? getSpec(dstComp.type)?.ports?.[dstPortName] : null;
    if (!srcSpec || !dstSpec) return { ok: false, reason: "Unknown port" };
    if (srcSpec.direction !== "out" || dstSpec.direction !== "in") {
      return { ok: false, reason: "Connections must go from output to input" };
    }
    if (!isPortActive(srcComp, srcSpec)) {
      return { ok: false, reason: `${srcCompId}.${srcPortName} is inactive under current parameters` };
    }
    if (!isPortActive(dstComp, dstSpec)) {
      return { ok: false, reason: `${dstCompId}.${dstPortName} is inactive under current parameters` };
    }
    if (srcSpec.kind !== dstSpec.kind) {
      return { ok: false, reason: `Incompatible port kinds (${srcSpec.kind} -> ${dstSpec.kind})` };
    }
    if (srcSpec.kind === "classical" && !classicalTypesCompatible(srcSpec, dstSpec)) {
      return {
        ok: false,
        reason: `Incompatible classical message (${srcSpec.message_type} -> ${dstSpec.accepts ? dstSpec.accepts.join("/") : dstSpec.message_type})`,
      };
    }
    const dup = state.doc.connections.some(
      (c) =>
        c.from.component === srcCompId &&
        c.from.port === srcPortName &&
        c.to.component === dstCompId &&
        c.to.port === dstPortName
    );
    if (dup) return { ok: false, reason: "Duplicate connection" };
    if (srcSpec.max_connections != null && portConnectionCount(srcCompId, srcPortName, "out") >= srcSpec.max_connections) {
      return { ok: false, reason: `${srcCompId}.${srcPortName} already has its maximum (${srcSpec.max_connections}) connection` };
    }
    if (dstSpec.max_connections != null && portConnectionCount(dstCompId, dstPortName, "in") >= dstSpec.max_connections) {
      return { ok: false, reason: `${dstCompId}.${dstPortName} already has its maximum (${dstSpec.max_connections}) connection` };
    }
    return { ok: true };
  }

  function renderNodes() {
    els.nodeLayer.innerHTML = "";
    for (const comp of state.doc.components) {
      const spec = getSpec(comp.type);
      const node = document.createElement("div");
      node.className = "node";
      node.dataset.compId = comp.id;
      node.dataset.family = spec?.category || "other";
      node.tabIndex = 0;
      node.setAttribute("role", "group");
      node.setAttribute("aria-label", `${spec?.label || comp.type}, ${comp.id}`);
      node.addEventListener("focus", () => {
        state.selected = { type: "component", id: comp.id };
        renderSelectionAndInspector();
      });
      if (state.selected && state.selected.type === "component" && state.selected.id === comp.id) {
        node.classList.add("selected");
      }
      node.style.left = `${toCanvasX(comp.position.x)}px`;
      node.style.top = `${toCanvasY(comp.position.y)}px`;

      const header = document.createElement("div");
      header.className = "node-header";
      const [shortName, icon] = MODULE_STYLES[comp.type] || [spec?.label || comp.type, "□"];
      header.innerHTML = `<span class="module-mark" aria-hidden="true">${icon}</span><div class="node-heading"><div class="node-type">${escapeHtml(shortName)}</div><div class="node-id" title="${escapeHtml(comp.id)}">${escapeHtml(comp.id)}</div></div>`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "node-remove";
      remove.title = "Delete component (Del)";
      remove.setAttribute("aria-label", `Delete component ${comp.id}`);
      remove.textContent = "×";
      remove.addEventListener("click", (event) => {
        event.stopPropagation();
        deleteComponent(comp.id);
      });
      header.appendChild(remove);
      node.appendChild(header);

      const summary = summarizeComponent(comp);
      if (summary) {
        const sumEl = document.createElement("div");
        sumEl.className = "node-summary";
        sumEl.textContent = summary;
        node.appendChild(sumEl);
      }

      const portsWrap = document.createElement("div");
      portsWrap.className = "node-ports";
      const inCol = document.createElement("div");
      inCol.className = "port-col in";
      const outCol = document.createElement("div");
      outCol.className = "port-col out";

      if (spec && spec.ports) {
        for (const [pname, pspec] of Object.entries(spec.ports)) {
          const portEl = document.createElement("button");
          portEl.type = "button";
          portEl.className = "port";
          portEl.dataset.compId = comp.id;
          portEl.dataset.port = pname;
          portEl.dataset.direction = pspec.direction;
          portEl.dataset.kind = pspec.kind;
          const active = isPortActive(comp, pspec);
          const portDisplay = pspec.label || pname;
          const msgTag = pspec.message_type ? `, ${pspec.message_type}` : "";
          portEl.title = `${comp.id}.${pname} — ${portDisplay} (${pspec.direction}, ${pspec.kind}${msgTag})${active ? "" : " [inactive]"}`;
          portEl.setAttribute("aria-label", `${comp.id}: ${portDisplay} (${pspec.kind} ${pspec.direction})`);
          if (!active) {
            portEl.classList.add("inactive");
            portEl.setAttribute("aria-disabled", "true");
          }

          const dot = `<span class="port-dot ${pspec.kind}"></span>`;
          const label = `<span class="port-name">${escapeHtml(portDisplay)}</span>`;
          portEl.innerHTML = pspec.direction === "in" ? `${dot}${label}` : `${label}${dot}`;

          if (state.wiring) {
            if (state.wiring.component === comp.id && state.wiring.port === pname) {
              portEl.classList.add("wire-source");
            } else if (
              pspec.direction === "in" &&
              checkWireAllowed(state.wiring.component, state.wiring.port, comp.id, pname).ok
            ) {
              portEl.classList.add("wire-compatible");
            }
          }

          portEl.addEventListener("click", (e) => {
            e.stopPropagation();
            handlePortClick(comp.id, pname, pspec);
          });

          if (pspec.direction === "in") inCol.appendChild(portEl);
          else outCol.appendChild(portEl);
        }
      }

      portsWrap.appendChild(inCol);
      portsWrap.appendChild(outCol);
      node.appendChild(portsWrap);

      // Select & drag
      node.addEventListener("mousedown", (e) => {
        if (e.button !== 0 || e.target.closest("button")) return;
        e.stopPropagation();
        state.selected = { type: "component", id: comp.id };
        renderSelectionAndInspector();

        const startX = e.clientX;
        const startY = e.clientY;
        const origLeft = toCanvasX(comp.position.x);
        const origTop = toCanvasY(comp.position.y);

        function onMove(ev) {
          const nx = Math.max(0, origLeft + (ev.clientX - startX) / state.zoom);
          const ny = Math.max(0, origTop + (ev.clientY - startY) / state.zoom);
          node.style.left = `${nx}px`;
          node.style.top = `${ny}px`;
          comp.position.x = fromCanvasX(nx);
          comp.position.y = fromCanvasY(ny);
          renderEdges();
        }
        function onUp() {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
          resizeWorld();
        }
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });

      els.nodeLayer.appendChild(node);
    }
  }

  function getPortCenter(compId, portName) {
    const portEl = els.nodeLayer.querySelector(
      `.port[data-comp-id="${CSS.escape(compId)}"][data-port="${CSS.escape(portName)}"]`
    );
    if (!portEl) return null;
    const dot = portEl.querySelector(".port-dot") || portEl;
    const worldRect = els.canvasWorld.getBoundingClientRect();
    const dotRect = dot.getBoundingClientRect();
    return {
      x: (dotRect.left - worldRect.left + dotRect.width / 2) / state.zoom,
      y: (dotRect.top - worldRect.top + dotRect.height / 2) / state.zoom,
    };
  }

  function connectionKind(conn) {
    const srcComp = getComp(conn.from.component);
    const srcSpec = srcComp ? getSpec(srcComp.type) : null;
    const p = srcSpec && srcSpec.ports ? srcSpec.ports[conn.from.port] : null;
    return p ? p.kind : "classical";
  }

  function clearFlow() {
    window.clearTimeout(state.flowTimeout);
    state.flowTimeout = null;
    const hadFlow = state.flow !== null;
    state.flow = null;
    els.btnReplay.hidden = true;
    els.edgeLayer.classList.remove("replaying");
    if (hadFlow && state.doc) renderEdges();
  }

  function invalidateFlow() {
    state.graphRevision += 1;
    clearFlow();
  }

  function getWireActivity(index) {
    return state.flow?.get(index);
  }

  function showRunFlow(result, replayCurrentGraph) {
    if (!Array.isArray(result.wire_activity)) return;
    const active = result.wire_activity.filter((wire) => wire.delivered > 0);
    const card = document.createElement("div");
    card.className = "result-card";
    const heading = document.createElement("h3");
    heading.textContent = "Qubit flow";
    const description = document.createElement("p");
    description.className = "muted flow-description";
    if (active.length) {
      const total = active.reduce((sum, wire) => sum + wire.delivered, 0);
      description.textContent = `${total.toLocaleString()} qubit deliveries across ${active.length} ${active.length === 1 ? "wire" : "wires"}.`;
      if (!replayCurrentGraph) description.textContent += " Run the edited graph to replay its flow.";
    } else {
      description.textContent = "No qubits reached the far end of a wire during this run.";
    }
    card.append(heading, description);
    els.resultsBody.prepend(card);

    if (!active.length || !replayCurrentGraph) return;
    state.flow = new Map(active.map((wire) => [wire.connection, wire]));
    els.btnReplay.hidden = false;
    renderEdges();
    replayFlow();
  }

  function replayFlow() {
    if (!state.flow?.size) return;
    window.clearTimeout(state.flowTimeout);
    els.edgeLayer.querySelectorAll(".flow-pulse").forEach((pulse) => pulse.remove());
    els.edgeLayer.classList.add("replaying");

    if (!REDUCED_MOTION.matches) {
      const wires = [...state.flow.values()]
        .sort((a, b) => a.first_delivery_tick - b.first_delivery_tick)
        .slice(0, MAX_FLOW_PULSES);
      const first = wires[0].first_delivery_tick;
      const span = Math.max(1, wires.at(-1).first_delivery_tick - first);
      const svgNS = "http://www.w3.org/2000/svg";
      for (const wire of wires) {
        const edge = els.edgeLayer.querySelector(`[data-wire="${wire.connection}"]`);
        if (!edge) continue;
        const pulse = document.createElementNS(svgNS, "circle");
        pulse.setAttribute("class", "flow-pulse");
        pulse.setAttribute("r", "5");
        pulse.setAttribute("aria-hidden", "true");
        const motion = document.createElementNS(svgNS, "animateMotion");
        motion.setAttribute("path", edge.getAttribute("d"));
        motion.setAttribute("dur", "0.68s");
        motion.setAttribute("begin", "indefinite");
        const visibility = document.createElementNS(svgNS, "set");
        visibility.setAttribute("attributeName", "visibility");
        visibility.setAttribute("to", "visible");
        visibility.setAttribute("dur", "0.68s");
        visibility.setAttribute("begin", "indefinite");
        pulse.append(motion, visibility);
        els.edgeLayer.appendChild(pulse);
        const offset = ((wire.first_delivery_tick - first) / span) * 0.65;
        motion.beginElementAt?.(offset);
        visibility.beginElementAt?.(offset);
      }
    }
    state.flowTimeout = window.setTimeout(() => {
      els.edgeLayer.classList.remove("replaying");
      els.edgeLayer.querySelectorAll(".flow-pulse").forEach((pulse) => pulse.remove());
    }, 1500);
  }

  function renderEdges() {
    els.edgeLayer.innerHTML = "";
    const svgNS = "http://www.w3.org/2000/svg";

    state.doc.connections.forEach((conn, idx) => {
      const p1 = getPortCenter(conn.from.component, conn.from.port);
      const p2 = getPortCenter(conn.to.component, conn.to.port);
      if (!p1 || !p2) return;

      const kind = connectionKind(conn);
      const dx = Math.max(40, Math.abs(p2.x - p1.x) * 0.45);
      const c1x = p1.x + dx;
      const c2x = p2.x - dx;
      const d = `M ${p1.x} ${p1.y} C ${c1x} ${p1.y}, ${c2x} ${p2.y}, ${p2.x} ${p2.y}`;

      const hit = document.createElementNS(svgNS, "path");
      hit.setAttribute("d", d);
      hit.setAttribute("class", "edge-hit");
      hit.addEventListener("click", (e) => {
        e.stopPropagation();
        state.selected = { type: "connection", index: idx };
        renderSelectionAndInspector();
      });

      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", d);
      path.dataset.wire = idx;
      const isSelected = state.selected && state.selected.type === "connection" && state.selected.index === idx;
      const srcComp = getComp(conn.from.component);
      const dstComp = getComp(conn.to.component);
      const srcPSpec = srcComp ? getSpec(srcComp.type)?.ports?.[conn.from.port] : null;
      const dstPSpec = dstComp ? getSpec(dstComp.type)?.ports?.[conn.to.port] : null;
      const isInactiveEdge =
        (srcComp && srcPSpec && !isPortActive(srcComp, srcPSpec)) ||
        (dstComp && dstPSpec && !isPortActive(dstComp, dstPSpec));
      path.setAttribute(
        "class",
        `edge-path ${kind}${isSelected ? " selected" : ""}${isInactiveEdge ? " invalid" : ""}`
      );

      els.edgeLayer.appendChild(hit);
      els.edgeLayer.appendChild(path);

      const activity = getWireActivity(idx);
      if (activity) {
        const title = document.createElementNS(svgNS, "title");
        title.textContent = `${activity.delivered} qubit deliveries · first at tick ${activity.first_delivery_tick}`;
        hit.appendChild(title);
        path.classList.add("has-flow");
      }

      // Show delay / noise badge if non-zero or selected
      const parts = [];
      if (conn.delay) parts.push(`d=${conn.delay}`);
      if (conn.loss_p) parts.push(`L=${conn.loss_p}`);
      if (conn.depolarization_p) parts.push(`p=${conn.depolarization_p}`);
      if (conn.length_km) parts.push(`${conn.length_km} km`);
      if (parts.length || isSelected) {
        const mx = (p1.x + p2.x) / 2;
        const my = (p1.y + p2.y) / 2;
        const text = parts.length ? parts.join(" ") : "d=0";
        const w = Math.max(30, text.length * 6.5 + 8);
        const rect = document.createElementNS(svgNS, "rect");
        rect.setAttribute("x", mx - w / 2);
        rect.setAttribute("y", my - 8);
        rect.setAttribute("width", w);
        rect.setAttribute("height", 16);
        rect.setAttribute("class", "edge-label-bg");
        const label = document.createElementNS(svgNS, "text");
        label.setAttribute("x", mx);
        label.setAttribute("y", my);
        label.setAttribute("class", "edge-label");
        label.textContent = text;
        els.edgeLayer.appendChild(rect);
        els.edgeLayer.appendChild(label);
      }
    });
  }

  function handlePortClick(compId, portName, pspec) {
    const comp = getComp(compId);
    if (!state.wiring) {
      if (pspec.direction !== "out") {
        showInputError("Start from an output port on the right side of a module.");
        return;
      }
      if (!isPortActive(comp, pspec)) {
        showInputError(`${compId}.${portName} is inactive under current parameters`);
        return;
      }
      if (pspec.max_connections != null && portConnectionCount(compId, portName, "out") >= pspec.max_connections) {
        showInputError(`${compId}.${portName} already has its maximum (${pspec.max_connections}) connection`);
        return;
      }
      state.wiring = { component: compId, port: portName, kind: pspec.kind };
      const msgLabel = pspec.message_type ? ` (${pspec.message_type})` : ` (${pspec.kind})`;
      els.wiringText.textContent = `Wiring ${compId}.${portName}${msgLabel} -> click a compatible input port`;
      els.wiringBanner.hidden = false;
      renderNodes();
      focusPort(compId, portName);
      return;
    }

    if (pspec.direction === "in") {
      const verdict = checkWireAllowed(state.wiring.component, state.wiring.port, compId, portName);
      if (!verdict.ok) {
        showInputError(verdict.reason);
        return;
      }
      const newConn = {
        from: { component: state.wiring.component, port: state.wiring.port },
        to: { component: compId, port: portName },
        delay: 0,
      };
      dismissCanvasMessage();
      invalidateFlow();
      state.doc.connections.push(newConn);
      state.selected = { type: "connection", index: state.doc.connections.length - 1 };
      state.wiring = null;
      els.wiringBanner.hidden = true;
      setStatus("neutral", "Ready");
      renderAll();
      return;
    }

    // Clicked another output port -> switch source if allowed
    if (!isPortActive(comp, pspec)) {
      showInputError(`${compId}.${portName} is inactive under current parameters`);
      return;
    }
    if (pspec.max_connections != null && portConnectionCount(compId, portName, "out") >= pspec.max_connections) {
      showInputError(`${compId}.${portName} already has its maximum (${pspec.max_connections}) connection`);
      return;
    }
    state.wiring = { component: compId, port: portName, kind: pspec.kind };
    const msgLabel = pspec.message_type ? ` (${pspec.message_type})` : ` (${pspec.kind})`;
    els.wiringText.textContent = `Wiring ${compId}.${portName}${msgLabel} -> click a compatible input port`;
    renderNodes();
    focusPort(compId, portName);
  }

  function focusPort(compId, portName) {
    els.nodeLayer.querySelector(
      `.port[data-comp-id="${CSS.escape(compId)}"][data-port="${CSS.escape(portName)}"]`
    )?.focus({ preventScroll: true });
  }

  function cancelWiring() {
    if (!state.wiring) return;
    state.wiring = null;
    els.wiringBanner.hidden = true;
    renderNodes();
  }

  function renameComponent(oldId, newId) {
    const trimmed = newId.trim();
    if (!trimmed || trimmed === oldId) return false;
    if (state.doc.components.some((c) => c.id === trimmed)) {
      showInputError(`A module already uses the ID "${trimmed}".`);
      return false;
    }
    const comp = getComp(oldId);
    if (!comp) return false;
    dismissCanvasMessage();
    invalidateFlow();
    comp.id = trimmed;
    for (const conn of state.doc.connections) {
      if (conn.from.component === oldId) conn.from.component = trimmed;
      if (conn.to.component === oldId) conn.to.component = trimmed;
    }
    for (const m of state.doc.measurements) {
      if (Array.isArray(m.probes)) {
        m.probes = m.probes.map((pid) => (pid === oldId ? trimmed : pid));
      }
    }
    state.selected = { type: "component", id: trimmed };
    renderAll();
    return true;
  }

  function focusComponent(compId) {
    els.nodeLayer.querySelector(`.node[data-comp-id="${CSS.escape(compId)}"]`)?.focus();
  }

  function dismissCanvasMessage() {
    state.undoRemoval = null;
    els.canvasMessage.hidden = true;
    els.btnUndo.hidden = true;
  }

  function showCanvasMessage(message, undo = null) {
    state.undoRemoval = undo;
    els.canvasMessage.dataset.kind = undo ? "removed" : "input-error";
    els.canvasMessageText.textContent = message;
    els.btnUndo.hidden = !undo;
    els.canvasMessage.hidden = false;
  }

  function showInputError(message) {
    showCanvasMessage(`That's not it boss. ${message}`);
  }

  function deleteSelection() {
    if (state.selected?.type === "component") deleteComponent(state.selected.id);
    if (state.selected?.type === "connection") deleteConnection(state.selected.index);
  }

  function deleteComponent(compId) {
    const comp = getComp(compId);
    if (!comp) return;
    const previous = {
      components: state.doc.components,
      connections: state.doc.connections,
      measurements: state.doc.measurements,
    };
    state.doc.components = previous.components.filter((c) => c !== comp);
    state.doc.connections = previous.connections.filter(
      (conn) => conn.from.component !== compId && conn.to.component !== compId
    );
    state.doc.measurements = previous.measurements.filter(
      (m) => !Array.isArray(m.probes) || !m.probes.includes(compId)
    );
    const wireCount = previous.connections.length - state.doc.connections.length;
    finishRemoval(wireCount ? `Removed ${compId} and ${wireCount} connected ${wireCount === 1 ? "wire" : "wires"}.` : `Removed ${compId}.`, () => {
      Object.assign(state.doc, previous);
      state.selected = { type: "component", id: compId };
    });
  }

  function deleteConnection(index) {
    if (!state.doc.connections[index]) return;
    const previous = state.doc.connections;
    state.doc.connections = previous.filter((_, i) => i !== index);
    finishRemoval("Removed wire.", () => {
      state.doc.connections = previous;
      state.selected = { type: "connection", index };
    });
  }

  function finishRemoval(message, undo) {
    invalidateFlow();
    state.wiring = null;
    state.selected = null;
    els.wiringBanner.hidden = true;
    renderAll();
    showCanvasMessage(message, undo);
    els.btnUndo.focus();
  }

  function undoRemoval() {
    if (!state.undoRemoval) return;
    invalidateFlow();
    state.undoRemoval();
    dismissCanvasMessage();
    renderAll();
    if (state.selected?.type === "component") focusComponent(state.selected.id);
    else els.canvasViewport.focus();
  }

  function renderInspector() {
    els.inspectorBody.innerHTML = "";

    if (state.selected && state.selected.type === "component") {
      const comp = getComp(state.selected.id);
      if (!comp) {
        state.selected = null;
        renderInspector();
        return;
      }
      const spec = getSpec(comp.type);
      els.inspectorTitle.textContent = spec ? spec.label : comp.type;
      els.btnSelectExp.hidden = false;

      if (spec && spec.model) {
        const modelEl = document.createElement("div");
        modelEl.className = "model-note";
        modelEl.textContent = spec.model;
        els.inspectorBody.appendChild(modelEl);
      }

      // Component ID field
      const idField = document.createElement("div");
      idField.className = "field";
      idField.innerHTML = `<label for="insp-comp-id">Component ID</label>`;
      const idInput = document.createElement("input");
      idInput.id = "insp-comp-id";
      idInput.type = "text";
      idInput.value = comp.id;
      idInput.addEventListener("change", () => {
        if (!renameComponent(comp.id, idInput.value)) {
          idInput.value = comp.id;
        }
      });
      idField.appendChild(idInput);
      els.inspectorBody.appendChild(idField);

      // Parameters from manifest (hide inactive/reserved controls marked ui_hidden)
      const paramsSpec = spec ? spec.parameters || {} : {};
      for (const [pname, pspec] of Object.entries(paramsSpec)) {
        if (pspec.ui_hidden) continue;
        const field = document.createElement("div");
        field.className = "field";
        const inputId = `param-${pname}`;
        const label = document.createElement("label");
        label.htmlFor = inputId;
        const baseLabel = pspec.label || pname;
        label.textContent = pspec.unit ? `${baseLabel} (${pspec.unit})` : baseLabel;
        field.appendChild(label);

        const currentVal = comp.params[pname] !== undefined ? comp.params[pname] : pspec.default;
        let control;
        if (Array.isArray(pspec.enum)) {
          control = document.createElement("select");
          control.id = inputId;
          for (const optVal of pspec.enum) {
            const opt = document.createElement("option");
            opt.value = String(optVal);
            const enumLabel = pspec.enum_labels && pspec.enum_labels[String(optVal)];
            opt.textContent = enumLabel || String(optVal);
            if (optVal === currentVal) opt.selected = true;
            control.appendChild(opt);
          }
          control.addEventListener("change", () => {
            comp.params[pname] = pspec.type === "integer" ? parseInt(control.value, 10) : Number(control.value);
            renderNodes();
            renderEdges();
          });
        } else {
          control = document.createElement("input");
          control.id = inputId;
          control.type = "number";
          control.step = pspec.type === "integer" ? "1" : "any";
          if (pspec.min !== undefined) control.min = String(pspec.min);
          if (pspec.max !== undefined) control.max = String(pspec.max);
          control.value = String(currentVal);
          control.addEventListener("input", () => {
            if (control.value === "") return;
            const parsed = pspec.type === "integer" ? parseInt(control.value, 10) : Number(control.value);
            if (!Number.isNaN(parsed)) {
              comp.params[pname] = parsed;
              renderNodes();
            }
          });
        }
        field.appendChild(control);

        if (pspec.description) {
          const help = document.createElement("div");
          help.className = "field-help";
          help.textContent = pspec.description;
          field.appendChild(help);
        }
        els.inspectorBody.appendChild(field);
      }

      const delBtn = document.createElement("button");
      delBtn.className = "btn btn-danger";
      delBtn.type = "button";
      delBtn.textContent = "Delete Component";
      delBtn.addEventListener("click", () => deleteComponent(comp.id));
      els.inspectorBody.appendChild(delBtn);
      return;
    }

    if (state.selected && state.selected.type === "connection") {
      const idx = state.selected.index;
      const conn = state.doc.connections[idx];
      if (!conn) {
        state.selected = null;
        renderInspector();
        return;
      }
      const kind = connectionKind(conn);
      const chSpec = state.manifest && state.manifest.channels ? state.manifest.channels[kind] : null;
      const chLabel = chSpec ? chSpec.label : (kind === "quantum" ? "Quantum Channel" : "Classical Channel");
      els.inspectorTitle.textContent = chLabel;
      els.btnSelectExp.hidden = false;

      const info = document.createElement("div");
      info.innerHTML = `
        <span class="kind-badge ${kind}">${escapeHtml(chLabel)}</span>
        <div class="field"><label>Route</label><div class="muted">${escapeHtml(conn.from.component)}.${escapeHtml(conn.from.port)} &rarr; ${escapeHtml(conn.to.component)}.${escapeHtml(conn.to.port)}</div></div>
      `;
      els.inspectorBody.appendChild(info);

      const chParams = chSpec ? chSpec.parameters || {} : {};
      const delaySpec = chParams.delay || {};
      addNumericConnField(
        conn,
        "delay",
        `${delaySpec.label || "Propagation delay"} (${delaySpec.unit || "simulation ticks"})`,
        0,
        undefined,
        delaySpec.description
      );
      if (kind === "quantum") {
        const lossSpec = chParams.loss_p || {};
        const depolSpec = chParams.depolarization_p || {};
        addNumericConnField(
          conn,
          "loss_p",
          `${lossSpec.label || "Qubit loss probability per transmission"} (${lossSpec.unit || "[0, 1]"})`,
          0,
          1,
          lossSpec.description
        );
        addNumericConnField(
          conn,
          "depolarization_p",
          `${depolSpec.label || "Pauli error probability per transmission"} (${depolSpec.unit || "[0, 1]"})`,
          0,
          1,
          depolSpec.description
        );
        const lengthSpec = chParams.length_km || {};
        const attSpec = chParams.attenuation_db_per_km || {};
        const couplingSpec = chParams.coupling_loss_db || {};
        addNumericConnField(
          conn,
          "length_km",
          `${lengthSpec.label || "Fibre length"} (${lengthSpec.unit || "km"})`,
          0,
          undefined,
          lengthSpec.description
        );
        addNumericConnField(
          conn,
          "attenuation_db_per_km",
          `${attSpec.label || "Fibre attenuation"} (${attSpec.unit || "dB/km"})`,
          0,
          undefined,
          attSpec.description,
          { fallback: 0.2, keepZero: true }
        );
        addNumericConnField(
          conn,
          "coupling_loss_db",
          `${couplingSpec.label || "Coupling loss"} (${couplingSpec.unit || "dB"})`,
          0,
          undefined,
          couplingSpec.description
        );
      }

      const delBtn = document.createElement("button");
      delBtn.className = "btn btn-danger";
      delBtn.type = "button";
      delBtn.textContent = "Delete Connection";
      delBtn.addEventListener("click", () => deleteConnection(idx));
      els.inspectorBody.appendChild(delBtn);
      return;
    }

    // Default: Experiment inspector
    els.inspectorTitle.textContent = "Experiment";
    els.btnSelectExp.hidden = true;

    const nameField = document.createElement("div");
    nameField.className = "field";
    nameField.innerHTML = `<label for="exp-name">Name</label>`;
    const nameInput = document.createElement("input");
    nameInput.id = "exp-name";
    nameInput.type = "text";
    nameInput.value = state.doc.name || "";
    nameInput.addEventListener("input", () => {
      state.doc.name = nameInput.value;
    });
    nameField.appendChild(nameInput);
    els.inspectorBody.appendChild(nameField);

    const descField = document.createElement("div");
    descField.className = "field";
    descField.innerHTML = `<label for="exp-desc">Description</label>`;
    const descInput = document.createElement("input");
    descInput.id = "exp-desc";
    descInput.type = "text";
    descInput.value = state.doc.description || "";
    descInput.addEventListener("input", () => {
      state.doc.description = descInput.value;
    });
    descField.appendChild(descInput);
    els.inspectorBody.appendChild(descField);

    // Measurements list
    const probes = state.doc.components.filter((c) => c.type === "endpoint_probe").map((c) => c.id);
    const measField = document.createElement("div");
    measField.className = "field";
    measField.innerHTML = `<div class="field-row"><label>Bell Fidelity Measurements</label></div>`;

    state.doc.measurements.forEach((m, mIdx) => {
      if (m.type !== "bell_fidelity") return;
      const row = document.createElement("div");
      row.className = "meas-row";
      [0, 1].forEach((slot) => {
        const sel = document.createElement("select");
        for (const pid of probes) {
          const opt = document.createElement("option");
          opt.value = pid;
          opt.textContent = pid;
          if (m.probes[slot] === pid) opt.selected = true;
          sel.appendChild(opt);
        }
        sel.addEventListener("change", () => {
          m.probes[slot] = sel.value;
        });
        row.appendChild(sel);
      });
      const rm = document.createElement("button");
      rm.className = "btn btn-xs btn-danger";
      rm.type = "button";
      rm.textContent = "×";
      rm.addEventListener("click", () => {
        dismissCanvasMessage();
        state.doc.measurements.splice(mIdx, 1);
        renderInspector();
      });
      row.appendChild(rm);
      measField.appendChild(row);
    });

    if (probes.length >= 2) {
      const addM = document.createElement("button");
      addM.className = "btn btn-xs";
      addM.type = "button";
      addM.textContent = "+ Add Bell Fidelity";
      addM.addEventListener("click", () => {
        dismissCanvasMessage();
        state.doc.measurements.push({ type: "bell_fidelity", probes: [probes[0], probes[1]] });
        renderInspector();
      });
      measField.appendChild(addM);
    } else {
      const note = document.createElement("div");
      note.className = "field-help";
      note.textContent = "Add at least two endpoint_probe nodes to measure Bell fidelity.";
      measField.appendChild(note);
    }

    els.inspectorBody.appendChild(measField);
  }

  function addNumericConnField(conn, key, labelText, min, max, description = "", options = {}) {
    const field = document.createElement("div");
    field.className = "field";
    const id = `conn-${key}`;
    field.innerHTML = `<label for="${id}">${escapeHtml(labelText)}</label>`;
    const input = document.createElement("input");
    input.id = id;
    input.type = "number";
    input.step = "any";
    if (min !== undefined) input.min = String(min);
    if (max !== undefined) input.max = String(max);
    // `fallback` is the backend default shown when the key is absent; `keepZero` keeps an
    // explicit 0 in the document (needed when the default is non-zero).
    const fallback = options.fallback !== undefined ? options.fallback : 0;
    input.value = String(conn[key] ?? fallback);
    input.addEventListener("input", () => {
      if (input.value === "") return;
      const val = Number(input.value);
      if (!Number.isNaN(val)) {
        if (key !== "delay" && val === 0 && !options.keepZero) {
          delete conn[key];
        } else {
          conn[key] = val;
        }
        renderEdges();
      }
    });
    field.appendChild(input);
    if (description) {
      const help = document.createElement("div");
      help.className = "field-help";
      help.textContent = description;
      field.appendChild(help);
    }
    els.inspectorBody.appendChild(field);
  }

  function renderSelectionAndInspector() {
    els.nodeLayer.querySelectorAll(".node").forEach((el) => {
      const isSel =
        state.selected && state.selected.type === "component" && state.selected.id === el.dataset.compId;
      el.classList.toggle("selected", Boolean(isSel));
    });
    renderEdges();
    renderInspector();
  }

  function renderAll() {
    renderNodes();
    resizeWorld();
    renderEdges();
    renderInspector();
  }

  function renderErrors(errors, system = false) {
    setStatus("err", system ? "Run unavailable" : "Needs attention");
    const heading = document.createElement("h3");
    heading.className = "error-title";
    heading.textContent = system ? "We are not that good yet." : "That's not it boss.";
    const card = document.createElement("div");
    card.className = `error-card ${system ? "system-error" : "input-error"}`;
    card.setAttribute("role", "alert");
    const ul = document.createElement("ul");
    ul.className = "error-list";
    for (const msg of errors) {
      const li = document.createElement("li");
      li.textContent = msg;
      ul.appendChild(li);
    }
    els.resultsBody.innerHTML = "";
    card.append(heading, ul);
    els.resultsBody.appendChild(card);
  }

  function renderRunResult(result, replayCurrentGraph) {
    state.lastResult = result;
    setStatus("ok", "Completed");
    const frag = document.createDocumentFragment();

    const meta = document.createElement("div");
    meta.className = "result-card";
    meta.innerHTML = `
      <h3>Run Summary</h3>
      <div class="metric-row"><span>Simulator</span><span>v${escapeHtml(result.simulator_version)}</span></div>
      <div class="metric-row"><span>Final time</span><span>${result.final_time}</span></div>
      <div class="metric-row"><span>Seed</span><span>${result.seed === null ? "auto" : result.seed}</span></div>
    `;
    frag.appendChild(meta);

    for (const m of result.measurements || []) {
      if (m.type === "bell_fidelity") {
        const card = document.createElement("div");
        card.className = "result-card";
        const fStr = m.mean_fidelity === null ? "—" : String(m.mean_fidelity);
        const latRow =
          m.mean_latency != null
            ? `<div class="metric-row"><span>Mean delivery latency</span><span>${m.mean_latency} ticks</span></div>`
            : "";
        const unmRow =
          (m.unmatched_a || m.unmatched_b)
            ? `<div class="metric-row"><span>Unmatched arrivals (A / B)</span><span>${m.unmatched_a} / ${m.unmatched_b}</span></div>`
            : "";
        card.innerHTML = `
          <h3>Conditional mean fidelity to |&Phi;<sup>+</sup>&rang; (at delivery)</h3>
          <div class="field-help">${escapeHtml(m.probes[0])} &harr; ${escapeHtml(m.probes[1])} (matched by pair ID)</div>
          <div class="metric-big" data-testid="mean-fidelity">${escapeHtml(fStr)}</div>
          <div class="metric-row"><span>End-to-end pairs delivered</span><span>${m.pairs}</span></div>
          ${latRow}
          ${unmRow}
          <div class="metric-row diagnostic-row"><span>Diagnostic: shared register</span><span>${m.all_shared_register}</span></div>
        `;
        frag.appendChild(card);
      }
    }

    const coincMap = (result.metrics && result.metrics.readers_coincidences) || {};
    for (const [rid, counts] of Object.entries(result.readers || {})) {
      const card = document.createElement("div");
      card.className = "result-card";
      const c = coincMap[rid];
      const coincRows =
        c && (c.accidental_coincidences || c.dark_clicks_1 || c.dark_clicks_2)
          ? `
        <div class="metric-row"><span>Coincidences (|&Delta;t| &le; ${c.window})</span><span>${c.total} (true ${c.true_pair_coincidences} / acc. ${c.accidental_coincidences})</span></div>
        <div class="metric-row"><span>Dark clicks (in 1 / in 2)</span><span>${c.dark_clicks_1} / ${c.dark_clicks_2}</span></div>
      `
          : "";
      card.innerHTML = `
        <h3>Joint Outcome Counter: ${escapeHtml(rid)}</h3>
        <div class="field-help">Matched by pair ID (excludes untagged / dark clicks)</div>
        <div class="metric-row"><span>00 / 11</span><span>${counts["00"]} / ${counts["11"]}</span></div>
        <div class="metric-row"><span>01 / 10</span><span>${counts["01"]} / ${counts["10"]}</span></div>
        ${coincRows}
      `;
      frag.appendChild(card);
    }

    for (const [did, d] of Object.entries(result.detectors || {})) {
      const card = document.createElement("div");
      card.className = "result-card";
      card.innerHTML = `
        <h3>Qubit Arrival Monitor: ${escapeHtml(did)}</h3>
        <div class="metric-row"><span>Arrivals in two-qubit registers (1 / 2)</span><span>${d.ebits_1} / ${d.ebits_2}</span></div>
        <div class="metric-row"><span>Single-qubit arrivals (1 / 2)</span><span>${d.single_1} / ${d.single_2}</span></div>
        <div class="metric-row"><span>Total arrivals (1 / 2)</span><span>${d.total_1} / ${d.total_2}</span></div>
      `;
      frag.appendChild(card);
    }

    const raw = document.createElement("details");
    raw.className = "raw-json";
    raw.innerHTML = `<summary>Raw JSON output</summary><pre>${escapeHtml(JSON.stringify(result, null, 2))}</pre>`;
    frag.appendChild(raw);

    els.resultsBody.innerHTML = "";
    els.resultsBody.appendChild(frag);
    showRunFlow(result, replayCurrentGraph);

  }

  async function validateCurrent() {
    if (!state.doc) return false;
    const current = state.doc;
    try {
      const data = await requestExperiment("/api/validate", buildExportDocument());
      if (state.doc !== current) return false;
      if (!data.ok) {
        renderErrors(data.errors);
        return false;
      }
      setStatus("ok", `Valid (schema ${data.schema_version})`);
      els.resultsBody.innerHTML = `<p class="muted">Experiment graph passed static validation (schema ${escapeHtml(data.schema_version)}).</p>`;
      return true;
    } catch (error) {
      if (state.doc === current) renderErrors([error.message], true);
      return false;
    }
  }

  async function requestExperiment(path, doc) {
    const headers = { "Content-Type": "application/json" };
    if (path === "/api/run") headers["X-DAMN-Q-Flow"] = "1";
    const resp = await fetch(path, {
      method: "POST",
      headers,
      body: JSON.stringify(doc),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      const errors = data.errors || [data.error || "The request could not be completed."];
      if (resp.status >= 500) throw new Error(errors.join(" "));
      return { ok: false, errors };
    }
    return data;
  }

  async function runCurrent() {
    if (!state.doc || state.pendingRun) return null;
    const current = state.doc;
    const doc = buildExportDocument();
    const revision = state.graphRevision;
    state.pendingRun = true;
    els.btnRun.disabled = true;
    els.btnValidate.disabled = true;
    clearFlow();
    setStatus("neutral", "Running…");
    try {
      const data = await requestExperiment("/api/run", doc);
      if (state.doc !== current) return null;
      if (!data.ok) {
        renderErrors(data.errors);
        return null;
      }
      renderRunResult(data.result, revision === state.graphRevision);
      return data.result;
    } catch (error) {
      if (state.doc === current) renderErrors([error.message], true);
      return null;
    } finally {
      state.pendingRun = false;
      els.btnRun.disabled = false;
      els.btnValidate.disabled = false;
    }
  }

  function exportCurrent() {
    const doc = buildExportDocument();
    const jsonText = JSON.stringify(doc, null, 2) + "\n";
    const slug = (doc.name || "experiment")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") || "experiment";
    const blob = new Blob([jsonText], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return jsonText;
  }

  function graphBounds() {
    const boxes = [...els.nodeLayer.children].map((node) => ({
      x: node.offsetLeft,
      y: node.offsetTop,
      right: node.offsetLeft + node.offsetWidth,
      bottom: node.offsetTop + node.offsetHeight,
    }));
    if (!boxes.length) return null;
    return {
      x: Math.min(...boxes.map((b) => b.x)),
      y: Math.min(...boxes.map((b) => b.y)),
      right: Math.max(...boxes.map((b) => b.right)),
      bottom: Math.max(...boxes.map((b) => b.bottom)),
    };
  }

  function resizeWorld() {
    const bounds = graphBounds();
    els.canvasWorld.style.width = `${Math.max(els.canvasViewport.clientWidth / state.zoom, (bounds?.right ?? 0) + 44)}px`;
    els.canvasWorld.style.height = `${Math.max(els.canvasViewport.clientHeight / state.zoom, (bounds?.bottom ?? 0) + 44)}px`;
  }

  function setZoom(value) {
    state.zoom = Math.min(1.5, Math.max(0.25, value));
    els.canvasWorld.style.zoom = String(state.zoom);
    els.zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
    resizeWorld();
    renderEdges();
  }

  function fitView(minZoom = 0.25) {
    const bounds = graphBounds();
    if (!bounds) return;
    setZoom(Math.max(minZoom, Math.min(
      1,
      (els.canvasViewport.clientWidth - 42) / (bounds.right - bounds.x),
      (els.canvasViewport.clientHeight - 44) / (bounds.bottom - bounds.y)
    )));
    els.canvasViewport.scrollTo(
      Math.max(0, bounds.x * state.zoom - 20),
      Math.max(0, bounds.y * state.zoom - 20)
    );
  }

  async function loadExample(filename) {
    try {
      const resp = await fetch(`/api/examples/${encodeURIComponent(filename)}`);
      if (!resp.ok) throw new Error("Could not load this example. Try again.");
      setExperiment(await resp.json());
      fitView(0.72);
    } catch (error) {
      renderErrors([error.message], true);
    }
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function bindEvents() {
    els.btnLoadExample.addEventListener("click", () => {
      if (els.exampleSelect.value) loadExample(els.exampleSelect.value);
    });
    els.exampleSelect.addEventListener("change", () => {
      if (els.exampleSelect.value) loadExample(els.exampleSelect.value);
    });

    els.btnImport.addEventListener("click", () => els.fileImport.click());
    els.fileImport.addEventListener("change", async () => {
      const file = els.fileImport.files && els.fileImport.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const imported = JSON.parse(text);
        if (!imported || !Array.isArray(imported.components)
            || imported.components.some((component) => !component || typeof component !== "object")
            || (Array.isArray(imported.connections) && imported.connections.some((conn) => !conn?.from || !conn?.to))) {
          renderErrors(["Choose a DAMN-Q experiment with components and valid connection endpoints."]);
          return;
        }
        setExperiment(imported);
        fitView();
        // Validate immediately so unknown components or schema problems are reported at import time
        await validateCurrent();
      } catch (err) {
        renderErrors([`Could not parse JSON file: ${err.message}`]);
      } finally {
        els.fileImport.value = "";
      }
    });

    els.btnExport.addEventListener("click", () => exportCurrent());
    els.btnValidate.addEventListener("click", () => validateCurrent());
    els.btnRun.addEventListener("click", () => runCurrent());
    els.btnFit.addEventListener("click", () => fitView());
    els.btnReplay.addEventListener("click", replayFlow);
    for (const element of [els.runUntil, els.runSeed, els.inspectorBody]) {
      element.addEventListener("input", invalidateFlow, true);
    }
    els.zoomIn.addEventListener("click", () => setZoom(state.zoom * 1.2));
    els.zoomOut.addEventListener("click", () => setZoom(state.zoom / 1.2));
    els.btnUndo.addEventListener("click", undoRemoval);
    els.btnDismiss.addEventListener("click", () => {
      dismissCanvasMessage();
      els.canvasViewport.focus();
    });
    window.addEventListener("resize", () => {
      if (state.doc) resizeWorld();
    });
    els.btnCancelWire.addEventListener("click", () => cancelWiring());
    els.btnSelectExp.addEventListener("click", () => {
      state.selected = null;
      renderSelectionAndInspector();
    });

    els.runUntil.addEventListener("input", () => {
      if (!state.doc) return;
      const val = Number(els.runUntil.value);
      if (!Number.isNaN(val)) state.doc.run.until = val;
    });

    els.runSeed.addEventListener("input", () => {
      if (!state.doc) return;
      if (els.runSeed.value === "") {
        state.doc.run.seed = null;
      } else {
        const val = parseInt(els.runSeed.value, 10);
        if (!Number.isNaN(val)) state.doc.run.seed = val;
      }
    });

    els.canvasViewport.addEventListener("mousedown", (e) => {
      if (e.target === els.canvasViewport || e.target === els.canvasWorld || e.target === els.edgeLayer) {
        if (state.wiring) cancelWiring();
        state.selected = null;
        renderSelectionAndInspector();
      }
    });

    els.canvasWorld.addEventListener("dragover", (e) => e.preventDefault());
    els.canvasWorld.addEventListener("drop", (e) => {
      e.preventDefault();
      const ctype = e.dataTransfer.getData("text/plain");
      if (!ctype || !getSpec(ctype)) return;
      const rect = els.canvasWorld.getBoundingClientRect();
      addComponent(ctype, { x: (e.clientX - rect.left) / state.zoom, y: (e.clientY - rect.top) / state.zoom });
    });

    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") cancelWiring();
      if (e.target.closest?.("input, textarea, select, [contenteditable]:not([contenteditable=false])")) return;
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z" && state.undoRemoval) {
        e.preventDefault();
        undoRemoval();
        return;
      }
      if (!e.repeat && !e.altKey && !e.ctrlKey && !e.metaKey
          && (e.key === "Delete" || e.key === "Backspace") && state.selected && !state.wiring) {
        e.preventDefault();
        deleteSelection();
      }
    });
  }

  async function init() {
    bindEvents();
    const [manResp, exResp] = await Promise.all([
      fetch("/api/manifest"),
      fetch("/api/examples"),
    ]);
    if (!manResp.ok || !exResp.ok) throw new Error("The simulator could not load its components or experiments.");
    state.manifest = await manResp.json();
    const exData = await exResp.json();
    state.examples = exData.examples || [];

    els.versionBadge.textContent = `v${state.manifest.simulator_version}`;
    renderPalette();

    els.exampleSelect.innerHTML = "";
    for (const ex of state.examples) {
      const opt = document.createElement("option");
      opt.value = ex.filename;
      opt.textContent = `${ex.name} (${ex.filename})`;
      els.exampleSelect.appendChild(opt);
    }

    const defaultEx =
      state.examples.find((e) => e.filename === "repeater_ideal.json") || state.examples[0];
    if (defaultEx) {
      els.exampleSelect.value = defaultEx.filename;
      await loadExample(defaultEx.filename);
    }

    // Expose a clean handle for inspection and automated verification
    window.__DAMN_Q_APP__ = {
      getExperiment: () => buildExportDocument(),
      setExperiment,
      validate: validateCurrent,
      run: runCurrent,
      exportJson: () => JSON.stringify(buildExportDocument(), null, 2) + "\n",
      getLastResult: () => state.lastResult,
    };
  }

  init().catch((err) => {
    renderErrors([`Could not start the workbench. ${err.message}`], true);
  });
})();
