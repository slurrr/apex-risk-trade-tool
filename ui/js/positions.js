(function () {
  const API_BASE = (window.TradeApp && window.TradeApp.API_BASE) || 
  window.API_BASE || 
  `${window.location.protocol}//${window.location.hostname}:8000`;
  const formatNumber = (window.TradeApp && window.TradeApp.formatNumber) || ((v) => v);
  const openPanels = {
    manage: new Set(),
    modify: new Set(),
  };
  const sliderValues = new Map();
  const limitPriceValues = new Map();
  const tpValues = new Map();
  const slValues = new Map();
  let lastPositions = [];
  let editLockCount = 0;
  let pendingRender = null;
  const lockEditing = () => {};
  const unlockEditing = () => {};

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

  function renderPositions(positions) {
    lastPositions = positions;
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
    tbody.innerHTML = "";
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

    positions.forEach((pos) => {
      const row = document.createElement("tr");
      row.dataset.positionId = pos.id || pos.symbol || "";
      const pnlValue = typeof pos.pnl === "number" ? pos.pnl : Number(pos.pnl);
      const pnlClass = Number.isFinite(pnlValue) ? (pnlValue > 0 ? "positive" : pnlValue < 0 ? "negative" : "") : "";
      const positionId = row.dataset.positionId;
      const sliderVal = sliderValues.get(positionId) ?? 100;
      const limitVal = limitPriceValues.get(positionId) ?? "";
      const tpVal = tpValues.get(positionId) ?? "";
      const slVal = slValues.get(positionId) ?? "";
      row.innerHTML = `
        <td>${pos.symbol || ""}</td>
        <td>${formatNumber(pos.entry_price)}</td>
        <td>${pos.side || ""}</td>
        <td>${pos.size ?? ""}</td>
        <td class="pnl ${pnlClass}">${formatNumber(pos.pnl)}</td>
        <td class="tp-sl-cell">
          <div class="tp-sl-row">
            <div class="stacked">
              <span class="tp">TP: ${pos.take_profit ?? "None"}</span>
              <span class="sl">SL: ${pos.stop_loss ?? "None"}</span>
            </div>
            <button class="btn ghost modify-btn" type="button">Modify</button>
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
          <button class="btn ghost manage-btn" type="button">Manage</button>
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
  }

  async function loadPositions(forceResync = false) {
    const errorBox = document.getElementById("positions-error");
    errorBox.textContent = "";
    try {
      const positions = await fetchPositions(forceResync);
      renderPositions(positions);
    } catch (err) {
      errorBox.textContent = err.message;
    }
  }

  function startStream(attempt = 0) {
    const errorBox = document.getElementById("positions-error");
    try {
      const wsUrl = API_BASE.replace(/^http/, "ws") + "/ws/stream";
      const socket = new WebSocket(wsUrl);
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "positions" && Array.isArray(msg.payload)) {
            console.log("WS positions message", msg);
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
        errorBox.textContent = "Stream closed; attempting to reconnect.";
        setTimeout(() => startStream(Math.min(attempt + 1, 5)), 1000 * Math.min(attempt + 1, 5));
      };
    } catch (err) {
      errorBox.textContent = err.message;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const refreshBtn = document.getElementById("refresh-positions");
    const table = document.getElementById("positions-table");

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
      const modifyBtn = event.target.closest(".modify-btn");
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
      if (modifyBtn) {
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

    document.addEventListener("click", (event) => {
      const target = event.target;
      const clickedManagePanel = target.closest(".manage-panel");
      const clickedModifyPanel = target.closest(".modify-panel");
      const clickedManageBtn = target.closest(".manage-btn");
      const clickedModifyBtn = target.closest(".modify-btn");
      // If click is inside a panel or on its toggle buttons, do nothing.
      if (clickedManagePanel || clickedModifyPanel || clickedManageBtn || clickedModifyBtn) {
        return;
      }
      // Otherwise collapse all open panels
      document.querySelectorAll(".manage-panel").forEach((panel) => panel.classList.add("hidden"));
      document.querySelectorAll(".modify-panel").forEach((panel) => panel.classList.add("hidden"));
      openPanels.manage.clear();
      openPanels.modify.clear();
      document.querySelectorAll(".confirm-popover").forEach((pop) => pop.remove());
    });

    loadPositions();
    startStream();
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
