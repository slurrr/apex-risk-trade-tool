(function () {
  const API_BASE = (window.TradeApp && window.TradeApp.API_BASE) || 
  window.API_BASE || 
  `${window.location.protocol}//${window.location.hostname}:8000`;
  const validateSymbol = (window.TradeApp && window.TradeApp.validateSymbol) || ((val) => val?.toUpperCase());
  const warnUserPopup = (window.TradeApp && window.TradeApp.warnUserPopup) || ((msg) => window.alert(msg));
  const markStopInputInvalid = (window.TradeApp && window.TradeApp.markStopInputInvalid) || (() => {});
  const createTradeTraceId = (window.TradeApp && window.TradeApp.createTradeTraceId) || (() => `trd-${Date.now()}`);
  const executeUiState = {
    current: null,
  };
  let executeSubmitInFlight = false;

  function getNormalizeTradePayloadBeforeSubmit() {
    return (window.TradeApp && window.TradeApp.normalizeTradePayloadBeforeSubmit) || null;
  }

  function isFormActionLocked() {
    const fn = window.TradeApp && window.TradeApp.isFormActionLocked;
    return typeof fn === "function" ? Boolean(fn()) : false;
  }

  async function postExecute(payload) {
    const response = await fetch(`${API_BASE}/api/trade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, execute: true, preview: false }),
    });
    const data = await response.json();
    if (!response.ok) {
      const msg = data?.detail || "Execute request failed";
      throw new Error(msg);
    }
    return data;
  }

  function formatCompact(value, maxDigits = 6) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "--";
    return numeric.toLocaleString(undefined, { maximumFractionDigits: maxDigits });
  }

  function getCard(container) {
    return container ? container.closest(".result") : null;
  }

  function showCard(container) {
    const card = getCard(container);
    if (card) card.classList.remove("hidden");
  }

  function renderWarnings(warnings) {
    if (!Array.isArray(warnings) || warnings.length === 0) return "";
    const rows = warnings.map((warning) => `<div class="trade-warning">${warning}</div>`).join("");
    return `<div class="trade-warnings">${rows}</div>`;
  }

  function normalizeSide(value) {
    const raw = (value || "").toString().trim().toUpperCase();
    if (raw === "BUY" || raw === "LONG") return "BUY";
    if (raw === "SELL" || raw === "SHORT") return "SELL";
    return raw || null;
  }

  function normalizePositionSide(value) {
    const raw = (value || "").toString().trim().toUpperCase();
    if (raw === "LONG" || raw === "BUY") return "BUY";
    if (raw === "SHORT" || raw === "SELL") return "SELL";
    return null;
  }

  function computeNotional(result) {
    const explicit = Number(result?.notional);
    if (Number.isFinite(explicit)) return explicit;
    const size = Number(result?.size);
    const entry = Number(result?.entry_price);
    if (Number.isFinite(size) && Number.isFinite(entry)) {
      return Math.abs(size * entry);
    }
    return null;
  }

  function setExecutionStatus(status, { animate = false } = {}) {
    const statusEl = document.getElementById("execute-status");
    if (!statusEl) return;
    const normalized = (status || "").toString().trim().toLowerCase();
    const isFilled = normalized === "filled";
    statusEl.classList.toggle("is-filled", isFilled);
    statusEl.innerHTML = isFilled
      ? `<span class="trade-status-check ${animate ? "is-pop" : ""}" aria-hidden="true">✓</span><span>Filled</span>`
      : "<span>Submitted</span>";
  }

  function maybeMarkExecutionFilledFromPositions(positions) {
    if (!executeUiState.current || executeUiState.current.status !== "submitted") return;
    if (!Array.isArray(positions) || !positions.length) return;
    const targetSymbol = (executeUiState.current.symbol || "").toUpperCase();
    const targetSide = normalizeSide(executeUiState.current.side);
    const matched = positions.some((pos) => {
      const sym = (pos?.symbol || "").toString().trim().toUpperCase();
      const side = normalizePositionSide(pos?.side);
      if (!sym || sym !== targetSymbol) return false;
      if (!targetSide) return true;
      return side === targetSide;
    });
    if (!matched) return;
    executeUiState.current.status = "filled";
    setExecutionStatus("filled", { animate: true });
  }

  function renderExecute(container, result, context = {}) {
    showCard(container);
    const side = String(result.side || context.side || "").toUpperCase();
    const sideClass = side === "SELL" ? "sell" : "buy";
    const symbol = context.symbol || result.symbol || "";
    const displaySymbol = symbol || "--";
    const notional = computeNotional(result);
    const notionalDisplay = Number.isFinite(notional) ? formatCompact(notional, 2) : "--";
    const sizeDisplay = formatCompact(result.size);
    container.innerHTML = `
      <div class="trade-output">
        <div class="trade-output-head">
          <span class="trade-action-pill ${sideClass}">${side || "--"}</span>
          <span class="trade-symbol">${displaySymbol}</span>
        </div>
        <div class="trade-line">${notionalDisplay}</div>
        <div class="trade-line dim">Order to ${side || "--"} ${sizeDisplay} ${displaySymbol.split("-")[0] || displaySymbol} <span id="execute-status" class="trade-status-pill"><span>Submitted</span></span></div>
        <div class="trade-line dim">Order ID: ${result.exchange_order_id || "--"}</div>
        ${renderWarnings(result.warnings)}
      </div>
    `;
    executeUiState.current = {
      status: "submitted",
      symbol: displaySymbol,
      side,
      orderId: result.exchange_order_id || null,
      submittedAt: Date.now(),
    };
  }

  document.addEventListener("DOMContentLoaded", () => {
    const executeBtn = document.getElementById("execute-button");
    const executeResult = document.getElementById("execute-result");
    window.addEventListener("positions:update", (event) => {
      const positions = event?.detail?.positions;
      maybeMarkExecutionFilledFromPositions(positions);
    });

    executeBtn.addEventListener("click", async () => {
      if (executeSubmitInFlight) return;
      if (isFormActionLocked()) {
        showCard(executeResult);
        executeResult.innerHTML = `<div class="error">Syncing entry fields. Please retry in a moment.</div>`;
        return;
      }
      executeSubmitInFlight = true;
      executeBtn.disabled = true;

      const normalizeTradePayloadBeforeSubmit = getNormalizeTradePayloadBeforeSubmit();
      if (!normalizeTradePayloadBeforeSubmit) {
        showCard(executeResult);
        executeResult.innerHTML = `<div class="error">Trade form normalization unavailable. Refresh and retry.</div>`;
        executeSubmitInFlight = false;
        executeBtn.disabled = false;
        return;
      }
      const normalized = await normalizeTradePayloadBeforeSubmit({ traceId: createTradeTraceId() });
      if (!normalized.ok) {
        if (normalized.tickInvalid) {
          markStopInputInvalid(true);
        }
        showCard(executeResult);
        executeResult.innerHTML = `<div class="error">${normalized.message}</div>`;
        warnUserPopup(normalized.message);
        executeSubmitInFlight = false;
        executeBtn.disabled = false;
        return;
      }
      const payload = normalized.payload;
      const symbol = payload.symbol;
      try {
        const result = await postExecute(payload);
        renderExecute(executeResult, result, { symbol, side: payload.side });
      } catch (err) {
        showCard(executeResult);
        executeResult.innerHTML = `<div class="error">${err.message}</div>`;
        executeUiState.current = null;
      } finally {
        executeSubmitInFlight = false;
        executeBtn.disabled = false;
      }
    });
  });
})();
