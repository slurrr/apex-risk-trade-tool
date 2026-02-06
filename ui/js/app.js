(function () {
  const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000`;
  const SYMBOL_PATTERN = /^[A-Z0-9]+-[A-Z0-9]+$/;
  const DEFAULT_PRICE_DECIMALS = 6;
  const PRICE_INPUT_IDS = ["entry_price", "stop_price", "tp"];
  const THEME_STORAGE_KEY = "trade_app_theme";
  const ATR_TIMEFRAME_STORAGE_KEY = "atr_timeframe_override";
  const ATR_TIMEFRAME_DEFAULT = "15m";
  const ATR_TIMEFRAMES = ["3m", "15m", "1h", "4h"];
  const DEV_STREAM_HEALTH_STORAGE_KEY = "dev_stream_health";
  const STREAM_HEALTH_POLL_INTERVAL_MS = 15000;
  let manualTheme = null;
  let mediaQuery;
  let streamHealthTimerId = null;
  const state = {
    symbols: [],
    symbolIndex: new Map(),
    priceCache: new Map(),
    activeSymbol: null,
    activeTickSize: null,
    activePriceDecimals: DEFAULT_PRICE_DECIMALS,
    lastAccountUpdate: 0,
  };
  let sideToggleControl = null;

  function normalizeSymbolCode(value) {
    const clean = (value || "").trim().toUpperCase();
    if (SYMBOL_PATTERN.test(clean)) {
      return clean;
    }
    return null;
  }

  function getPriceInputs() {
    return PRICE_INPUT_IDS.map((id) => document.getElementById(id)).filter(Boolean);
  }

  function setInputPrecision(input, { step, decimals }) {
    if (!input) return;
    if (!step || step === "any") {
      input.setAttribute("step", "any");
    } else {
      input.setAttribute("step", `${step}`);
    }
    if (input.dataset) {
      if (typeof decimals === "number" && decimals >= 0) {
        input.dataset.precision = String(decimals);
      } else {
        delete input.dataset.precision;
      }
    }
  }

  function setPriceInputsPrecision(options = {}) {
    const priceInputs = getPriceInputs();
    priceInputs.forEach((input) => setInputPrecision(input, options));
  }

  function getSymbolMeta(symbolCode) {
    if (!symbolCode) return null;
    const key = normalizeSymbolCode(symbolCode);
    if (!key) return null;
    return state.symbolIndex.get(key) || null;
  }

  function formatStepValue(step, decimals) {
    const numeric = Number(step);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return null;
    }
    if (typeof decimals === "number" && decimals >= 0) {
      return numeric.toFixed(Math.min(decimals, 10));
    }
    return `${numeric}`;
  }

  function applySymbolPrecision(symbolCode) {
    const normalized = normalizeSymbolCode(symbolCode);
    const meta = normalized ? getSymbolMeta(normalized) : null;
    state.activeSymbol = normalized || null;
    state.activeTickSize = meta && typeof meta.tick_size === "number" ? meta.tick_size : null;
    const decimals =
      typeof meta?.price_decimals === "number" && meta.price_decimals >= 0
        ? meta.price_decimals
        : DEFAULT_PRICE_DECIMALS;
    state.activePriceDecimals = decimals;
    const stepValue = formatStepValue(meta?.tick_size, decimals) || "any";
    setPriceInputsPrecision({ step: stepValue, decimals });
  }

  function getStoredTheme() {
    try {
      return window.localStorage ? window.localStorage.getItem(THEME_STORAGE_KEY) : null;
    } catch (err) {
      return null;
    }
  }

  function persistTheme(theme) {
    try {
      if (window.localStorage) {
        if (theme) {
          window.localStorage.setItem(THEME_STORAGE_KEY, theme);
        } else {
          window.localStorage.removeItem(THEME_STORAGE_KEY);
        }
      }
    } catch (err) {
      // ignore storage errors
    }
  }

  function applyTheme(theme, options = {}) {
    document.documentElement.setAttribute("data-theme", theme);
    const toggleBtn = document.getElementById("theme-toggle");
    if (toggleBtn) {
      const isDark = theme === "dark";
      toggleBtn.dataset.icon = isDark ? "☾" : "☼";
      toggleBtn.dataset.theme = theme;
    }
    if (options.persist) {
      persistTheme(theme);
    }
  }

  function initThemeListener() {
    mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const stored = getStoredTheme();
    if (stored) {
      manualTheme = stored;
      applyTheme(stored);
    } else {
      applyTheme(mediaQuery.matches ? "dark" : "light");
    }
    const handleMediaChange = () => {
      if (!manualTheme) {
        applyTheme(mediaQuery.matches ? "dark" : "light");
      }
    };
    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleMediaChange);
    } else if (typeof mediaQuery.addListener === "function") {
      mediaQuery.addListener(handleMediaChange);
    }
    const toggleBtn = document.getElementById("theme-toggle");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme") || (mediaQuery.matches ? "dark" : "light");
        const next = current === "dark" ? "light" : "dark";
        manualTheme = next;
        applyTheme(next, { persist: true });
      });
    }
  }

  function normalizeAtrTimeframe(value) {
    const clean = (value || "").toString().trim().toLowerCase();
    return ATR_TIMEFRAMES.includes(clean) ? clean : null;
  }

  function getStoredAtrTimeframe() {
    try {
      return window.localStorage ? window.localStorage.getItem(ATR_TIMEFRAME_STORAGE_KEY) : null;
    } catch (err) {
      return null;
    }
  }

  function persistAtrTimeframe(timeframe) {
    try {
      if (window.localStorage) {
        if (timeframe) {
          window.localStorage.setItem(ATR_TIMEFRAME_STORAGE_KEY, timeframe);
        } else {
          window.localStorage.removeItem(ATR_TIMEFRAME_STORAGE_KEY);
        }
      }
    } catch (err) {
      // ignore storage errors
    }
  }

  function getAtrTimeframeInput() {
    return document.getElementById("atr_timeframe");
  }

  function applyAtrTimeframeSelection(value, options = {}) {
    const { persist = false, silent = false } = options;
    const normalized = normalizeAtrTimeframe(value) || ATR_TIMEFRAME_DEFAULT;
    const input = getAtrTimeframeInput();
    const buttons = Array.from(document.querySelectorAll(".atr-timeframe-option"));
    if (input) {
      const changed = input.value !== normalized;
      input.value = normalized;
      if (!silent && changed) {
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
    buttons.forEach((btn) => {
      const btnValue = normalizeAtrTimeframe(btn.dataset.value);
      const isActive = btnValue === normalized;
      btn.classList.toggle("is-active", isActive);
      btn.setAttribute("aria-pressed", String(isActive));
    });
    if (persist) {
      persistAtrTimeframe(normalized);
    }
    return normalized;
  }

  function getAtrTimeframe() {
    const input = getAtrTimeframeInput();
    const fromInput = input ? normalizeAtrTimeframe(input.value) : null;
    if (fromInput) return fromInput;
    const stored = normalizeAtrTimeframe(getStoredAtrTimeframe());
    return stored || ATR_TIMEFRAME_DEFAULT;
  }

  function initAtrTimeframeSelector() {
    const input = getAtrTimeframeInput();
    const buttons = Array.from(document.querySelectorAll(".atr-timeframe-option"));
    if (!input || buttons.length === 0) return;
    const stored = normalizeAtrTimeframe(getStoredAtrTimeframe());
    const initial = stored || normalizeAtrTimeframe(input.value) || ATR_TIMEFRAME_DEFAULT;
    applyAtrTimeframeSelection(initial, { persist: true, silent: true });
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        applyAtrTimeframeSelection(btn.dataset.value, { persist: true });
      });
    });
  }

  async function fetchJson(url) {
    const resp = await fetch(url);
    const data = await resp.json();
    if (!resp.ok) {
      const msg = data?.detail || "Request failed";
      throw new Error(msg);
    }
    return data;
  }

  function getPrecisionFromInput(input) {
    if (!input || !input.dataset) return null;
    const hint = Number(input.dataset.precision);
    return Number.isFinite(hint) ? hint : null;
  }

  function decimalsFromStepString(stepStr) {
    if (!stepStr || stepStr.toLowerCase() === "any") return null;
    const parts = stepStr.split(".");
    if (parts.length === 2) {
      return parts[1].replace(/0+$/, "").length;
    }
    return null;
  }

  function snapToInputStep(value, input) {
    if (!input) return value;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return numeric;
    const stepAttr = (input.getAttribute("step") || "").toLowerCase();
    const precisionHint = getPrecisionFromInput(input);
    if (stepAttr && stepAttr !== "any") {
      const step = Number(stepAttr);
      if (Number.isFinite(step) && step > 0) {
        const snapped = Math.round(numeric / step) * step;
        if (!Number.isFinite(snapped)) {
          return numeric;
        }
        const decimals = precisionHint ?? decimalsFromStepString(stepAttr);
        if (typeof decimals === "number" && decimals >= 0) {
          return snapped.toFixed(decimals);
        }
        return snapped;
      }
    }
    if (typeof precisionHint === "number" && precisionHint >= 0) {
      return numeric.toFixed(precisionHint);
    }
    return numeric;
  }

  async function fetchAtrStop(symbol, side, entryPrice, timeframe) {
    const cleanSymbol = (symbol || "").trim().toUpperCase();
    const numericEntry = Number(entryPrice);
    if (!cleanSymbol || !side) {
      throw new Error("Symbol and side are required");
    }
    if (!Number.isFinite(numericEntry) || numericEntry <= 0) {
      throw new Error("Entry price must be greater than zero");
    }
    const payload = {
      symbol: cleanSymbol,
      side,
      entry_price: numericEntry,
    };
    const normalizedTimeframe = normalizeAtrTimeframe(timeframe);
    if (normalizedTimeframe) {
      payload.timeframe = normalizedTimeframe;
    }
    const resp = await fetch(`${API_BASE}/risk/atr-stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      const msg = data?.detail || "Unable to fetch ATR stop";
      const err = new Error(msg);
      err.code = data?.error;
      err.context = data?.context;
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  function renderAccountSummary(summary) {
    const equityEl = document.getElementById("summary-equity");
    const upnlEl = document.getElementById("summary-upnl");
    const marginEl = document.getElementById("summary-margin");
    if (!summary) return;
    const format = (val) => (typeof val === "number" ? val.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "--");
    equityEl.textContent = format(summary.total_equity);
    upnlEl.textContent = format(summary.total_upnl);
    marginEl.textContent = format(summary.available_margin);
    upnlEl.classList.remove("positive", "negative");
    if (typeof summary.total_upnl === "number") {
      if (summary.total_upnl > 0) upnlEl.classList.add("positive");
      if (summary.total_upnl < 0) upnlEl.classList.add("negative");
    }
  }

  function coerceNumber(value) {
    if (value === null || value === undefined) return null;
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  function normalizeAccountPayload(payload) {
    if (!payload || typeof payload !== "object") return null;
    const totalEquity =
      coerceNumber(payload.total_equity) ||
      coerceNumber(payload.totalEquity) ||
      coerceNumber(payload.totalEquityValue) ||
      coerceNumber(payload.totalEquityUsd) ||
      coerceNumber(payload.totalEquityUSDT);
    const available =
      coerceNumber(payload.available_margin) ||
      coerceNumber(payload.availableBalance) ||
      coerceNumber(payload.available) ||
      coerceNumber(payload.availableEquity);
    const totalUpnl =
      coerceNumber(payload.total_upnl) ||
      coerceNumber(payload.totalUnrealizedPnl) ||
      coerceNumber(payload.totalUnrealizedPnlUsd) ||
      coerceNumber(payload.totalUpnl);
    if (totalEquity === null && available === null && totalUpnl === null) {
      return null;
    }
    return {
      total_equity: totalEquity ?? 0,
      available_margin: available ?? 0,
      total_upnl: totalUpnl ?? 0,
    };
  }

  function applyAccountPayload(payload) {
    const summary = normalizeAccountPayload(payload);
    if (summary) {
      renderAccountSummary(summary);
      state.lastAccountUpdate = Date.now();
    }
  }

  async function loadAccountSummary() {
    try {
      const data = await fetchJson(`${API_BASE}/api/account/summary`);
      renderAccountSummary(data);
      state.lastAccountUpdate = Date.now();
    } catch (err) {
      // silent fail for header; avoid blocking UI
      const upnlEl = document.getElementById("summary-upnl");
      if (upnlEl) upnlEl.textContent = "--";
    }
  }

  function startAccountSummaryHeartbeat() {
    window.setInterval(() => {
      const staleMs = 20000;
      const last = state.lastAccountUpdate || 0;
      if (!last || Date.now() - last > staleMs) {
        loadAccountSummary();
      }
    }, 10000);
  }

  function isDevStreamHealthEnabled() {
    try {
      if (!window.localStorage) return false;
      return window.localStorage.getItem(DEV_STREAM_HEALTH_STORAGE_KEY) === "1";
    } catch (err) {
      return false;
    }
  }

  function setTextContent(id, value) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = value;
    }
  }

  function formatSeconds(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    return `${num.toFixed(1)}s`;
  }

  function renderStreamHealth(payload) {
    if (!payload || typeof payload !== "object") return;
    setTextContent("stream-health-venue", `${payload.venue || "--"}`);
    setTextContent("stream-health-ws-alive", payload.ws_alive ? "YES" : "NO");
    setTextContent("stream-health-ws-age", formatSeconds(payload.last_private_ws_event_age_seconds));
    setTextContent("stream-health-reconcile-count", `${payload.reconcile_count ?? "--"}`);
    setTextContent("stream-health-reconcile-reason", `${payload.last_reconcile_reason || "--"}`);
    setTextContent("stream-health-pending", `${payload.pending_submitted_orders ?? "--"}`);
    setTextContent("stream-health-raw", JSON.stringify(payload, null, 2));
  }

  async function loadStreamHealth() {
    try {
      const payload = await fetchJson(`${API_BASE}/api/stream/health`);
      renderStreamHealth(payload);
      setTextContent("stream-health-status", `Updated ${new Date().toLocaleTimeString()}`);
    } catch (err) {
      const message = err?.message || "Request failed";
      setTextContent("stream-health-status", `Failed: ${message}`);
    }
  }

  function initStreamHealthDiagnostics() {
    const panel = document.getElementById("stream-health-panel");
    if (!panel) return;
    if (!isDevStreamHealthEnabled()) {
      panel.classList.add("hidden");
      return;
    }
    panel.classList.remove("hidden");
    const refreshBtn = document.getElementById("stream-health-refresh");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        loadStreamHealth();
      });
    }
    if (streamHealthTimerId) {
      window.clearInterval(streamHealthTimerId);
    }
    loadStreamHealth();
    streamHealthTimerId = window.setInterval(loadStreamHealth, STREAM_HEALTH_POLL_INTERVAL_MS);
  }

  async function loadSymbols() {
    try {
      const data = await fetchJson(`${API_BASE}/api/symbols`);
      const list = Array.isArray(data) ? data : [];
      state.symbols = list;
      state.symbolIndex = new Map();
      list.forEach((sym) => {
        if (sym?.code) {
          state.symbolIndex.set(sym.code.toUpperCase(), sym);
        }
      });
      const input = document.getElementById("symbol-input");
      const currentSymbol = normalizeSymbolCode(input ? input.value : state.activeSymbol);
      if (currentSymbol && state.symbolIndex.has(currentSymbol)) {
        applySymbolPrecision(currentSymbol);
      } else {
        applySymbolPrecision(null);
      }
    } catch (err) {
      state.symbols = [];
      state.symbolIndex = new Map();
      if (!state.activeSymbol) {
        applySymbolPrecision(null);
      }
    }
  }

  const symbolDropdownState = {
    suppressOpen: false,
  };

  function renderSymbolOptions(filter) {
    const list = document.getElementById("symbol-options");
    const input = document.getElementById("symbol-input");
    if (!list || !input) return;
    const query = (filter || input.value || "").toUpperCase();
    const matches = state.symbols.filter((sym) => sym.code.toUpperCase().includes(query));
    list.innerHTML = "";
    matches.slice(0, 30).forEach((sym) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = sym.code;
      btn.addEventListener("click", () => {
        symbolDropdownState.suppressOpen = true;
        input.value = sym.code;
        list.classList.remove("open");
        applySymbolPrecision(sym.code);
        prefillEntryPrice(sym.code);
        updateSymbolClearState();
        input.dispatchEvent(new Event("input", { bubbles: true }));
        window.setTimeout(() => {
          symbolDropdownState.suppressOpen = false;
        }, 0);
      });
      list.appendChild(btn);
    });
    const shouldOpen = document.activeElement === input && matches.length > 0 && !symbolDropdownState.suppressOpen;
    if (shouldOpen) {
      list.classList.add("open");
    } else {
      list.classList.remove("open");
    }
  }

  function updateSymbolClearState() {
    const input = document.getElementById("symbol-input");
    const clearBtn = document.getElementById("symbol-clear");
    if (!input || !clearBtn) return;
    const hasValue = Boolean((input.value || "").trim());
    const isFocused = document.activeElement === input;
    clearBtn.classList.toggle("hidden", !(hasValue || isFocused));
  }

  function attachSymbolDropdown() {
    const input = document.getElementById("symbol-input");
    const list = document.getElementById("symbol-options");
    const clearBtn = document.getElementById("symbol-clear");
    const clearFormBtn = document.getElementById("clear-trade-form");
    const form = document.getElementById("preview-form");
    if (!input || !list) return;
    const syncPrecision = () => {
      const symbol = normalizeSymbolCode(input.value);
      if (symbol && state.symbolIndex.has(symbol)) {
        applySymbolPrecision(symbol);
      } else if (!symbol) {
        applySymbolPrecision(null);
      }
    };
    input.addEventListener("input", () => {
      renderSymbolOptions(input.value);
      updateSymbolClearState();
    });
    input.addEventListener("focus", () => {
      renderSymbolOptions(input.value);
      updateSymbolClearState();
    });
    input.addEventListener("change", syncPrecision);
    input.addEventListener("blur", () => {
      setTimeout(() => {
        updateSymbolClearState();
        syncPrecision();
      }, 0);
    });
    document.addEventListener("click", (evt) => {
      if (!list.contains(evt.target) && evt.target !== input && evt.target !== clearBtn) {
        list.classList.remove("open");
      }
    });
    if (clearBtn) {
      clearBtn.addEventListener("click", (evt) => {
        evt.preventDefault();
        input.value = "";
        input.focus();
        renderSymbolOptions("");
        updateSymbolClearState();
        applySymbolPrecision(null);
      });
    }
    if (clearFormBtn) {
      clearFormBtn.addEventListener("click", () => {
        if (form) {
          form.reset();
        }
        input.value = "";
        renderSymbolOptions("");
        resetSideValue();
        updateSymbolClearState();
        document.getElementById("preview-result").innerHTML = "";
        document.getElementById("execute-result").innerHTML = "";
        applySymbolPrecision(null);
      });
    }
    if (form) {
      form.addEventListener("reset", () => {
        window.setTimeout(() => {
          resetSideValue();
          applySymbolPrecision(null);
        }, 0);
      });
    }
  }

  function initSideToggle() {
    const wrapper = document.querySelector(".side-toggle");
    const hiddenInput = document.getElementById("side");
    if (!wrapper || !hiddenInput) return;
    const buttons = Array.from(wrapper.querySelectorAll(".side-option"));
    if (!buttons.length) return;
    const normalize = (val) => (val || "").toString().trim().toUpperCase();
    const defaultValue = normalize(hiddenInput.getAttribute("value") || buttons[0]?.dataset.value || "");

    const applyState = (nextValue, { silent = false, force = false } = {}) => {
      const normalized = normalize(nextValue || defaultValue);
      const changed = hiddenInput.value !== normalized;
      hiddenInput.value = normalized;
      buttons.forEach((btn) => {
        const btnValue = normalize(btn.dataset.value);
        const isActive = btnValue === normalized;
        btn.classList.toggle("is-active", isActive);
        btn.setAttribute("aria-pressed", String(isActive));
      });
      if (!silent && (changed || force)) {
        hiddenInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
    };

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => applyState(btn.dataset.value));
    });

    applyState(hiddenInput.value || defaultValue, { silent: true, force: true });

    sideToggleControl = {
      set(value, options = {}) {
        applyState(value, options);
      },
      reset() {
        applyState(defaultValue, { force: true });
      },
    };
  }

  function setSideValue(value, options) {
    if (sideToggleControl && typeof sideToggleControl.set === "function") {
      sideToggleControl.set(value, options);
    } else {
      const sideInput = document.getElementById("side");
      if (sideInput) {
        sideInput.value = (value || "").toString().trim().toUpperCase();
      }
    }
  }

  function resetSideValue() {
    if (sideToggleControl && typeof sideToggleControl.reset === "function") {
      sideToggleControl.reset();
    } else {
      const sideInput = document.getElementById("side");
      if (sideInput) {
        sideInput.value = sideInput.getAttribute("value") || "";
      }
    }
  }

  function validateSymbol(value) {
    return normalizeSymbolCode(value);
  }

  function formatNumber(value, digits = 2) {
    if (value === null || value === undefined || value === "") return "";
    const num = Number(value);
    if (Number.isNaN(num)) return value;
    return num.toFixed(digits);
  }

  async function fetchSymbolPrice(symbol) {
    if (!symbol) return null;
    const key = symbol.toUpperCase();
    const cached = state.priceCache.get(key);
    const now = Date.now();
    if (cached && now - cached.ts < 10000) {
      return cached.price;
    }
    try {
      const resp = await fetch(`${API_BASE}/api/price/${encodeURIComponent(key)}`);
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data?.detail || "Unable to fetch price");
      }
      const price = typeof data?.price === "number" ? data.price : Number(data?.price || 0);
      if (!Number.isFinite(price)) {
        throw new Error("Price unavailable");
      }
      state.priceCache.set(key, { price, ts: now });
      return price;
    } catch (err) {
      return null;
    }
  }

  async function prefillEntryPrice(symbol) {
    const entryInput = document.getElementById("entry_price");
    if (!entryInput || !symbol) return;
    const normalized = normalizeSymbolCode(symbol);
    if (normalized) {
      applySymbolPrecision(normalized);
    }
    const price = await fetchSymbolPrice(symbol);
    if (price !== null && price !== undefined) {
      const snapped = snapToInputStep(price, entryInput);
      entryInput.value = snapped;
      entryInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function updateTickerCache(symbol, price) {
    if (!symbol || price === null || price === undefined) {
      return;
    }
    const numeric = Number(price);
    if (!Number.isFinite(numeric)) {
      return;
    }
    const key = symbol.toUpperCase();
    state.priceCache.set(key, { price: numeric, ts: Date.now() });
  }

  window.TradeApp = {
    API_BASE,
    state,
    SYMBOL_PATTERN,
    formatNumber,
    validateSymbol,
    getSymbolMeta,
    applySymbolPrecision,
    prefillEntryPrice,
    updateTickerCache,
    getAtrTimeframe,
    applyAtrTimeframeSelection,
    applyTheme,
    renderAccountSummary,
    applyAccountPayload,
    loadAccountSummary,
    renderSymbolOptions,
    loadSymbols,
    fetchAtrStop,
    snapToInputStep,
    setSideValue,
    resetSideValue,
  };

  document.addEventListener("DOMContentLoaded", () => {
    initThemeListener();
    initAtrTimeframeSelector();
    initSideToggle();
    attachSymbolDropdown();
    applySymbolPrecision(null);
    loadSymbols();
    loadAccountSummary();
    startAccountSummaryHeartbeat();
    initStreamHealthDiagnostics();
  });
})();
