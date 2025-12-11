(function () {
  const API_BASE =
    (window.TradeApp && window.TradeApp.API_BASE) ||
    window.API_BASE ||
    `${window.location.protocol}//${window.location.hostname}:8000`;
  const validateSymbol = (window.TradeApp && window.TradeApp.validateSymbol) || ((val) => val?.toUpperCase());
  const fetchAtrStop = window.TradeApp && window.TradeApp.fetchAtrStop;
  const snapToStep = (window.TradeApp && window.TradeApp.snapToInputStep) || ((value) => value);
  const ATR_STATUS_DEFAULT = "ATR stop will populate once symbol, side, and entry price are set.";

  const atrState = {
    timer: null,
    token: 0,
    statusEl: null,
    manualOverride: false,
    manualSymbol: null,
    lastAutoPrice: null,
    settingStopValue: false,
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
    el.textContent = message || ATR_STATUS_DEFAULT;
    el.classList.remove("is-error", "is-success");
    if (mode === "error") {
      el.classList.add("is-error");
    } else if (mode === "success") {
      el.classList.add("is-success");
    }
  }

  function setManualOverride(symbol) {
    atrState.manualOverride = true;
    atrState.manualSymbol = symbol || null;
    atrState.lastAutoPrice = null;
  }

  function clearManualOverride() {
    atrState.manualOverride = false;
    atrState.manualSymbol = null;
  }

  function manualOverrideActive(symbol) {
    if (!symbol) return false;
    return atrState.manualOverride && atrState.manualSymbol === symbol;
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
    const form = document.getElementById("preview-form");
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
    symbolInput.addEventListener("change", () => {
      schedule();
      const currentSymbol = validateSymbol(symbolInput.value);
      if (atrState.manualOverride && atrState.manualSymbol && atrState.manualSymbol !== currentSymbol) {
        clearManualOverride();
        atrState.lastAutoPrice = null;
        setAtrStatus(ATR_STATUS_DEFAULT);
      }
    });
    entryInput.addEventListener("input", schedule);
    sideSelect.addEventListener("change", schedule);

    stopInput.addEventListener("input", () => {
      if (atrState.settingStopValue) {
        return;
      }
      const value = (stopInput.value || "").trim();
      const symbol = validateSymbol(symbolInput.value);
      if (value) {
        setManualOverride(symbol);
        setAtrStatus("Manual stop in use. Clear the Stop field to resume ATR suggestions.");
      } else {
        clearManualOverride();
        atrState.lastAutoPrice = null;
        setAtrStatus(ATR_STATUS_DEFAULT);
        schedule();
      }
    });

    const clearBtn = document.getElementById("clear-trade-form");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        clearManualOverride();
        atrState.lastAutoPrice = null;
        setAtrStatus(ATR_STATUS_DEFAULT);
        if (stopInput) {
          atrState.settingStopValue = true;
          stopInput.value = "";
          atrState.settingStopValue = false;
        }
        symbolInput.dispatchEvent(new Event("input", { bubbles: true }));
      });
    }
    if (form) {
      form.addEventListener("reset", () => {
        clearManualOverride();
        atrState.lastAutoPrice = null;
        setAtrStatus(ATR_STATUS_DEFAULT);
        window.setTimeout(schedule, 0);
      });
    }
    setAtrStatus(ATR_STATUS_DEFAULT);
    schedule();
  }

  async function runAtrAutofill(symbolInput, entryInput, sideSelect, stopInput) {
    if (!fetchAtrStop) return;
    const symbol = validateSymbol(symbolInput.value);
    const side = normalizedSide(sideSelect.value);
    const entry = parseFloat(entryInput.value);

    if (!symbol || !side || !Number.isFinite(entry) || entry <= 0) {
      setAtrStatus("Select a symbol, side, and entry price to auto-calc the stop.");
      return;
    }

    if (manualOverrideActive(symbol)) {
      setAtrStatus("Manual stop preserved. Clear the Stop field to use ATR suggestions again.");
      return;
    }
    if (atrState.manualOverride && atrState.manualSymbol && atrState.manualSymbol !== symbol) {
      clearManualOverride();
    }

    const token = ++atrState.token;
    setAtrStatus("Calculating ATR stop...");
    try {
      const response = await fetchAtrStop(symbol, side, entry);
      if (token !== atrState.token) return;
      if (response && typeof response.stop_loss_price === "number" && Number.isFinite(response.stop_loss_price)) {
        const snapped = snapToStep(response.stop_loss_price, stopInput);
        atrState.settingStopValue = true;
        stopInput.value = snapped;
        atrState.settingStopValue = false;
        atrState.lastAutoPrice = typeof snapped === "string" ? parseFloat(snapped) : snapped;
      }
      clearManualOverride();
      const label = response
        ? `Auto stop (${response.timeframe || symbol} x${response.multiplier})`
        : "ATR stop ready.";
      setAtrStatus(label, "success");
    } catch (err) {
      if (token !== atrState.token) return;
      if (!manualOverrideActive(symbol)) {
        atrState.settingStopValue = true;
        stopInput.value = "";
        atrState.settingStopValue = false;
        atrState.lastAutoPrice = null;
      }
      setAtrStatus(buildAtrErrorMessage(err), "error");
    }
  }

  function buildAtrErrorMessage(err) {
    if (!err) {
      return "ATR stop unavailable. Enter a stop price manually.";
    }
    switch (err.code) {
      case "atr_insufficient_history":
        return "ATR data needs more candles. Enter a stop manually while history loads.";
      case "atr_history_unavailable":
      case "atr_data_unavailable":
        return "Market data unavailable for ATR. Please enter a stop price manually.";
      case "atr_unavailable":
        return err.message || "ATR calculation unavailable. Enter a stop manually.";
      default:
        return err.message || "ATR stop unavailable. Enter a stop price manually.";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("preview-form");
    const resultContainer = document.getElementById("preview-result");
    setupAtrAutofill();

    if (!form) {
      return;
    }

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
