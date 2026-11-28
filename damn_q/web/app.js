(() => {
  "use strict";

  const POS_SCALE_X = 1.45;
  const POS_SCALE_Y = 1.65;
  const POS_OFFSET_X = 40;
  const POS_OFFSET_Y = 30;

  const state = {
    manifest: null,
    examples: [],
    doc: null,
    selected: null, // { type: "component", id } | { type: "connection", index } | null
    wiring: null,   // { component, port, kind } | null
    lastResult: null,
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
    state.doc = JSON.parse(JSON.stringify(doc));
    ensurePositions(state.doc);
    state.selected = null;
    state.wiring = null;
    state.lastResult = null;
    syncToolbarFromDoc();
    setStatus("neutral", "Ready");
    els.resultsBody.innerHTML =
      '<p class="muted">Click <strong>Validate</strong> or <strong>Run</strong> to execute this experiment through the DAMN-Q simulator.</p>';
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
        const item = document.createElement("div");
        item.className = "palette-item";
        item.draggable = true;
        item.dataset.ctype = ctype;
        item.innerHTML = `<span>${spec.label}</span><span class="palette-item-add">+</span>`;
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
  }

  function summarizeComponent(comp) {
    const p = comp.params || {};
    if (comp.type === "quantum_memory") {
      return `p=${p.depolarization_p ?? 0}/tick cap=${p.capacity ?? 100} ${p.fifo === 0 ? "LIFO" : "FIFO"}`;
    }
    if (comp.type === "source") {
      return `T=${p.delay ?? 1} ${p.type === 1 ? "|0>" : "|Phi+>"}`;
    }
    if (comp.type === "entanglement_swapper" || comp.type === "pauli_corrector") {
      return `out_delay=${p.delay ?? 0}`;
    }
    if (comp.type === "measurer" || comp.type === "measurer_memory_paired") {
      return `out_delay=${p.delay ?? 0} x_p=${p.x_basis_p ?? 0}`;
    }
    if (comp.type === "detector_module") {
      return `trace=${p.trace ?? 0}`;
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
      if (state.selected && state.selected.type === "component" && state.selected.id === comp.id) {
        node.classList.add("selected");
      }
      node.style.left = `${toCanvasX(comp.position.x)}px`;
      node.style.top = `${toCanvasY(comp.position.y)}px`;

      const header = document.createElement("div");
      header.className = "node-header";
      header.innerHTML = `<div class="node-id">${escapeHtml(comp.id)}</div><div class="node-type">${escapeHtml(spec ? spec.label : comp.type)}</div>`;
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
          const portEl = document.createElement("div");
          portEl.className = "port";
          portEl.dataset.compId = comp.id;
          portEl.dataset.port = pname;
          portEl.dataset.direction = pspec.direction;
          portEl.dataset.kind = pspec.kind;
          const active = isPortActive(comp, pspec);
          const portDisplay = pspec.label || pname;
          const msgTag = pspec.message_type ? `, ${pspec.message_type}` : "";
          portEl.title = `${comp.id}.${pname} — ${portDisplay} (${pspec.direction}, ${pspec.kind}${msgTag})${active ? "" : " [inactive]"}`;
          if (!active) portEl.classList.add("inactive");

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
        if (e.target.closest(".port")) return;
        e.stopPropagation();
        state.selected = { type: "component", id: comp.id };
        renderSelectionAndInspector();

        const startX = e.clientX;
        const startY = e.clientY;
        const origLeft = toCanvasX(comp.position.x);
        const origTop = toCanvasY(comp.position.y);

        function onMove(ev) {
          const nx = Math.max(0, origLeft + (ev.clientX - startX));
          const ny = Math.max(0, origTop + (ev.clientY - startY));
          node.style.left = `${nx}px`;
          node.style.top = `${ny}px`;
          comp.position.x = fromCanvasX(nx);
          comp.position.y = fromCanvasY(ny);
          renderEdges();
        }
        function onUp() {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
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
      x: dotRect.left - worldRect.left + dotRect.width / 2,
      y: dotRect.top - worldRect.top + dotRect.height / 2,
    };
  }

  function connectionKind(conn) {
    const srcComp = getComp(conn.from.component);
    const srcSpec = srcComp ? getSpec(srcComp.type) : null;
    const p = srcSpec && srcSpec.ports ? srcSpec.ports[conn.from.port] : null;
    return p ? p.kind : "classical";
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
        setStatus("neutral", "Start wiring from an output port (right side)");
        return;
      }
      if (!isPortActive(comp, pspec)) {
        setStatus("err", `${compId}.${portName} is inactive under current parameters`);
        return;
      }
      if (pspec.max_connections != null && portConnectionCount(compId, portName, "out") >= pspec.max_connections) {
        setStatus("err", `${compId}.${portName} already has its maximum (${pspec.max_connections}) connection`);
        return;
      }
      state.wiring = { component: compId, port: portName, kind: pspec.kind };
      const msgLabel = pspec.message_type ? ` (${pspec.message_type})` : ` (${pspec.kind})`;
      els.wiringText.textContent = `Wiring ${compId}.${portName}${msgLabel} -> click a compatible input port`;
      els.wiringBanner.hidden = false;
      renderNodes();
      return;
    }

    if (pspec.direction === "in") {
      const verdict = checkWireAllowed(state.wiring.component, state.wiring.port, compId, portName);
      if (!verdict.ok) {
        setStatus("err", verdict.reason);
        return;
      }
      const newConn = {
        from: { component: state.wiring.component, port: state.wiring.port },
        to: { component: compId, port: portName },
        delay: 0,
      };
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
      setStatus("err", `${compId}.${portName} is inactive under current parameters`);
      return;
    }
    if (pspec.max_connections != null && portConnectionCount(compId, portName, "out") >= pspec.max_connections) {
      setStatus("err", `${compId}.${portName} already has its maximum (${pspec.max_connections}) connection`);
      return;
    }
    state.wiring = { component: compId, port: portName, kind: pspec.kind };
    const msgLabel = pspec.message_type ? ` (${pspec.message_type})` : ` (${pspec.kind})`;
    els.wiringText.textContent = `Wiring ${compId}.${portName}${msgLabel} -> click a compatible input port`;
    renderNodes();
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
      setStatus("err", `Duplicate ID "${trimmed}"`);
      return false;
    }
    const comp = getComp(oldId);
    if (!comp) return false;
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

  function deleteComponent(compId) {
    state.doc.components = state.doc.components.filter((c) => c.id !== compId);
    state.doc.connections = state.doc.connections.filter(
      (conn) => conn.from.component !== compId && conn.to.component !== compId
    );
    state.doc.measurements = state.doc.measurements.filter(
      (m) => !Array.isArray(m.probes) || !m.probes.includes(compId)
    );
    state.selected = null;
    renderAll();
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
      delBtn.addEventListener("click", () => {
        state.doc.connections.splice(idx, 1);
        state.selected = null;
        renderAll();
      });
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
    renderEdges();
    renderInspector();
  }

  function renderErrors(errors) {
    setStatus("err", "Invalid");
    const ul = document.createElement("ul");
    ul.className = "error-list";
    for (const msg of errors) {
      const li = document.createElement("li");
      li.textContent = msg;
      ul.appendChild(li);
    }
    els.resultsBody.innerHTML = "";
    els.resultsBody.appendChild(ul);
  }

  function renderRunResult(result) {
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
  }

  async function validateCurrent() {
    const doc = buildExportDocument();
    const resp = await fetch("/api/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(doc),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      renderErrors(data.errors || [data.error || "Validation failed"]);
      return false;
    }
    setStatus("ok", `Valid (schema ${data.schema_version})`);
    els.resultsBody.innerHTML = `<p class="muted">Experiment graph passed static validation (schema ${escapeHtml(data.schema_version)}).</p>`;
    return true;
  }

  async function runCurrent() {
    setStatus("neutral", "Running…");
    const doc = buildExportDocument();
    const resp = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(doc),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      renderErrors(data.errors || [data.error || "Run failed"]);
      return null;
    }
    renderRunResult(data.result);
    return data.result;
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

  function fitView() {
    if (!state.doc || !state.doc.components.length) return;
    let minX = Infinity;
    let minY = Infinity;
    for (const c of state.doc.components) {
      minX = Math.min(minX, toCanvasX(c.position.x));
      minY = Math.min(minY, toCanvasY(c.position.y));
    }
    els.canvasViewport.scrollTo({
      left: Math.max(0, minX - 24),
      top: Math.max(0, minY - 24),
      behavior: "smooth",
    });
  }

  async function loadExample(filename) {
    const resp = await fetch(`/api/examples/${encodeURIComponent(filename)}`);
    if (!resp.ok) {
      setStatus("err", "Load failed");
      return;
    }
    const doc = await resp.json();
    setExperiment(doc);
    fitView();
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
        setExperiment(JSON.parse(text));
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
      addComponent(ctype, { x: e.clientX - rect.left, y: e.clientY - rect.top });
    });

    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") cancelWiring();
    });
  }

  async function init() {
    bindEvents();
    const [manResp, exResp] = await Promise.all([
      fetch("/api/manifest"),
      fetch("/api/examples"),
    ]);
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
    renderErrors([`Failed to initialize workbench: ${err.message}`]);
  });
})();
