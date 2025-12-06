(function () {
  const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000`;
  const SYMBOL_PATTERN = /^[A-Z0-9]+-[A-Z0-9]+$/;
  const THEME_STORAGE_KEY = "trade_app_theme";
  let manualTheme = null;
  let mediaQuery;
  const state = {
    symbols: [],
    priceCache: new Map(),
  };

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

  async function fetchJson(url) {
    const resp = await fetch(url);
    const data = await resp.json();
    if (!resp.ok) {
      const msg = data?.detail || "Request failed";
      throw new Error(msg);
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
    }
  }

  async function loadAccountSummary() {
    try {
      const data = await fetchJson(`${API_BASE}/api/account/summary`);
      renderAccountSummary(data);
    } catch (err) {
      // silent fail for header; avoid blocking UI
      const upnlEl = document.getElementById("summary-upnl");
      if (upnlEl) upnlEl.textContent = "--";
    }
  }

  async function loadSymbols() {
    try {
      const data = await fetchJson(`${API_BASE}/api/symbols`);
      state.symbols = Array.isArray(data) ? data : [];
    } catch (err) {
      state.symbols = [];
    }
  }

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
        input.value = sym.code;
        list.classList.remove("open");
        prefillEntryPrice(sym.code);
        updateSymbolClearState();
      });
      list.appendChild(btn);
    });
    const shouldOpen = document.activeElement === input && matches.length > 0;
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
    if (!input || !list) return;
    input.addEventListener("input", () => {
      renderSymbolOptions(input.value);
      updateSymbolClearState();
    });
    input.addEventListener("focus", () => {
      renderSymbolOptions(input.value);
      updateSymbolClearState();
    });
    input.addEventListener("blur", () => {
      setTimeout(updateSymbolClearState, 0);
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
      });
    }
    if (clearFormBtn) {
      clearFormBtn.addEventListener("click", () => {
        const form = document.getElementById("preview-form");
        if (form) {
          form.reset();
        }
        input.value = "";
        renderSymbolOptions("");
        const dropdown = document.getElementById("side");
        if (dropdown) dropdown.selectedIndex = 0;
        updateSymbolClearState();
        document.getElementById("preview-result").innerHTML = "";
        document.getElementById("execute-result").innerHTML = "";
      });
    }
  }

  function validateSymbol(value) {
    const clean = (value || "").trim().toUpperCase();
    if (SYMBOL_PATTERN.test(clean)) return clean;
    return null;
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
    const price = await fetchSymbolPrice(symbol);
    if (price !== null && price !== undefined) {
      entryInput.value = price;
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
    prefillEntryPrice,
    updateTickerCache,
    applyTheme,
    renderAccountSummary,
    applyAccountPayload,
    loadAccountSummary,
    renderSymbolOptions,
    loadSymbols,
  };

  document.addEventListener("DOMContentLoaded", () => {
    initThemeListener();
    attachSymbolDropdown();
    loadSymbols();
    loadAccountSummary();
  });
})();
