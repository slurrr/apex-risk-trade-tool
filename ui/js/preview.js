(function () {
  const API_BASE =
    (window.TradeApp && window.TradeApp.API_BASE) ||
    window.API_BASE ||
    `${window.location.protocol}//${window.location.hostname}:8000`;
  const validateSymbol = (window.TradeApp && window.TradeApp.validateSymbol) || ((val) => val?.toUpperCase());
  const fetchAtrStop = window.TradeApp && window.TradeApp.fetchAtrStop;
  const getAtrTimeframe = window.TradeApp && window.TradeApp.getAtrTimeframe;
  const enforceTradeDirectionConsistency =
    (window.TradeApp && window.TradeApp.enforceTradeDirectionConsistency) || (() => ({ valid: true }));
  const warnUserPopup = (window.TradeApp && window.TradeApp.warnUserPopup) || ((msg) => window.alert(msg));
  const markStopInputInvalid = (window.TradeApp && window.TradeApp.markStopInputInvalid) || (() => {});
  const snapToStep = (window.TradeApp && window.TradeApp.snapToInputStep) || ((value) => value);
  const createTradeTraceId = (window.TradeApp && window.TradeApp.createTradeTraceId) || (() => `trd-${Date.now()}`);
  const ATR_STATUS_DEFAULT = "ATR stop will populate once symbol, side, and entry price are set.";
  let previewSubmitInFlight = false;

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

  const atrState = {
    timer: null,
    token: 0,
    statusEl: null,
    manualOverride: false,
    manualSymbol: null,
    lastAutoPrice: null,
    settingStopValue: false,
    emptyActiveLock: false,
    inFlight: false,
  };
  let formActionLock = false;

  function setFormActionLock(locked) {
    formActionLock = Boolean(locked);
    const calcBtn = document.querySelector('#preview-form button[type="submit"]');
    const executeBtn = document.getElementById("execute-button");
    if (calcBtn) {
      calcBtn.disabled = formActionLock || previewSubmitInFlight;
    }
    if (executeBtn) {
      executeBtn.disabled = formActionLock;
    }
  }

  function refreshFormActionLock() {
    const locked = Boolean(previewSubmitInFlight || atrState.inFlight || atrState.timer);
    setFormActionLock(locked);
  }

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

  function renderResult(container, result, context = {}) {
    showCard(container);
    const side = String(result.side || context.side || "").toUpperCase();
    const sideClass = side === "SELL" ? "sell" : "buy";
    const symbol = context.symbol || result.symbol || "";
    container.innerHTML = `
      <div class="trade-output">
        <div class="trade-output-head">
          <span class="trade-action-pill ${sideClass}">${side || "--"}</span>
          <span class="trade-symbol">${symbol}</span>
        </div>
        <div class="trade-line strong">${formatCompact(result.notional, 2)}</div>
        <div class="trade-line">${formatCompact(result.size)} @ ${formatCompact(result.entry_price)}</div>
        <div class="trade-line dim">SL: ${formatCompact(result.stop_price)} Risk: ${formatCompact(result.estimated_loss, 2)}</div>
        ${renderWarnings(result.warnings)}
      </div>
    `;
  }

  function renderError(container, message) {
    showCard(container);
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
    const timeframeInput = document.getElementById("atr_timeframe");
    const form = document.getElementById("preview-form");
    if (!symbolInput || !entryInput || !sideSelect || !stopInput) {
      return;
    }

    const schedule = () => {
      if (atrState.timer) {
        clearTimeout(atrState.timer);
      }
      atrState.timer = window.setTimeout(() => runAtrAutofill(symbolInput, entryInput, sideSelect, stopInput), 250);
      refreshFormActionLock();
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
    if (timeframeInput) {
      timeframeInput.addEventListener("change", () => {
        // Timeframe changes should re-enable ATR auto-stop even after manual stop edits.
        clearManualOverride();
        atrState.lastAutoPrice = null;
        schedule();
      });
    }
    window.addEventListener("trade:side-stop-mismatch", () => {
      // When user flips side and stop is now invalid for that side,
      // release manual lock and recompute stop from ATR immediately.
      clearManualOverride();
      atrState.lastAutoPrice = null;
      schedule();
    });

    stopInput.addEventListener("input", () => {
      if (atrState.settingStopValue) {
        return;
      }
      const value = (stopInput.value || "").trim();
      const symbol = validateSymbol(symbolInput.value);
      const isActive = document.activeElement === stopInput;
      if (value) {
        atrState.emptyActiveLock = false;
        setManualOverride(symbol);
        setAtrStatus("Manual stop in use. Clear the Stop field to resume ATR suggestions.");
      } else {
        if (isActive) {
          // User is actively editing stop and has cleared the input (e.g. backspace).
          // Keep ATR from repopulating until they leave the field.
          atrState.emptyActiveLock = true;
          setManualOverride(symbol);
          setAtrStatus("Manual stop edit in progress.");
        } else {
          atrState.emptyActiveLock = false;
          clearManualOverride();
          atrState.lastAutoPrice = null;
          setAtrStatus(ATR_STATUS_DEFAULT);
          schedule();
        }
      }
    });
    stopInput.addEventListener("focus", () => {
      const value = (stopInput.value || "").trim();
      if (!value) {
        atrState.emptyActiveLock = true;
      }
    });
    stopInput.addEventListener("blur", () => {
      if (!atrState.emptyActiveLock) return;
      atrState.emptyActiveLock = false;
      const value = (stopInput.value || "").trim();
      if (!value) {
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

  async function runAtrAutofill(symbolInput, entryInput, sideSelect, stopInput, options = {}) {
    const force = Boolean(options.force);
    if (!fetchAtrStop) return;
    if (atrState.timer) {
      clearTimeout(atrState.timer);
      atrState.timer = null;
    }
    atrState.inFlight = true;
    refreshFormActionLock();
    const symbol = validateSymbol(symbolInput.value);
    const side = normalizedSide(sideSelect.value);
    const entry = parseFloat(entryInput.value);
    const timeframe = getAtrTimeframe ? getAtrTimeframe() : null;

    try {
      if (!symbol || !side || !Number.isFinite(entry) || entry <= 0) {
        setAtrStatus("Select a symbol, side, and entry to auto-calc the stop.");
        return;
      }

      if (!force && atrState.emptyActiveLock && document.activeElement === stopInput && !(stopInput.value || "").trim()) {
        setAtrStatus("Manual stop edit in progress.");
        return;
      }

      if (!force && manualOverrideActive(symbol)) {
        setAtrStatus("Manual stop preserved. Clear the Stop field to use ATR suggestions again.");
        return;
      }
      if (atrState.manualOverride && atrState.manualSymbol && atrState.manualSymbol !== symbol) {
        clearManualOverride();
      }

      const token = ++atrState.token;
      setAtrStatus("Calculating ATR stop...");
      const response = await fetchAtrStop(symbol, side, entry, timeframe);
      if (token !== atrState.token) return;
      if (response && typeof response.stop_loss_price === "number" && Number.isFinite(response.stop_loss_price)) {
        const snapped = snapToStep(response.stop_loss_price, stopInput);
        atrState.settingStopValue = true;
        stopInput.value = snapped;
        stopInput.dispatchEvent(new Event("input", { bubbles: true }));
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
        stopInput.dispatchEvent(new Event("input", { bubbles: true }));
        atrState.settingStopValue = false;
        atrState.lastAutoPrice = null;
      }
      setAtrStatus(buildAtrErrorMessage(err), "error");
    } finally {
      atrState.inFlight = false;
      refreshFormActionLock();
    }
  }

  async function normalizeTradePayloadBeforeSubmit(options = {}) {
    const { traceId = null } = options;
    const symbolInput = document.getElementById("symbol-input");
    const entryInput = document.getElementById("entry_price");
    const stopInput = document.getElementById("stop_price");
    const riskInput = document.getElementById("risk_pct");
    const sideInput = document.getElementById("side");
    const tpInput = document.getElementById("tp");

    const symbol = validateSymbol(symbolInput?.value);
    if (!symbol) {
      return { ok: false, message: "Select a valid symbol (e.g., BTC-USDT)." };
    }

    let directionCheck = enforceTradeDirectionConsistency({ autoFlip: false, animate: false });
    if (!directionCheck.valid) {
      if (directionCheck.expectedSide && symbolInput && entryInput && sideInput && stopInput) {
        atrState.emptyActiveLock = false;
        clearManualOverride();
        atrState.lastAutoPrice = null;
        await runAtrAutofill(symbolInput, entryInput, sideInput, stopInput, { force: true });
        await new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
        directionCheck = enforceTradeDirectionConsistency({ autoFlip: false, animate: false });
      }
      if (!directionCheck.valid) {
        return { ok: false, message: directionCheck.reason || "Invalid side/stop configuration." };
      }
    }

    const payload = {
      symbol,
      entry_price: parseFloat(entryInput?.value),
      stop_price: parseFloat(stopInput?.value),
      risk_pct: parseFloat(riskInput?.value),
      side: sideInput?.value || null,
      tp: tpInput?.value ? parseFloat(tpInput.value) : null,
      trace_id: traceId || createTradeTraceId(),
    };

    const tickSize = getActiveTickSize();
    if (
      tickSize &&
      Number.isFinite(payload.entry_price) &&
      Number.isFinite(payload.stop_price) &&
      Math.abs(payload.entry_price - payload.stop_price) < tickSize
    ) {
      const formattedTick = formatTickSize(tickSize) || tickSize;
      return {
        ok: false,
        message: `Entry and stop must differ by at least ${formattedTick}.`,
        tickInvalid: true,
      };
    }

    return { ok: true, payload };
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

    if (!window.TradeApp) {
      window.TradeApp = {};
    }
    window.TradeApp.normalizeTradePayloadBeforeSubmit = normalizeTradePayloadBeforeSubmit;
    window.TradeApp.isFormActionLocked = () => formActionLock;

    if (!form) {
      return;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (previewSubmitInFlight) return;
      previewSubmitInFlight = true;
      const submitter = event.submitter;
      if (submitter) submitter.disabled = true;
      refreshFormActionLock();
      const normalized = await normalizeTradePayloadBeforeSubmit();
      if (!normalized.ok) {
        if (normalized.tickInvalid) {
          markStopInputInvalid(true);
        }
        renderError(resultContainer, normalized.message);
        warnUserPopup(normalized.message);
        previewSubmitInFlight = false;
        refreshFormActionLock();
        return;
      }
      const payload = { ...normalized.payload, preview: true, execute: false };
      const symbol = payload.symbol;

      try {
        const result = await postPreview(payload);
        renderResult(resultContainer, result, { symbol, side: payload.side });
      } catch (err) {
        renderError(resultContainer, err.message);
      } finally {
        previewSubmitInFlight = false;
        refreshFormActionLock();
      }
    });
  });
})();
