(function () {
  const API_BASE = (window.TradeApp && window.TradeApp.API_BASE) || 
  window.API_BASE || 
  `${window.location.protocol}//${window.location.hostname}:8000`;
  const formatNumber = (window.TradeApp && window.TradeApp.formatNumber) || ((v) => v);
  const PNL_BASIS_STORAGE_KEY = "positions_pnl_basis_v1";
  const PNL_BASIS_OPTIONS = new Set(["notional", "equity", "size_move"]);
  const openPanels = {
    manage: new Set(),
    modify: new Set(),
  };
  const sliderValues = new Map();
  const limitPriceValues = new Map();
  const tpValues = new Map();
  const slValues = new Map();
  let lastPositions = [];
  let lastPositionsUpdate = 0;
  let positionsRefreshInFlight = false;
  let editLockCount = 0;
  let pendingRender = null;
  let streamSocket = null;
  let streamToken = 0;
  let currentPnlBasis = "notional";
  const lockEditing = () => {};
  const unlockEditing = () => {};

  function normalizePnlBasis(value) {
    const clean = (value || "").toString().trim().toLowerCase();
    return PNL_BASIS_OPTIONS.has(clean) ? clean : "notional";
  }

  function getPnlBasisLabel(value) {
    const basis = normalizePnlBasis(value);
    if (basis === "equity") return "Equity %";
    if (basis === "size_move") return "Underlying";
    return "Notional % (ROE)";
  }

  function loadStoredPnlBasis() {
    try {
      if (!window.localStorage) return "notional";
      return normalizePnlBasis(window.localStorage.getItem(PNL_BASIS_STORAGE_KEY));
    } catch (err) {
      return "notional";
    }
  }

  function persistPnlBasis(value) {
    try {
      if (!window.localStorage) return;
      window.localStorage.setItem(PNL_BASIS_STORAGE_KEY, normalizePnlBasis(value));
    } catch (err) {
      // ignore storage errors
    }
  }

  function showConfirmPopover(targetBtn, positionId, message, onConfirm) {
    if (!targetBtn) return;
    const host =
      targetBtn.closest(".modify-panel") ||
      targetBtn.closest(".tp-sl-cell") ||
      targetBtn.closest(".manage-panel") ||
      targetBtn.closest(".actions-cell") ||
      targetBtn.parentElement;
    const existing = host?.querySelector(".confirm-popover");
    if (existing) existing.remove();
    const closeModifyPanel = () => {
      const row = targetBtn.closest("tr");
      if (row) {
        const panel = row.querySelector(".modify-panel");
        if (panel) panel.classList.add("hidden");
      }
      if (positionId) {
        openPanels.modify.delete(positionId);
      }
    };
    if (!host) {
      if (window.confirm(message || "Are you sure?")) {
        onConfirm && onConfirm();
        closeModifyPanel();
      }
      return;
    }
    const pop = document.createElement("div");
    pop.className = "confirm-popover";
    pop.innerHTML = `
      <span class="confirm-text">${message || "Confirm?"}</span>
      <button type="button" class="btn ghost btn-cancel">No</button>
      <button type="button" class="btn primary btn-yes">Yes</button>
    `;
    const cancelBtn = pop.querySelector(".btn-cancel");
    const yesBtn = pop.querySelector(".btn-yes");
    cancelBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      pop.remove();
      closeModifyPanel();
      if (!document.querySelector(".confirm-popover") && pendingRender && editLockCount === 0) {
        const toRender = pendingRender;
        pendingRender = null;
        renderPositions(toRender);
      }
    });
    yesBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      // Leave the popover visible until the action kicks off to reduce mis-click risk.
      if (onConfirm) {
        const run = onConfirm();
        if (run && typeof run.then === "function") {
          try {
            await run;
          } catch (err) {
            const errorBox = document.getElementById("positions-error");
            if (errorBox) {
              errorBox.textContent = err?.message || "Unable to complete action";
            }
          }
        }
      }
      pop.remove();
      closeModifyPanel();
      if (!document.querySelector(".confirm-popover") && pendingRender && editLockCount === 0) {
        const toRender = pendingRender;
        pendingRender = null;
        renderPositions(toRender);
      }
    });
    host.appendChild(pop);
  }

  async function fetchPositions(forceResync = false) {
    const query = forceResync ? "?resync=1" : "";
    const resp = await fetch(`${API_BASE}/api/positions${query}`);
    const data = await resp.json();
    if (!resp.ok) {
      const msg = data?.detail || "Unable to load positions";
      throw new Error(msg);
    }
    return data;
  }

  async function closePosition(positionId, percent, type, limitPrice) {
    const resp = await fetch(`${API_BASE}/api/positions/${positionId}/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ close_percent: percent, close_type: type, limit_price: limitPrice }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      const msg = data?.detail || "Unable to close position";
      throw new Error(msg);
    }
    return data;
  }

  async function updateTargets(positionId, tp, sl, opts = {}) {
    const body = {};
    if (tp !== null && tp !== undefined) body.take_profit = tp;
    if (sl !== null && sl !== undefined) body.stop_loss = sl;
    if (opts.clearTp) body.clear_tp = true;
    if (opts.clearSl) body.clear_sl = true;
    const resp = await fetch(`${API_BASE}/api/positions/${positionId}/targets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) {
      const msg = data?.detail || "Unable to update targets";
      throw new Error(msg);
    }
    return data;
  }

  function normalizePositionList(list) {
    if (!Array.isArray(list)) return [];
    return list
      .map((pos) => ({
        id: String(pos.id || pos.symbol || ""),
        symbol: pos.symbol || "",
        side: pos.side || "",
        size: pos.size ?? null,
        entry: pos.entry_price ?? null,
        pnl: pos.pnl ?? null,
        margin_used: pos.margin_used ?? null,
        leverage: pos.leverage ?? null,
        tp: pos.take_profit ?? null,
        sl: pos.stop_loss ?? null,
        tp_count: pos.take_profit_count ?? 0,
        sl_count: pos.stop_loss_count ?? 0,
      }))
      .sort((a, b) => a.id.localeCompare(b.id));
  }

  function positionsEqual(a, b) {
    const normA = normalizePositionList(a);
    const normB = normalizePositionList(b);
    if (normA.length !== normB.length) return false;
    for (let i = 0; i < normA.length; i += 1) {
      const left = normA[i];
      const right = normB[i];
      if (
        left.id !== right.id ||
        left.symbol !== right.symbol ||
        left.side !== right.side ||
        left.size !== right.size ||
        left.entry !== right.entry ||
        left.pnl !== right.pnl ||
        left.margin_used !== right.margin_used ||
        left.leverage !== right.leverage ||
        left.tp !== right.tp ||
        left.sl !== right.sl ||
        left.tp_count !== right.tp_count ||
        left.sl_count !== right.sl_count
      ) {
        return false;
      }
    }
    return true;
  }

  function renderPositions(positions, options = {}) {
    const { force = false } = options;
    if (!force && positionsEqual(lastPositions, positions)) {
      return;
    }
    lastPositions = positions;
    lastPositionsUpdate = Date.now();
    // If a confirmation popover is open, defer rendering to avoid wiping it out mid-action.
    if (document.querySelector(".confirm-popover")) {
      pendingRender = positions;
      return;
    }
    if (editLockCount > 0) {
      pendingRender = positions;
      return;
    }
    pendingRender = null;
    const tbody = document.querySelector("#positions-table tbody");
    const emptyState = document.getElementById("positions-empty");
    const totalFoot = document.getElementById("positions-total-foot");
    const totalOiCell = document.getElementById("positions-total-oi");
    tbody.innerHTML = "";
    if (totalFoot) totalFoot.classList.add("hidden");
    if (totalOiCell) totalOiCell.textContent = "";
    if (!positions || positions.length === 0) {
      emptyState.style.display = "block";
      return;
    }
    emptyState.style.display = "none";

    const existingIds = new Set((positions || []).map((p) => String(p.id || p.symbol || "")));
    // prune state for positions that no longer exist
    for (const id of Array.from(openPanels.manage)) {
      if (!existingIds.has(id)) openPanels.manage.delete(id);
    }
    for (const id of Array.from(openPanels.modify)) {
      if (!existingIds.has(id)) openPanels.modify.delete(id);
    }
    for (const id of Array.from(sliderValues.keys())) {
      if (!existingIds.has(id)) sliderValues.delete(id);
    }
    for (const id of Array.from(limitPriceValues.keys())) {
      if (!existingIds.has(id)) limitPriceValues.delete(id);
    }
    for (const id of Array.from(tpValues.keys())) {
      if (!existingIds.has(id)) tpValues.delete(id);
    }
    for (const id of Array.from(slValues.keys())) {
      if (!existingIds.has(id)) slValues.delete(id);
    }

    const formatNotional = (value) =>
      Number.isFinite(value)
        ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
        : "--";
    const formatPercent = (value) =>
      Number.isFinite(value)
        ? `${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
        : "--";
    let totalOpenInterest = 0;
    let hasOpenInterest = false;
    const accountEquity =
      window.TradeApp && window.TradeApp.state && window.TradeApp.state.lastAccountSummary
        ? Number(window.TradeApp.state.lastAccountSummary.total_equity)
        : null;

    positions.forEach((pos) => {
      const row = document.createElement("tr");
      row.dataset.positionId = pos.id || pos.symbol || "";
      const pnlValue = typeof pos.pnl === "number" ? pos.pnl : Number(pos.pnl);
      const pnlClass = Number.isFinite(pnlValue) ? (pnlValue > 0 ? "positive" : pnlValue < 0 ? "negative" : "") : "";
      const entryValue = Number(pos.entry_price);
      const sizeValue = Number(pos.size);
      const notionalValue =
        Number.isFinite(entryValue) && Number.isFinite(sizeValue) ? Math.abs(entryValue * sizeValue) : null;
      if (Number.isFinite(notionalValue)) {
        totalOpenInterest += notionalValue;
        hasOpenInterest = true;
      }
      const pnlPctValue =
        Number.isFinite(pnlValue) && Number.isFinite(notionalValue) && notionalValue > 0
          ? (pnlValue / notionalValue) * 100
          : null;
      const marginUsedValue = Number(pos.margin_used);
      const marginReturnPct =
        Number.isFinite(pnlValue) && Number.isFinite(marginUsedValue) && marginUsedValue > 0
          ? (pnlValue / marginUsedValue) * 100
          : null;
      const equityPctValue =
        Number.isFinite(pnlValue) && Number.isFinite(accountEquity) && Math.abs(accountEquity) > 1e-9
          ? (pnlValue / accountEquity) * 100
          : null;
      const perUnitMove =
        Number.isFinite(pnlValue) && Number.isFinite(sizeValue) && Math.abs(sizeValue) > 1e-9
          ? (pnlValue / sizeValue)
          : null;
      const underlyingMovePct =
        Number.isFinite(perUnitMove) && Number.isFinite(entryValue) && Math.abs(entryValue) > 1e-9
          ? (perUnitMove / entryValue) * 100
          : null;
      const tpCount = Number(pos.take_profit_count || 0);
      const slCount = Number(pos.stop_loss_count || 0);
      const tpBadge = tpCount > 1 ? `<span class="tpsl-count-badge" title="${tpCount} TP orders">${tpCount}</span>` : "";
      const slBadge = slCount > 1 ? `<span class="tpsl-count-badge" title="${slCount} SL orders">${slCount}</span>` : "";
      const positionId = row.dataset.positionId;
      const sliderVal = sliderValues.get(positionId) ?? 100;
      const limitVal = limitPriceValues.get(positionId) ?? "";
      const tpVal = tpValues.get(positionId) ?? "";
      const slVal = slValues.get(positionId) ?? "";
      let pnlDetail = "";
      if (currentPnlBasis === "equity") {
        pnlDetail = Number.isFinite(equityPctValue) ? formatPercent(equityPctValue) : "--";
      } else if (currentPnlBasis === "size_move") {
        pnlDetail = Number.isFinite(underlyingMovePct) ? formatPercent(underlyingMovePct) : "--";
      } else {
        pnlDetail = Number.isFinite(marginReturnPct)
          ? formatPercent(marginReturnPct)
          : (Number.isFinite(pnlPctValue) ? formatPercent(pnlPctValue) : "--");
      }
      const pnlDisplay = pnlDetail && pnlDetail !== "--"
        ? `${formatNumber(pos.pnl)} (${pnlDetail})`
        : `${formatNumber(pos.pnl)}`;
      row.innerHTML = `
        <td>${pos.symbol || ""}</td>
        <td>${formatNumber(pos.entry_price)}</td>
        <td>${pos.side || ""}</td>
        <td>${notionalValue !== null ? formatNotional(notionalValue) : ""}</td>
        <td class="pnl ${pnlClass}">${pnlDisplay}</td>
        <td class="tp-sl-cell">
          <div class="tp-sl-row tp-sl-click-target" role="button" tabindex="0" aria-label="Manage TP/SL">
            <div class="stacked">
              <span class="tp">TP: ${pos.take_profit ?? "None"} ${tpBadge}</span>
              <span class="sl">SL: ${pos.stop_loss ?? "None"} ${slBadge}</span>
            </div>
          </div>
          <div class="modify-panel hidden">
            <div class="manage-row">
              <label class="field">
                <span>TP</span>
                <input type="number" step="0.0001" class="tp-input" placeholder="Take profit price" value="${tpVal}" />
              </label>
              <label class="field">
                <span>SL</span>
                <input type="number" step="0.0001" class="sl-input" placeholder="Stop loss price" value="${slVal}" />
              </label>
              <button class="btn primary submit-modify" type="button">Submit</button>
            </div>
            <div class="manage-row">
              <button class="btn ghost clear-tp" type="button">Clear TP</button>
              <button class="btn ghost clear-sl" type="button">Clear SL</button>
            </div>
          </div>
        </td>
      `;
      const actionsCell = document.createElement("td");
      actionsCell.classList.add("actions-cell");
      actionsCell.innerHTML = `
        <div class="actions-cell">
          <button class="btn ghost manage-btn" type="button">Close</button>
        </div>
        <div class="manage-panel hidden">
          <div class="manage-row">
            <div class="slider-row full-width">
              <div class="slider-track">
                <input type="range" min="0" max="100" step="1" value="${sliderVal}" class="close-slider" />
                <span class="slider-value">${sliderVal}%</span>
              </div>
              <div class="slider-marks">
                <span class="slider-mark" data-value="0">0</span>
                <span class="slider-mark" data-value="25">25</span>
                <span class="slider-mark" data-value="50">50</span>
                <span class="slider-mark" data-value="75">75</span>
                <span class="slider-mark" data-value="100">100</span>
              </div>
            </div>
            <div class="actions-cell">
              <button class="btn primary market-close" type="button">Market Close</button>
              <div class="limit-group">
                <input type="number" step="0.0001" placeholder="Limit price" class="limit-price field-input" value="${limitVal}" />
                <button class="btn ghost limit-close" type="button">Limit Close</button>
              </div>
            </div>
          </div>
        </div>
      `;
      const modifyPanel = row.querySelector(".modify-panel");
      const managePanel = actionsCell.querySelector(".manage-panel");
      if (openPanels.modify.has(positionId) && modifyPanel) {
        modifyPanel.classList.remove("hidden");
      }
      if (openPanels.manage.has(positionId) && managePanel) {
        managePanel.classList.remove("hidden");
      }
      row.appendChild(actionsCell);
      tbody.appendChild(row);
    });

    if (hasOpenInterest && totalFoot && totalOiCell) {
      totalOiCell.textContent = `Total OI: ${formatNotional(totalOpenInterest)}`;
      totalFoot.classList.remove("hidden");
    }
  }

  async function loadPositions(forceResync = false) {
    if (positionsRefreshInFlight) return;
    positionsRefreshInFlight = true;
    const errorBox = document.getElementById("positions-error");
    errorBox.textContent = "";
    try {
      const positions = await fetchPositions(forceResync);
      renderPositions(positions);
    } catch (err) {
      errorBox.textContent = err.message;
    } finally {
      positionsRefreshInFlight = false;
    }
  }

  function startPositionsHeartbeat() {
    let lastForcedRefresh = 0;
    window.setInterval(() => {
      const now = Date.now();
      const staleMs = 20000;
      const forcedRefreshMs = 45000;
      const stale = !lastPositionsUpdate || (now - lastPositionsUpdate) > staleMs;
      const dueForced = !lastForcedRefresh || (now - lastForcedRefresh) > forcedRefreshMs;
      if (stale || dueForced) {
        lastForcedRefresh = now;
        loadPositions(false);
      }
    }, 10000);
  }

  function startStream(attempt = 0, token = streamToken) {
    const errorBox = document.getElementById("positions-error");
    try {
      const wsUrl = API_BASE.replace(/^http/, "ws") + "/ws/stream";
      const socket = new WebSocket(wsUrl);
      streamSocket = socket;
      socket.onmessage = (event) => {
        if (token !== streamToken) {
          return;
        }
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "positions" && Array.isArray(msg.payload)) {
            renderPositions(msg.payload);
          }
        } catch (err) {
          // ignore malformed frames
        }
      };
      socket.onerror = () => {
        errorBox.textContent = "Stream disconnected; falling back to manual refresh.";
      };
      socket.onclose = () => {
        if (token !== streamToken) {
          return;
        }
        errorBox.textContent = "Stream closed; attempting to reconnect.";
        setTimeout(
          () => startStream(Math.min(attempt + 1, 5), token),
          1000 * Math.min(attempt + 1, 5)
        );
      };
    } catch (err) {
      errorBox.textContent = err.message;
    }
  }

  function restartStream() {
    streamToken += 1;
    if (streamSocket && streamSocket.readyState < WebSocket.CLOSING) {
      streamSocket.close();
    }
    startStream(0, streamToken);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const refreshBtn = document.getElementById("refresh-positions");
    const table = document.getElementById("positions-table");
    const pnlBasisTrigger = document.getElementById("positions-pnl-basis-trigger");
    const pnlBasisOptions = document.getElementById("positions-pnl-basis-options");

    currentPnlBasis = loadStoredPnlBasis();
    if (pnlBasisTrigger) {
      pnlBasisTrigger.textContent = getPnlBasisLabel(currentPnlBasis);
    }
    if (pnlBasisOptions) {
      const buttons = Array.from(pnlBasisOptions.querySelectorAll("button[data-value]"));
      const syncActive = () => {
        buttons.forEach((btn) => {
          const isActive = normalizePnlBasis(btn.dataset.value) === currentPnlBasis;
          btn.classList.toggle("is-active", isActive);
          btn.setAttribute("aria-selected", String(isActive));
        });
      };
      syncActive();
      if (pnlBasisTrigger) {
        pnlBasisTrigger.addEventListener("click", () => {
          const isOpen = pnlBasisOptions.classList.contains("open");
          pnlBasisOptions.classList.toggle("open", !isOpen);
          pnlBasisTrigger.setAttribute("aria-expanded", String(!isOpen));
        });
      }
      pnlBasisOptions.addEventListener("click", (event) => {
        const btn = event.target.closest("button[data-value]");
        if (!btn) return;
        const next = normalizePnlBasis(btn.dataset.value);
        if (next !== currentPnlBasis) {
          currentPnlBasis = next;
          persistPnlBasis(currentPnlBasis);
          if (pnlBasisTrigger) {
            pnlBasisTrigger.textContent = getPnlBasisLabel(currentPnlBasis);
          }
          syncActive();
          renderPositions(lastPositions || [], { force: true });
        }
        pnlBasisOptions.classList.remove("open");
        if (pnlBasisTrigger) {
          pnlBasisTrigger.setAttribute("aria-expanded", "false");
        }
      });
    }

    refreshBtn.addEventListener("click", () => loadPositions(true));

    table.addEventListener("input", (event) => {
      const slider = event.target.closest(".close-slider");
      if (slider) {
        const value = slider.value;
        const valEl = slider.parentElement?.querySelector(".slider-value");
        if (valEl) valEl.textContent = `${value}%`;
        const row = slider.closest("tr");
        if (row && row.dataset.positionId) {
          sliderValues.set(row.dataset.positionId, parseFloat(value));
        }
      }
      const limitInput = event.target.closest(".limit-price");
      if (limitInput) {
        const row = limitInput.closest("tr");
        if (row && row.dataset.positionId) {
          limitPriceValues.set(row.dataset.positionId, limitInput.value);
        }
      }
      const tpInput = event.target.closest(".tp-input");
      if (tpInput) {
        const row = tpInput.closest("tr");
        if (row && row.dataset.positionId) {
          tpValues.set(row.dataset.positionId, tpInput.value);
        }
      }
      const slInput = event.target.closest(".sl-input");
      if (slInput) {
        const row = slInput.closest("tr");
        if (row && row.dataset.positionId) {
          slValues.set(row.dataset.positionId, slInput.value);
        }
      }
    });

    table.addEventListener("click", async (event) => {
      const manageBtn = event.target.closest(".manage-btn");
      const tpSlTarget = event.target.closest(".tp-sl-click-target");
      const mark = event.target.closest(".slider-mark");
      const marketCloseBtn = event.target.closest(".market-close");
      const limitCloseBtn = event.target.closest(".limit-close");
      const submitModify = event.target.closest(".submit-modify");
      const clearTpBtn = event.target.closest(".clear-tp");
      const clearSlBtn = event.target.closest(".clear-sl");
      const row = event.target.closest("tr");
      if (!row) return;
      const positionId = row.dataset.positionId;
      const errorBox = document.getElementById("positions-error");

      if (mark) {
        const val = mark.dataset.value ? parseFloat(mark.dataset.value) : null;
        const slider = row.querySelector(".close-slider");
        const valEl = row.querySelector(".slider-value");
        if (val !== null && slider) {
          slider.value = String(val);
          if (valEl) valEl.textContent = `${val}%`;
          sliderValues.set(positionId, val);
        }
        return;
      }

      if (manageBtn) {
        event.stopPropagation();
        const panel = row.querySelector(".manage-panel");
        if (panel) {
          const isOpen = !panel.classList.contains("hidden");
          panel.classList.toggle("hidden");
          if (isOpen) {
            openPanels.manage.delete(positionId);
          } else {
            openPanels.manage.add(positionId);
          }
        }
        return;
      }
      if (tpSlTarget) {
        event.stopPropagation();
        const panel = row.querySelector(".modify-panel");
        if (panel) {
          const isOpen = !panel.classList.contains("hidden");
          panel.classList.toggle("hidden");
          if (isOpen) {
            openPanels.modify.delete(positionId);
          } else {
            openPanels.modify.add(positionId);
          }
        }
        return;
      }
      if (marketCloseBtn) {
        showConfirmPopover(marketCloseBtn, positionId, "Market close?", async () => {
          const slider = row.querySelector(".close-slider");
          const percent = slider ? parseFloat(slider.value) : 0;
          marketCloseBtn.disabled = true;
          try {
            await closePosition(positionId, percent, "market", null);
            await loadPositions();
            openPanels.manage.delete(positionId);
            sliderValues.delete(positionId);
            limitPriceValues.delete(positionId);
            if (window.TradeApp && window.TradeApp.loadAccountSummary) {
              window.TradeApp.loadAccountSummary();
            }
          } catch (err) {
            errorBox.textContent = err.message;
          } finally {
            marketCloseBtn.disabled = false;
          }
        });
        return;
      }
      if (limitCloseBtn) {
        const slider = row.querySelector(".close-slider");
        const percent = slider ? parseFloat(slider.value) : 0;
        const priceInput = row.querySelector(".limit-price");
        const price = priceInput && priceInput.value ? parseFloat(priceInput.value) : null;
        if (!price) {
          errorBox.textContent = "Provide a limit price to submit a limit close.";
          return;
        }
        limitCloseBtn.disabled = true;
        try {
          await closePosition(positionId, percent, "limit", price);
          await loadPositions();
          openPanels.manage.delete(positionId);
          sliderValues.delete(positionId);
          limitPriceValues.delete(positionId);
          if (window.TradeApp && window.TradeApp.loadAccountSummary) {
            window.TradeApp.loadAccountSummary();
          }
        } catch (err) {
          errorBox.textContent = err.message;
        } finally {
          limitCloseBtn.disabled = false;
        }
        return;
      }
      if (clearTpBtn) {
        showConfirmPopover(clearTpBtn, positionId, "Clear TP?", async () => {
          clearTpBtn.disabled = true;
          try {
            await updateTargets(positionId, null, null, { clearTp: true });
            await loadPositions();
            tpValues.delete(positionId);
          } catch (err) {
            errorBox.textContent = err.message;
          } finally {
            clearTpBtn.disabled = false;
          }
        });
        return;
      }
      if (clearSlBtn) {
        showConfirmPopover(clearSlBtn, positionId, "Clear SL?", async () => {
          clearSlBtn.disabled = true;
          try {
            await updateTargets(positionId, null, null, { clearSl: true });
            await loadPositions();
            slValues.delete(positionId);
          } catch (err) {
            errorBox.textContent = err.message;
          } finally {
            clearSlBtn.disabled = false;
          }
        });
        return;
      }
      if (submitModify) {
        const tpInput = row.querySelector(".tp-input");
        const slInput = row.querySelector(".sl-input");
        const tp = tpInput && tpInput.value ? parseFloat(tpInput.value) : null;
        const sl = slInput && slInput.value ? parseFloat(slInput.value) : null;
        if (tp === null && sl === null) {
          errorBox.textContent = "Provide TP and/or SL before submitting.";
          return;
        }
        submitModify.disabled = true;
        try {
          await updateTargets(positionId, tp, sl);
          await loadPositions();
          openPanels.modify.delete(positionId);
          tpValues.delete(positionId);
          slValues.delete(positionId);
        } catch (err) {
          errorBox.textContent = err.message;
        } finally {
          submitModify.disabled = false;
        }
        return;
      }
    });

    table.addEventListener("keydown", (event) => {
      const tpSlTarget = event.target.closest(".tp-sl-click-target");
      if (!tpSlTarget) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      const row = tpSlTarget.closest("tr");
      if (!row) return;
      const positionId = row.dataset.positionId;
      const panel = row.querySelector(".modify-panel");
      if (!panel) return;
      const isOpen = !panel.classList.contains("hidden");
      panel.classList.toggle("hidden");
      if (isOpen) {
        openPanels.modify.delete(positionId);
      } else {
        openPanels.modify.add(positionId);
      }
    });

    document.addEventListener("click", (event) => {
      const target = event.target;
      const clickedManagePanel = target.closest(".manage-panel");
      const clickedModifyPanel = target.closest(".modify-panel");
      const clickedManageBtn = target.closest(".manage-btn");
      const clickedModifyBtn = target.closest(".tp-sl-click-target");
      const clickedPnlBasis = target.closest(".positions-basis-dropdown");
      // If click is inside a panel or on its toggle buttons, do nothing.
      if (clickedManagePanel || clickedModifyPanel || clickedManageBtn || clickedModifyBtn || clickedPnlBasis) {
        return;
      }
      if (pnlBasisOptions) pnlBasisOptions.classList.remove("open");
      if (pnlBasisTrigger) pnlBasisTrigger.setAttribute("aria-expanded", "false");
      // Otherwise collapse all open panels
      document.querySelectorAll(".manage-panel").forEach((panel) => panel.classList.add("hidden"));
      document.querySelectorAll(".modify-panel").forEach((panel) => panel.classList.add("hidden"));
      openPanels.manage.clear();
      openPanels.modify.clear();
      document.querySelectorAll(".confirm-popover").forEach((pop) => pop.remove());
    });

    loadPositions();
    restartStream();
    startPositionsHeartbeat();

    window.addEventListener("venue:changed", () => {
      loadPositions(true);
      restartStream();
    });

    window.addEventListener("account:summary", () => {
      if (currentPnlBasis === "equity" && Array.isArray(lastPositions) && lastPositions.length > 0) {
        renderPositions(lastPositions, { force: true });
      }
    });

    window.setInterval(() => {
      const staleMs = 20000;
      if (!lastPositionsUpdate || Date.now() - lastPositionsUpdate > staleMs) {
        loadPositions();
      }
    }, 10000);
  });

  document.addEventListener("focusin", (event) => {
    if (event.target.closest(".manage-panel") || event.target.closest(".modify-panel")) {
      editLockCount += 1;
    }
  });

  document.addEventListener("focusout", (event) => {
    if (event.target.closest(".manage-panel") || event.target.closest(".modify-panel")) {
      editLockCount = Math.max(0, editLockCount - 1);
      if (editLockCount === 0 && pendingRender && !document.querySelector(".confirm-popover")) {
        renderPositions(pendingRender);
        pendingRender = null;
      }
    }
  });
})();
