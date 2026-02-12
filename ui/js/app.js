(function () {
  const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000`;
  const SYMBOL_PATTERN = /^[A-Z0-9]+-[A-Z0-9]+$/;
  const DEFAULT_PRICE_DECIMALS = 6;
  const PRICE_INPUT_IDS = ["entry_price", "stop_price", "tp"];
  const THEME_STORAGE_KEY = "trade_app_theme";
  const ATR_TIMEFRAME_STORAGE_KEY = "atr_timeframe_override";
  const SYMBOL_FAVORITES_STORAGE_KEY = "symbol_favorites_v1";
  const ATR_TIMEFRAME_DEFAULT = "15m";
  const ATR_TIMEFRAMES_FALLBACK = ["3m", "15m", "1h", "4h"];
  const SUPPORTED_VENUES = ["hyperliquid", "apex"];
  const DAILY_EQUITY_BASELINES_STORAGE_KEY = "daily_equity_baselines_v1";
  const VENUE_ACCENT_MAP = {
    hyperliquid: {
      accent: "#4fd6b4",
      accentRgb: "79, 214, 180",
      accentPress: "#35b394",
      accentMuted: "rgba(79, 214, 180, 0.30)",
    },
    apex: {
      accent: "#ecbc43",
      accentRgb: "236, 188, 67",
      accentPress: "#d8a529",
      accentMuted: "rgba(236, 188, 67, 0.30)",
    },
  };
  const VENUE_SYNC_INTERVAL_MS = 5000;
  const DEV_STREAM_HEALTH_STORAGE_KEY = "dev_stream_health";
  const STREAM_HEALTH_POLL_INTERVAL_MS = 15000;
  let manualTheme = null;
  let mediaQuery;
  let streamHealthTimerId = null;
  let venueSyncTimerId = null;
  let venueSyncInFlight = false;
  let venueSwitchInProgress = false;
  const state = {
    symbols: [],
    symbolIndex: new Map(),
    priceCache: new Map(),
    activeSymbol: null,
    activeTickSize: null,
    activePriceDecimals: DEFAULT_PRICE_DECIMALS,
    lastAccountUpdate: 0,
    activeVenue: null,
    dailyEquityBaselines: new Map(),
    lastAccountSummary: null,
    symbolFavoritesByVenue: {},
    atrTimeframes: [...ATR_TIMEFRAMES_FALLBACK],
    atrDefaultTimeframe: ATR_TIMEFRAME_DEFAULT,
    riskPresets: [1, 3, 6, 9],
    riskDefaultPct: 3,
  };
  let sideToggleControl = null;

  function normalizeSymbolCode(value) {
    const clean = (value || "").trim().toUpperCase();
    if (SYMBOL_PATTERN.test(clean)) {
      return clean;
    }
    return null;
  }

  function createTradeTraceId() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return `trd-${crypto.randomUUID()}`;
    }
    return `trd-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
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

  function getCurrentUtcDayKey() {
    return new Date().toISOString().slice(0, 10);
  }

  function loadDailyEquityBaselines() {
    try {
      if (!window.localStorage) return;
      const raw = window.localStorage.getItem(DAILY_EQUITY_BASELINES_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return;
      const currentDay = getCurrentUtcDayKey();
      const next = new Map();
      Object.entries(parsed).forEach(([key, value]) => {
        if (typeof key !== "string") return;
        const day = key.split(":")[1];
        if (day !== currentDay) return;
        const num = Number(value);
        if (!Number.isFinite(num)) return;
        next.set(key, num);
      });
      state.dailyEquityBaselines = next;
      persistDailyEquityBaselines();
    } catch (err) {
      // ignore storage errors
    }
  }

  function persistDailyEquityBaselines() {
    try {
      if (!window.localStorage) return;
      const currentDay = getCurrentUtcDayKey();
      const serializable = {};
      for (const [key, value] of state.dailyEquityBaselines.entries()) {
        const day = key.split(":")[1];
        if (day !== currentDay) continue;
        serializable[key] = value;
      }
      window.localStorage.setItem(DAILY_EQUITY_BASELINES_STORAGE_KEY, JSON.stringify(serializable));
    } catch (err) {
      // ignore storage errors
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
    updateVenueBannersForTheme(theme);
    if (options.persist) {
      persistTheme(theme);
    }
  }

  function updateVenueBannersForTheme(theme) {
    const hlBanner = document.getElementById("venue-banner-hl");
    if (!hlBanner) return;
    const darkSrc = hlBanner.getAttribute("data-dark-src");
    const lightSrc = hlBanner.getAttribute("data-light-src");
    const nextSrc = theme === "light" ? lightSrc : darkSrc;
    if (nextSrc) {
      hlBanner.setAttribute("src", nextSrc);
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
    const allowed =
      Array.isArray(state.atrTimeframes) && state.atrTimeframes.length
        ? state.atrTimeframes
        : ATR_TIMEFRAMES_FALLBACK;
    return allowed.includes(clean) ? clean : null;
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

  function normalizeFavoriteSymbol(value) {
    if (!value) return null;
    const symbol = normalizeSymbolCode(value);
    return symbol || null;
  }

  function getFavoritesVenueKey(venue = null) {
    return normalizeVenue(venue || state.activeVenue) || "global";
  }

  function loadSymbolFavorites() {
    try {
      if (!window.localStorage) return;
      const raw = window.localStorage.getItem(SYMBOL_FAVORITES_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return;
      const next = {};
      Object.entries(parsed).forEach(([venue, values]) => {
        if (!Array.isArray(values)) return;
        const unique = Array.from(
          new Set(values.map(normalizeFavoriteSymbol).filter(Boolean))
        );
        next[venue] = unique;
      });
      state.symbolFavoritesByVenue = next;
    } catch (err) {
      state.symbolFavoritesByVenue = {};
    }
  }

  function persistSymbolFavorites() {
    try {
      if (!window.localStorage) return;
      window.localStorage.setItem(
        SYMBOL_FAVORITES_STORAGE_KEY,
        JSON.stringify(state.symbolFavoritesByVenue || {})
      );
    } catch (err) {
      // ignore storage errors
    }
  }

  function getFavoriteSet(venue = null) {
    const key = getFavoritesVenueKey(venue);
    const raw = state.symbolFavoritesByVenue[key];
    const normalized = Array.isArray(raw)
      ? Array.from(new Set(raw.map(normalizeFavoriteSymbol).filter(Boolean)))
      : [];
    state.symbolFavoritesByVenue[key] = normalized;
    return new Set(normalized);
  }

  function setFavoritesForVenue(symbolSet, venue = null) {
    const key = getFavoritesVenueKey(venue);
    const normalized = Array.from(
      new Set(Array.from(symbolSet || []).map(normalizeFavoriteSymbol).filter(Boolean))
    ).sort((a, b) => a.localeCompare(b));
    state.symbolFavoritesByVenue[key] = normalized;
    persistSymbolFavorites();
  }

  function getAtrTimeframeInput() {
    return document.getElementById("atr_timeframe");
  }

  function getAtrTimeframeToggle() {
    return document.querySelector(".atr-timeframe-toggle");
  }

  function getRiskPresetToggle() {
    return document.querySelector(".risk-preset-toggle");
  }

  function normalizeRiskPreset(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }

  function formatRiskPreset(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "";
    return Number.isInteger(parsed) ? `${parsed}%` : `${parsed.toFixed(2)}%`;
  }

  function renderRiskPresetButtons(options) {
    const toggle = getRiskPresetToggle();
    if (!toggle) return;
    toggle.querySelectorAll(".risk-preset-option").forEach((el) => el.remove());
    const list = Array.isArray(options) && options.length ? options : [1, 3, 6, 9];
    list.slice(0, 4).forEach((value) => {
      const normalized = normalizeRiskPreset(value);
      if (normalized === null) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "risk-preset-option";
      btn.dataset.value = String(normalized);
      btn.setAttribute("aria-pressed", "false");
      btn.textContent = formatRiskPreset(normalized);
      toggle.appendChild(btn);
    });
  }

  function renderAtrTimeframeButtons(options) {
    const toggle = getAtrTimeframeToggle();
    if (!toggle) return;
    const input = getAtrTimeframeInput();
    toggle.querySelectorAll(".atr-timeframe-option").forEach((el) => el.remove());
    const list = Array.isArray(options) && options.length ? options : ATR_TIMEFRAMES_FALLBACK;
    list.slice(0, 4).forEach((value) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "atr-timeframe-option";
      btn.dataset.value = value;
      btn.setAttribute("aria-pressed", "false");
      btn.textContent = value;
      toggle.appendChild(btn);
    });
    if (input && !normalizeAtrTimeframe(input.value)) {
      input.value = list[0] || ATR_TIMEFRAME_DEFAULT;
    }
  }

  function applyAtrTimeframeSelection(value, options = {}) {
    const { persist = false, silent = false } = options;
    const normalized = normalizeAtrTimeframe(value) || state.atrDefaultTimeframe || ATR_TIMEFRAME_DEFAULT;
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
    return stored || state.atrDefaultTimeframe || ATR_TIMEFRAME_DEFAULT;
  }

  async function loadAtrTimeframeConfig() {
    try {
      const payload = await fetchJson(`${API_BASE}/risk/atr-config`);
      const optionsRaw = Array.isArray(payload?.timeframes) ? payload.timeframes : [];
      const options = optionsRaw
        .map((v) => (v || "").toString().trim().toLowerCase())
        .filter((v) => /^\d+[mh]$/.test(v));
      state.atrTimeframes = options.length ? options.slice(0, 4) : [...ATR_TIMEFRAMES_FALLBACK];
      const def = (payload?.default_timeframe || "").toString().trim().toLowerCase();
      state.atrDefaultTimeframe = state.atrTimeframes.includes(def)
        ? def
        : (state.atrTimeframes[0] || ATR_TIMEFRAME_DEFAULT);
      const riskRaw = Array.isArray(payload?.risk_presets) ? payload.risk_presets : [];
      const risk = riskRaw
        .map(normalizeRiskPreset)
        .filter((v) => v !== null);
      state.riskPresets = risk.length ? risk.slice(0, 4) : [1, 3, 6, 9];
      const riskDefault = normalizeRiskPreset(payload?.risk_default_pct);
      state.riskDefaultPct = riskDefault || 3;
    } catch (err) {
      state.atrTimeframes = [...ATR_TIMEFRAMES_FALLBACK];
      state.atrDefaultTimeframe = ATR_TIMEFRAME_DEFAULT;
      state.riskPresets = [1, 3, 6, 9];
      state.riskDefaultPct = 3;
    }
    const riskInput = document.getElementById("risk_pct");
    const defaultRisk = normalizeRiskPreset(state.riskDefaultPct) || normalizeRiskPreset(state.riskPresets[1]) || 3;
    if (riskInput) {
      riskInput.value = Number.isInteger(defaultRisk) ? String(defaultRisk) : defaultRisk.toFixed(2);
    }
    renderAtrTimeframeButtons(state.atrTimeframes);
    renderRiskPresetButtons(state.riskPresets);
    refreshRiskPresetState();
  }

  async function initAtrTimeframeSelector() {
    await loadAtrTimeframeConfig();
    const input = getAtrTimeframeInput();
    const buttons = Array.from(document.querySelectorAll(".atr-timeframe-option"));
    if (!input || buttons.length === 0) return;
    const initial = state.atrDefaultTimeframe || normalizeAtrTimeframe(input.value) || ATR_TIMEFRAME_DEFAULT;
    applyAtrTimeframeSelection(initial, { persist: true, silent: true });
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        applyAtrTimeframeSelection(btn.dataset.value, { persist: true });
      });
    });
  }

  function refreshRiskPresetState() {
    const input = document.getElementById("risk_pct");
    if (!input) return;
    const current = Number(input.value);
    const buttons = Array.from(document.querySelectorAll(".risk-preset-option"));
    buttons.forEach((btn) => {
      const value = Number(btn.dataset.value);
      const isActive = Number.isFinite(current) && Number.isFinite(value) && Math.abs(current - value) < 1e-9;
      btn.classList.toggle("is-active", isActive);
      btn.setAttribute("aria-pressed", String(isActive));
    });
  }

  function initRiskPresetSelector() {
    const input = document.getElementById("risk_pct");
    const toggle = getRiskPresetToggle();
    if (!input || !toggle) return;
    const defaultRisk = normalizeRiskPreset(state.riskDefaultPct) || normalizeRiskPreset(state.riskPresets[1]) || 3;
    input.value = Number.isInteger(defaultRisk) ? String(defaultRisk) : defaultRisk.toFixed(2);
    toggle.addEventListener("click", (event) => {
      const btn = event.target.closest(".risk-preset-option");
      if (!btn) return;
      const value = normalizeRiskPreset(btn.dataset.value);
      if (value === null) return;
      input.value = Number.isInteger(value) ? String(value) : value.toFixed(2);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      refreshRiskPresetState();
    });
    input.addEventListener("input", refreshRiskPresetState);
    input.addEventListener("change", refreshRiskPresetState);
    refreshRiskPresetState();
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
    const equityDailyPctEl = document.getElementById("summary-equity-daily-pct");
    const upnlEl = document.getElementById("summary-upnl");
    const upnlPctEl = document.getElementById("summary-upnl-pct");
    const marginEl = document.getElementById("summary-margin");
    const withdrawableEl = document.getElementById("summary-withdrawable");
    if (!summary) return;
    const format = (val) => (typeof val === "number" ? val.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "--");
    const formatPct = (val) => {
      if (typeof val !== "number" || !Number.isFinite(val)) return "--";
      const sign = val > 0 ? "+" : "";
      return `${sign}${val.toFixed(2)}%`;
    };
    const updateSignClass = (el, value) => {
      if (!el) return;
      el.classList.remove("positive", "negative");
      if (typeof value === "number" && Number.isFinite(value)) {
        if (value > 0) el.classList.add("positive");
        if (value < 0) el.classList.add("negative");
      }
    };
    const venue = normalizeVenue(summary.venue) || state.activeVenue || "apex";
    const dayKey = getCurrentUtcDayKey();
    const baselineKey = `${venue}:${dayKey}`;
    const equityNow = typeof summary.total_equity === "number" ? summary.total_equity : null;
    if (equityNow !== null && !state.dailyEquityBaselines.has(baselineKey)) {
      state.dailyEquityBaselines.set(baselineKey, equityNow);
      persistDailyEquityBaselines();
    }
    const baselineEquity = state.dailyEquityBaselines.get(baselineKey);
    const computedDailyPct =
      equityNow !== null &&
      typeof baselineEquity === "number" &&
      Number.isFinite(baselineEquity) &&
      baselineEquity > 0
        ? ((equityNow - baselineEquity) / baselineEquity) * 100
        : null;
    const dailyPct =
      typeof summary.daily_equity_change_pct === "number" && Number.isFinite(summary.daily_equity_change_pct)
        ? summary.daily_equity_change_pct
        : computedDailyPct;

    let upnlPct = null;
    if (typeof summary.total_upnl_pct === "number" && Number.isFinite(summary.total_upnl_pct)) {
      upnlPct = summary.total_upnl_pct;
    } else if (typeof summary.total_upnl === "number" && typeof summary.total_equity === "number") {
      const pnlBase = summary.total_equity - summary.total_upnl;
      const safeBase = Math.abs(pnlBase) > 1e-9 ? pnlBase : summary.total_equity;
      if (Math.abs(safeBase) > 1e-9) {
        upnlPct = (summary.total_upnl / safeBase) * 100;
      }
    }

    equityEl.textContent = format(summary.total_equity);
    upnlEl.textContent = format(summary.total_upnl);
    marginEl.textContent = format(summary.available_margin);
    if (equityDailyPctEl) equityDailyPctEl.textContent = formatPct(dailyPct);
    if (upnlPctEl) upnlPctEl.textContent = formatPct(upnlPct);
    if (withdrawableEl) withdrawableEl.textContent = format(summary.withdrawable_amount);
    updateSignClass(upnlEl, summary.total_upnl);
    updateSignClass(upnlPctEl, upnlPct);
    updateSignClass(equityDailyPctEl, dailyPct);
  }

  function coerceNumber(value) {
    if (value === null || value === undefined) return null;
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  function pickNumber(...values) {
    for (const value of values) {
      const parsed = coerceNumber(value);
      if (parsed !== null) {
        return parsed;
      }
    }
    return null;
  }

  function normalizeAccountPayload(payload) {
    if (!payload || typeof payload !== "object") return null;
    const totalEquity = pickNumber(
      payload.total_equity,
      payload.totalEquity,
      payload.totalEquityValue,
      payload.totalEquityUsd,
      payload.totalEquityUSDT
    );
    const available = pickNumber(
      payload.available_margin,
      payload.availableBalance,
      payload.available,
      payload.availableEquity
    );
    const totalUpnl = pickNumber(
      payload.total_upnl,
      payload.totalUnrealizedPnl,
      payload.totalUnrealizedPnlUsd,
      payload.totalUpnl
    );
    const withdrawable = pickNumber(
      payload.withdrawable_amount,
      payload.withdrawable,
      payload.withdrawableAmount,
      payload.availableWithdrawable,
      available
    );
    const totalUpnlPct = pickNumber(payload.total_upnl_pct, payload.totalUpnlPct);
    const dailyEquityChangePct = pickNumber(payload.daily_equity_change_pct, payload.dailyEquityChangePct);
    const venue = normalizeVenue(payload.venue) || state.activeVenue;
    if (totalEquity === null && available === null && totalUpnl === null) {
      return null;
    }
    return {
      total_equity: totalEquity ?? 0,
      available_margin: available ?? 0,
      total_upnl: totalUpnl ?? 0,
      total_upnl_pct: totalUpnlPct,
      daily_equity_change_pct: dailyEquityChangePct,
      withdrawable_amount: withdrawable,
      venue,
    };
  }

  function applyAccountPayload(payload) {
    const summary = normalizeAccountPayload(payload);
    if (summary) {
      state.lastAccountSummary = summary;
      renderAccountSummary(summary);
      state.lastAccountUpdate = Date.now();
      window.dispatchEvent(new CustomEvent("account:summary", { detail: summary }));
    }
  }

  async function loadAccountSummary() {
    try {
      const data = await fetchJson(`${API_BASE}/api/account/summary`);
      applyAccountPayload(data);
    } catch (err) {
      // silent fail for header; avoid blocking UI
      const upnlEl = document.getElementById("summary-upnl");
      if (upnlEl) upnlEl.textContent = "--";
    }
  }

  function startAccountSummaryHeartbeat() {
    let lastForcedRefresh = 0;
    window.setInterval(() => {
      const staleMs = 20000;
      const forcedRefreshMs = 30000;
      const now = Date.now();
      const last = state.lastAccountUpdate || 0;
      const stale = !last || now - last > staleMs;
      const dueForced = !lastForcedRefresh || now - lastForcedRefresh > forcedRefreshMs;
      if (stale || dueForced) {
        lastForcedRefresh = now;
        loadAccountSummary();
      }
    }, 10000);
  }

  function normalizeVenue(value) {
    const clean = (value || "").toString().trim().toLowerCase();
    return SUPPORTED_VENUES.includes(clean) ? clean : null;
  }

  function applyVenueAccent(venue) {
    const normalized = normalizeVenue(venue) || "apex";
    const palette = VENUE_ACCENT_MAP[normalized] || VENUE_ACCENT_MAP.apex;
    document.documentElement.style.setProperty("--accent", palette.accent);
    document.documentElement.style.setProperty("--accent-rgb", palette.accentRgb);
    document.documentElement.style.setProperty("--accent-press", palette.accentPress);
    document.documentElement.style.setProperty("--accent-muted", palette.accentMuted);
  }

  function setVenueSwitchState({ activeVenue = null, switching = false, status = "" } = {}) {
    const statusEl = document.getElementById("venue-switch-status");
    const buttons = Array.from(document.querySelectorAll(".venue-switch-btn"));
    buttons.forEach((btn) => {
      const venue = normalizeVenue(btn.dataset.venue);
      const isActive = Boolean(activeVenue && venue === activeVenue);
      btn.classList.toggle("is-active", isActive);
      btn.setAttribute("aria-pressed", String(isActive));
      btn.disabled = switching;
    });
    if (activeVenue) {
      applyVenueAccent(activeVenue);
    }
    if (statusEl) {
      if (switching && status) {
        statusEl.textContent = status;
        statusEl.classList.remove("hidden");
      } else {
        statusEl.textContent = "";
        statusEl.classList.add("hidden");
      }
    }
  }

  async function loadActiveVenue(options = {}) {
    const { propagateChange = true } = options;
    const panel = document.getElementById("venue-switch-card");
    if (!panel) return null;
    if (venueSwitchInProgress || venueSyncInFlight) {
      return state.activeVenue;
    }
    venueSyncInFlight = true;
    try {
      const payload = await fetchJson(`${API_BASE}/api/venue`);
      const activeVenue = normalizeVenue(payload?.active_venue);
      const previousVenue = state.activeVenue;
      state.activeVenue = activeVenue;
      setVenueSwitchState({ activeVenue });
      if (
        propagateChange &&
        previousVenue &&
        activeVenue &&
        previousVenue !== activeVenue
      ) {
        loadSymbols();
        loadAccountSummary();
        window.dispatchEvent(
          new CustomEvent("venue:changed", { detail: { active_venue: activeVenue } })
        );
      }
      return activeVenue;
    } catch (err) {
      setVenueSwitchState({ activeVenue: state.activeVenue });
      return null;
    } finally {
      venueSyncInFlight = false;
    }
  }

  async function setActiveVenue(nextVenue) {
    const normalized = normalizeVenue(nextVenue);
    if (!normalized || normalized === state.activeVenue) {
      return;
    }
    setVenueSwitchState({
      activeVenue: state.activeVenue,
      switching: true,
      status: `Switching to ${normalized}...`,
    });
    venueSwitchInProgress = true;
    try {
      const resp = await fetch(`${API_BASE}/api/venue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_venue: normalized }),
      });
      const payload = await resp.json();
      if (!resp.ok) {
        throw new Error(payload?.detail || "Venue switch failed");
      }
      const activeVenue = normalizeVenue(payload?.active_venue);
      state.activeVenue = activeVenue;
      setVenueSwitchState({ activeVenue });
      loadSymbols();
      loadAccountSummary();
      window.dispatchEvent(
        new CustomEvent("venue:changed", { detail: { active_venue: activeVenue } })
      );
    } catch (err) {
      setVenueSwitchState({ activeVenue: state.activeVenue });
    } finally {
      venueSwitchInProgress = false;
    }
  }

  function startVenueSyncLoop() {
    if (venueSyncTimerId) {
      window.clearInterval(venueSyncTimerId);
    }
    venueSyncTimerId = window.setInterval(() => {
      loadActiveVenue();
    }, VENUE_SYNC_INTERVAL_MS);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        loadActiveVenue();
      }
    });
    window.addEventListener("focus", () => {
      loadActiveVenue();
    });
  }

  function initVenueSwitcher() {
    const panel = document.getElementById("venue-switch-card");
    if (!panel) return;
    const buttons = Array.from(panel.querySelectorAll(".venue-switch-btn"));
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        setActiveVenue(btn.dataset.venue);
      });
    });
    setVenueSwitchState({ activeVenue: state.activeVenue });
    loadActiveVenue({ propagateChange: false });
    startVenueSyncLoop();
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
    const favorites = getFavoriteSet();
    const filtered = state.symbols.filter((sym) => sym.code.toUpperCase().includes(query));
    const favoriteRows = filtered.filter((sym) => favorites.has(sym.code.toUpperCase()));
    const regularRows = filtered.filter((sym) => !favorites.has(sym.code.toUpperCase()));
    const matches = [...favoriteRows, ...regularRows];
    list.innerHTML = "";
    matches.slice(0, 30).forEach((sym) => {
      const row = document.createElement("div");
      row.className = "symbol-option-row";

      const selectBtn = document.createElement("button");
      selectBtn.type = "button";
      selectBtn.className = "symbol-option-btn";
      selectBtn.textContent = sym.code;
      selectBtn.addEventListener("click", () => {
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

      const favBtn = document.createElement("button");
      favBtn.type = "button";
      favBtn.className = "symbol-fav-btn";
      const symCode = sym.code.toUpperCase();
      const isFavorite = favorites.has(symCode);
      favBtn.classList.toggle("is-favorite", isFavorite);
      favBtn.textContent = isFavorite ? "★" : "☆";
      favBtn.setAttribute("aria-label", isFavorite ? `Remove ${sym.code} from favorites` : `Add ${sym.code} to favorites`);
      favBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const nextFavorites = getFavoriteSet();
        if (nextFavorites.has(symCode)) {
          nextFavorites.delete(symCode);
        } else {
          nextFavorites.add(symCode);
        }
        setFavoritesForVenue(nextFavorites);
        renderSymbolOptions(input.value);
        list.classList.add("open");
        if (typeof input.focus === "function") {
          input.focus({ preventScroll: true });
        }
      });

      row.appendChild(favBtn);
      row.appendChild(selectBtn);
      list.appendChild(row);
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
        const previewCard = document.getElementById("preview-card");
        const executeCard = document.getElementById("execute-card");
        if (previewCard) previewCard.classList.add("hidden");
        if (executeCard) executeCard.classList.add("hidden");
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

  function normalizeTradeSide(value) {
    const raw = (value || "").toString().trim().toUpperCase();
    if (raw === "BUY" || raw === "LONG") return "BUY";
    if (raw === "SELL" || raw === "SHORT") return "SELL";
    return null;
  }

  function markStopInputInvalid(invalid) {
    const stopInput = document.getElementById("stop_price");
    if (!stopInput) return;
    stopInput.classList.toggle("is-invalid", Boolean(invalid));
  }

  function flashSideToggle() {
    const wrapper = document.querySelector(".side-toggle");
    if (!wrapper) return;
    wrapper.classList.remove("is-flash");
    // restart animation
    void wrapper.offsetWidth;
    wrapper.classList.add("is-flash");
    window.setTimeout(() => wrapper.classList.remove("is-flash"), 1680);
  }

  function warnUserPopup(message) {
    const msg = (message || "").toString().trim() || "Invalid order inputs.";
    if (typeof window !== "undefined" && typeof window.alert === "function") {
      window.alert(msg);
    }
  }

  function assessTradeDirection(entryPrice, stopPrice, sideValue) {
    const entry = Number(entryPrice);
    const stop = Number(stopPrice);
    const side = normalizeTradeSide(sideValue);
    if (!Number.isFinite(entry) || !Number.isFinite(stop) || !side) {
      return { ready: false, valid: true, side, expectedSide: null, reason: null };
    }
    if (stop === entry) {
      return {
        ready: true,
        valid: false,
        side,
        expectedSide: null,
        reason: "Stop price cannot equal entry price.",
      };
    }
    const expectedSide = stop < entry ? "BUY" : "SELL";
    if (side !== expectedSide) {
      return {
        ready: true,
        valid: false,
        side,
        expectedSide,
        reason:
          expectedSide === "BUY"
            ? "Stop below entry implies Long (BUY). Side was auto-corrected."
            : "Stop above entry implies Short (SELL). Side was auto-corrected.",
      };
    }
    return { ready: true, valid: true, side, expectedSide, reason: null };
  }

  function enforceTradeDirectionConsistency(options = {}) {
    const { autoFlip = true, animate = true } = options;
    const entryInput = document.getElementById("entry_price");
    const stopInput = document.getElementById("stop_price");
    const sideInput = document.getElementById("side");
    if (!entryInput || !stopInput || !sideInput) {
      return { ready: false, valid: true, reason: null };
    }
    const check = assessTradeDirection(entryInput.value, stopInput.value, sideInput.value);
    if (!check.ready) {
      markStopInputInvalid(false);
      return check;
    }
    if (!check.valid && check.expectedSide && autoFlip) {
      markStopInputInvalid(true);
      setSideValue(check.expectedSide, { force: true });
      if (animate) {
        flashSideToggle();
      }
      window.setTimeout(() => markStopInputInvalid(false), 520);
      return { ...check, valid: true, corrected: true };
    }
    markStopInputInvalid(!check.valid);
    return check;
  }

  function initTradeDirectionGuard() {
    const entryInput = document.getElementById("entry_price");
    const stopInput = document.getElementById("stop_price");
    const sideInput = document.getElementById("side");
    if (!entryInput || !stopInput || !sideInput) return;
    let showInvalidState = false;
    const hasCompleteInputs = () => {
      const entry = Number(entryInput.value);
      const stop = Number(stopInput.value);
      const side = normalizeTradeSide(sideInput.value);
      return Number.isFinite(entry) && Number.isFinite(stop) && !!side;
    };
    const isTickDistanceInvalid = () => {
      const tickSize = state.activeTickSize;
      if (!(typeof tickSize === "number" && tickSize > 0)) {
        return false;
      }
      const entry = Number(entryInput.value);
      const stop = Number(stopInput.value);
      if (!Number.isFinite(entry) || !Number.isFinite(stop)) {
        return false;
      }
      return Math.abs(entry - stop) < tickSize;
    };
    const refreshInvalidState = (directionCheck) => {
      if (!hasCompleteInputs()) {
        markStopInputInvalid(false);
        return;
      }
      if (!showInvalidState) {
        markStopInputInvalid(false);
        return;
      }
      const directionInvalid = Boolean(directionCheck?.ready && !directionCheck.valid);
      const tickInvalid = isTickDistanceInvalid();
      markStopInputInvalid(directionInvalid || tickInvalid);
    };
    const priceHandler = (evt) => {
      if (evt?.isTrusted) {
        showInvalidState = true;
      }
      enforceTradeDirectionConsistency({ autoFlip: true, animate: true });
      const current = assessTradeDirection(entryInput.value, stopInput.value, sideInput.value);
      refreshInvalidState(current);
    };
    const sideHandler = (evt) => {
      if (evt?.isTrusted) {
        showInvalidState = true;
      }
      const check = enforceTradeDirectionConsistency({ autoFlip: false, animate: false });
      refreshInvalidState(check);
      if (!check.valid) {
        window.dispatchEvent(
          new CustomEvent("trade:side-stop-mismatch", {
            detail: {
              reason: check.reason || "Side and stop are inconsistent for the current entry.",
            },
          })
        );
      }
    };
    markStopInputInvalid(false);
    entryInput.addEventListener("input", priceHandler);
    stopInput.addEventListener("input", priceHandler);
    sideInput.addEventListener("change", sideHandler);
    priceHandler();
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
    enforceTradeDirectionConsistency,
    warnUserPopup,
    markStopInputInvalid,
    createTradeTraceId,
  };

  document.addEventListener("DOMContentLoaded", () => {
    loadDailyEquityBaselines();
    loadSymbolFavorites();
    initThemeListener();
    initVenueSwitcher();
    initAtrTimeframeSelector();
    initRiskPresetSelector();
    initSideToggle();
    initTradeDirectionGuard();
    attachSymbolDropdown();
    applySymbolPrecision(null);
    loadSymbols();
    loadAccountSummary();
    startAccountSummaryHeartbeat();
    initStreamHealthDiagnostics();
  });
})();
