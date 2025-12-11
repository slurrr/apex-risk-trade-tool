(function () {
  const API_BASE =
    (window.TradeApp && window.TradeApp.API_BASE) ||
    window.API_BASE ||
    `${window.location.protocol}//${window.location.hostname}:8000`;
  const validateSymbol = (window.TradeApp && window.TradeApp.validateSymbol) || ((val) => val?.toUpperCase());
  const fetchAtrStop = window.TradeApp && window.TradeApp.fetchAtrStop;
  const atrState = {
    timer: null,
    token: 0,
    statusEl: null,
  };

  async function postPreview(payload) {
    const response = await fetch(`${API_BASE}/api/trade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      const msg = data?.detail || "Preview request failed";
      throw new Error(msg);
    }
    return data;
  }

  function renderResult(container, result) {
    container.innerHTML = `
      <div><strong>Side:</strong> ${result.side}</div>
      <div><strong>Size:</strong> ${result.size}</div>
      <div><strong>Notional:</strong> ${result.notional}</div>
      <div><strong>Estimated Loss:</strong> ${result.estimated_loss}</div>
      <div><strong>Entry:</strong> ${result.entry_price}</div>
      <div><strong>Stop:</strong> ${result.stop_price}</div>
      <div><strong>Warnings:</strong> ${(result.warnings || []).join(", ") || "None"}</div>
    `;
  }

  function renderError(container, message) {
    container.innerHTML = `<div class="error">${message}</div>`;
  }

  function ensureAtrStatusElement(stopInput) {
    if (atrState.statusEl && atrState.statusEl.isConnected) {
      return atrState.statusEl;
    }
    if (!stopInput || !stopInput.parentElement) {
      return null;
    }
    const hint = document.createElement("div");
    hint.id = "atr-stop-status";
    hint.className = "atr-stop-status";
    stopInput.parentElement.appendChild(hint);
    atrState.statusEl = hint;
    return hint;
  }

  function setAtrStatus(message, mode = "info") {
    const stopInput = document.getElementById("stop_price");
    const el = ensureAtrStatusElement(stopInput);
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("is-error", "is-success");
    if (mode === "error") {
      el.classList.add("is-error");
    } else if (mode === "success") {
      el.classList.add("is-success");
    }
  }

  function normalizedSide(value) {
    if (!value) return null;
    const raw = value.toString().trim().toUpperCase();
    if (raw === "BUY" || raw === "LONG") return "long";
    if (raw === "SELL" || raw === "SHORT") return "short";
    return null;
  }

  function setupAtrAutofill() {
    if (!fetchAtrStop) return;
    const symbolInput = document.getElementById("symbol-input");
    const entryInput = document.getElementById("entry_price");
    const sideSelect = document.getElementById("side");
    const stopInput = document.getElementById("stop_price");
    if (!symbolInput || !entryInput || !sideSelect || !stopInput) {
      return;
    }

    const schedule = () => {
      if (atrState.timer) {
        clearTimeout(atrState.timer);
      }
      atrState.timer = window.setTimeout(() => runAtrAutofill(symbolInput, entryInput, sideSelect, stopInput), 250);
    };

    symbolInput.addEventListener("input", schedule);
    symbolInput.addEventListener("change", schedule);
    entryInput.addEventListener("input", schedule);
    sideSelect.addEventListener("change", schedule);

    const clearBtn = document.getElementById("clear-trade-form");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        setAtrStatus("");
        symbolInput.dispatchEvent(new Event("input", { bubbles: true }));
      });
    }
    setAtrStatus("ATR stop will populate once symbol, side, and entry are set.");
    schedule();
  }

  async function runAtrAutofill(symbolInput, entryInput, sideSelect, stopInput) {
    if (!fetchAtrStop) return;
    const symbol = validateSymbol(symbolInput.value);
    const side = normalizedSide(sideSelect.value);
    const entry = parseFloat(entryInput.value);

    if (!symbol || !side || !Number.isFinite(entry) || entry <= 0) {
      setAtrStatus("Select a symbol, side, and entry price to auto-calc stop.");
      return;
    }

    const token = ++atrState.token;
    setAtrStatus("Calculating ATR stop…");
    try {
      const response = await fetchAtrStop(symbol, side, entry);
      if (token !== atrState.token) return;
      if (response && typeof response.stop_loss_price === "number" && Number.isFinite(response.stop_loss_price)) {
        stopInput.value = response.stop_loss_price;
        stopInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
      const label = response ? `Auto stop (${response.timeframe} · x${response.multiplier})` : "ATR stop ready.";
      setAtrStatus(label, "success");
    } catch (err) {
      if (token !== atrState.token) return;
      setAtrStatus(err?.message || "ATR stop unavailable.", "error");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("preview-form");
    const resultContainer = document.getElementById("preview-result");
    setupAtrAutofill();

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const symbol = validateSymbol(document.getElementById("symbol-input").value);
      if (!symbol) {
        renderError(resultContainer, "Select a valid symbol (e.g., BTC-USDT).");
        return;
      }
      const payload = {
        symbol,
        entry_price: parseFloat(document.getElementById("entry_price").value),
        stop_price: parseFloat(document.getElementById("stop_price").value),
        risk_pct: parseFloat(document.getElementById("risk_pct").value),
        side: document.getElementById("side").value || null,
        tp: document.getElementById("tp").value ? parseFloat(document.getElementById("tp").value) : null,
        preview: true,
        execute: false,
      };

      try {
        const result = await postPreview(payload);
        renderResult(resultContainer, result);
      } catch (err) {
        renderError(resultContainer, err.message);
      }
    });
  });
})();
