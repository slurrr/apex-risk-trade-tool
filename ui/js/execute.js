(function () {
  const API_BASE = (window.TradeApp && window.TradeApp.API_BASE) || 
  window.API_BASE || 
  `${window.location.protocol}//${window.location.hostname}:8000`;
  const validateSymbol = (window.TradeApp && window.TradeApp.validateSymbol) || ((val) => val?.toUpperCase());
  const enforceTradeDirectionConsistency =
    (window.TradeApp && window.TradeApp.enforceTradeDirectionConsistency) || (() => ({ valid: true }));
  const warnUserPopup = (window.TradeApp && window.TradeApp.warnUserPopup) || ((msg) => window.alert(msg));
  const markStopInputInvalid = (window.TradeApp && window.TradeApp.markStopInputInvalid) || (() => {});

  function getActiveTickSize() {
    const tick = window.TradeApp && window.TradeApp.state && window.TradeApp.state.activeTickSize;
    return typeof tick === "number" && tick > 0 ? tick : null;
  }

  function formatTickSize(tick) {
    if (!Number.isFinite(tick)) return "";
    const decimals =
      window.TradeApp && window.TradeApp.state && typeof window.TradeApp.state.activePriceDecimals === "number"
        ? window.TradeApp.state.activePriceDecimals
        : null;
    if (typeof decimals === "number" && decimals >= 0) {
      return Number(tick).toFixed(Math.min(decimals, 10));
    }
    return `${tick}`;
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

  function renderExecute(container, result, context = {}) {
    showCard(container);
    const side = String(result.side || context.side || "").toUpperCase();
    const sideClass = side === "SELL" ? "sell" : "buy";
    const symbol = context.symbol || result.symbol || "";
    const displaySymbol = symbol.includes("-") ? symbol.split("-")[0] : symbol;
    container.innerHTML = `
      <div class="trade-output">
        <div class="trade-output-head">
          <span class="trade-action-pill ${sideClass}">${side || "--"}</span>
        </div>
        <div class="trade-line strong">Order to ${side || "--"} ${formatCompact(result.size)} ${displaySymbol} Submitted</div>
        <div class="trade-line dim">Order ID: ${result.exchange_order_id || "--"}</div>
        ${renderWarnings(result.warnings)}
      </div>
    `;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const executeBtn = document.getElementById("execute-button");
    const executeResult = document.getElementById("execute-result");

    executeBtn.addEventListener("click", async () => {
      const symbol = validateSymbol(document.getElementById("symbol-input").value);
      if (!symbol) {
        showCard(executeResult);
        executeResult.innerHTML = `<div class="error">Select a valid symbol (e.g., BTC-USDT).</div>`;
        return;
      }
      const payload = {
        symbol,
        entry_price: parseFloat(document.getElementById("entry_price").value),
        stop_price: parseFloat(document.getElementById("stop_price").value),
        risk_pct: parseFloat(document.getElementById("risk_pct").value),
        side: document.getElementById("side").value || null,
        tp: document.getElementById("tp").value ? parseFloat(document.getElementById("tp").value) : null,
      };
      const directionCheck = enforceTradeDirectionConsistency({ autoFlip: true, animate: true });
      if (!directionCheck.valid) {
        const message = directionCheck.reason || "Invalid side/stop configuration.";
        showCard(executeResult);
        executeResult.innerHTML = `<div class="error">${message}</div>`;
        warnUserPopup(message);
        return;
      }
      if (directionCheck.corrected) {
        payload.side = document.getElementById("side").value || null;
      }
      const tickSize = getActiveTickSize();
      if (
        tickSize &&
        Number.isFinite(payload.entry_price) &&
        Number.isFinite(payload.stop_price) &&
        Math.abs(payload.entry_price - payload.stop_price) < tickSize
      ) {
        const formattedTick = formatTickSize(tickSize) || tickSize;
        const message = `Entry and stop must differ by at least ${formattedTick}.`;
        markStopInputInvalid(true);
        showCard(executeResult);
        executeResult.innerHTML = `<div class="error">${message}</div>`;
        warnUserPopup(message);
        return;
      }
      try {
        const result = await postExecute(payload);
        renderExecute(executeResult, result, { symbol, side: payload.side });
      } catch (err) {
        showCard(executeResult);
        executeResult.innerHTML = `<div class="error">${err.message}</div>`;
      }
    });
  });
})();
