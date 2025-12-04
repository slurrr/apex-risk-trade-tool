(function () {
  const API_BASE = window.API_BASE || "http://localhost:8000";
  const SYMBOL_PATTERN = /^[A-Z0-9]+-[A-Z0-9]+$/;
  const state = {
    symbols: [],
  };

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
  }

  function initThemeListener() {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const setTheme = () => applyTheme(media.matches ? "dark" : "light");
    setTheme();
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", setTheme);
    } else if (typeof media.addListener === "function") {
      media.addListener(setTheme);
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

  async function loadAccountSummary() {
    try {
      const data = await fetchJson(`${API_BASE}/api/account/summary`);
      renderAccountSummary(data);
    } catch (err) {
      // silent fail for header; avoid blocking UI
      const upnlEl = document.getElementById("summary-upnl");
      if (upnlEl) upnlEl.textContent = "—";
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

  function attachSymbolDropdown() {
    const input = document.getElementById("symbol-input");
    const list = document.getElementById("symbol-options");
    if (!input || !list) return;
    input.addEventListener("input", () => renderSymbolOptions(input.value));
    input.addEventListener("focus", () => renderSymbolOptions(input.value));
    document.addEventListener("click", (evt) => {
      if (!list.contains(evt.target) && evt.target !== input) {
        list.classList.remove("open");
      }
    });
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

  window.TradeApp = {
    API_BASE,
    state,
    SYMBOL_PATTERN,
    formatNumber,
    validateSymbol,
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
