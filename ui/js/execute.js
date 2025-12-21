(function () {
  const API_BASE = (window.TradeApp && window.TradeApp.API_BASE) || 
  window.API_BASE || 
  `${window.location.protocol}//${window.location.hostname}:8000`;
  const validateSymbol = (window.TradeApp && window.TradeApp.validateSymbol) || ((val) => val?.toUpperCase());

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

  function renderExecute(container, result) {
    container.innerHTML = `
      <div><strong>Executed:</strong> ${result.executed}</div>
      <div><strong>Exchange Order ID:</strong> ${result.exchange_order_id}</div>
      <div><strong>Side:</strong> ${result.side}</div>
      <div><strong>Size:</strong> ${result.size}</div>
      <div><strong>Notional:</strong> ${result.notional}</div>
      <div><strong>Estimated Loss:</strong> ${result.estimated_loss}</div>
      <div><strong>Warnings:</strong> ${(result.warnings || []).join(", ") || "None"}</div>
    `;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const executeBtn = document.getElementById("execute-button");
    const executeResult = document.getElementById("execute-result");

    executeBtn.addEventListener("click", async () => {
      const symbol = validateSymbol(document.getElementById("symbol-input").value);
      if (!symbol) {
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
      const tickSize = getActiveTickSize();
      if (
        tickSize &&
        Number.isFinite(payload.entry_price) &&
        Number.isFinite(payload.stop_price) &&
        Math.abs(payload.entry_price - payload.stop_price) < tickSize
      ) {
        const formattedTick = formatTickSize(tickSize) || tickSize;
        executeResult.innerHTML = `<div class="error">Entry and stop must differ by at least ${formattedTick}.</div>`;
        return;
      }
      try {
        const result = await postExecute(payload);
        renderExecute(executeResult, result);
      } catch (err) {
        executeResult.innerHTML = `<div class="error">${err.message}</div>`;
      }
    });
  });
})();
