(function () {
  const API_BASE =
    (window.TradeApp && window.TradeApp.API_BASE) ||
    window.API_BASE ||
    `${window.location.protocol}//${window.location.hostname}:8000`;
  const validateSymbol = (window.TradeApp && window.TradeApp.validateSymbol) || ((val) => val?.toUpperCase());
  const TOLERANCE_KEY = "liquidity_tolerance_bps";
  const DEFAULT_TOLERANCE = 10;
  const LEVELS = 25;
  const POLL_MS = 2000;
  const DEBOUNCE_MS = 300;

  const state = {
    symbol: null,
    tolerance: DEFAULT_TOLERANCE,
    inflight: 0,
    pollTimer: null,
    debounceTimer: null,
    paused: false,
  };

  function getPanelElements() {
    return {
      panel: document.getElementById("liquidity-panel"),
      headline: document.getElementById("liquidity-headline"),
      headlineBuy: document.getElementById("liquidity-headline-buy"),
      headlineSell: document.getElementById("liquidity-headline-sell"),
      spread: document.getElementById("liquidity-spread"),
      top: document.getElementById("liquidity-top"),
      status: document.getElementById("liquidity-status"),
      chips: Array.from(document.querySelectorAll(".liquidity-chip")),
    };
  }

  function readStoredTolerance() {
    try {
      const value = window.localStorage ? window.localStorage.getItem(TOLERANCE_KEY) : null;
      const numeric = Number(value);
      return Number.isFinite(numeric) ? numeric : null;
    } catch (err) {
      return null;
    }
  }

  function persistTolerance(bps) {
    try {
      if (window.localStorage) {
        window.localStorage.setItem(TOLERANCE_KEY, String(bps));
      }
    } catch (err) {
      // ignore storage errors
    }
  }

  function setPanelMode(panel, mode) {
    if (!panel) return;
    panel.classList.toggle("is-loading", mode === "loading");
    panel.classList.toggle("is-buy", mode === "buy");
    panel.classList.toggle("is-sell", mode === "sell");
  }

  function formatNotional(value) {
    if (!Number.isFinite(value)) return "--";
    const absValue = Math.abs(value);
    const digits = absValue < 1 ? 4 : 2;
    return value.toLocaleString(undefined, { maximumFractionDigits: digits });
  }

  function formatSpread(value) {
    if (!Number.isFinite(value)) return "--";
    return value.toFixed(2);
  }

  function computeSpreadBps(bid, ask) {
    if (!Number.isFinite(bid) || !Number.isFinite(ask)) return null;
    const mid = (bid + ask) / 2;
    if (!Number.isFinite(mid) || mid <= 0) return null;
    return ((ask - bid) / mid) * 10000;
  }

  function formatPrice(value) {
    if (!Number.isFinite(value)) return "--";
    const decimals =
      window.TradeApp && window.TradeApp.state && typeof window.TradeApp.state.activePriceDecimals === "number"
        ? window.TradeApp.state.activePriceDecimals
        : 2;
    return value.toLocaleString(undefined, { maximumFractionDigits: Math.min(decimals, 10) });
  }

  function updateHeadlines({ side, tolerance, buyNotional, sellNotional, loading }) {
    const { headline, headlineBuy, headlineSell } = getPanelElements();
    if (!headline || !headlineBuy || !headlineSell) return;
    const label = Number.isFinite(tolerance) ? `${tolerance} bps` : "--";
    if (loading) {
      headline.textContent = "Loading...";
      headline.classList.remove("hidden");
      headlineBuy.classList.add("hidden");
      headlineSell.classList.add("hidden");
      return;
    }
    if (side === "BUY" || side === "SELL") {
      const notional = side === "BUY" ? buyNotional : sellNotional;
      headline.textContent = `Max size @ ${label}: ${formatNotional(notional)}`;
      headline.classList.remove("hidden");
      headlineBuy.classList.add("hidden");
      headlineSell.classList.add("hidden");
      return;
    }
    headline.textContent = "--";
    headline.classList.add("hidden");
    headlineBuy.textContent = `Max Buy @ ${label}: ${formatNotional(buyNotional)}`;
    headlineSell.textContent = `Max Sell @ ${label}: ${formatNotional(sellNotional)}`;
    headlineBuy.classList.remove("hidden");
    headlineSell.classList.remove("hidden");
  }

  function renderIdle() {
    const { panel, spread, top, status } = getPanelElements();
    setPanelMode(panel, null);
    updateHeadlines({ side: null, tolerance: state.tolerance, buyNotional: null, sellNotional: null, loading: false });
    if (spread) spread.textContent = "--";
    if (top) top.textContent = "--";
    if (status) {
      status.textContent = "";
      status.removeAttribute("title");
      status.classList.remove("is-error");
    }
  }

  function renderLoading(side) {
    const { panel, status } = getPanelElements();
    setPanelMode(panel, "loading");
    updateHeadlines({ side, tolerance: state.tolerance, buyNotional: null, sellNotional: null, loading: true });
    if (status) {
      status.textContent = "";
      status.removeAttribute("title");
      status.classList.remove("is-error");
    }
  }

  function renderError(message, detail) {
    const { panel, status, spread, top } = getPanelElements();
    setPanelMode(panel, null);
    updateHeadlines({ side: null, tolerance: state.tolerance, buyNotional: null, sellNotional: null, loading: false });
    if (spread) spread.textContent = "--";
    if (top) top.textContent = "--";
    if (status) {
      status.textContent = message || "Liquidity unavailable";
      status.classList.add("is-error");
      if (detail) {
        status.setAttribute("title", detail);
      } else {
        status.removeAttribute("title");
      }
    }
  }

  function renderSummary(summary, side) {
    const { panel, spread, top, status } = getPanelElements();
    if (!summary) {
      renderIdle();
      return;
    }
    if (side === "BUY") {
      setPanelMode(panel, "buy");
    } else if (side === "SELL") {
      setPanelMode(panel, "sell");
    } else {
      setPanelMode(panel, null);
    }
    updateHeadlines({
      side,
      tolerance: summary.tolerance_bps,
      buyNotional: summary.max_buy_notional,
      sellNotional: summary.max_sell_notional,
      loading: false,
    });
    if (spread) {
      const computed = computeSpreadBps(summary.bid, summary.ask);
      const spreadValue = Number.isFinite(computed) ? computed : summary.spread_bps;
      spread.textContent = formatSpread(spreadValue);
    }
    if (top) {
      const bid = formatPrice(summary.bid);
      const ask = formatPrice(summary.ask);
      top.innerHTML = `<span class="liquidity-bid">${bid}</span> / <span class="liquidity-ask">${ask}</span>`;
    }
    if (status) {
      status.textContent = "";
      status.removeAttribute("title");
      status.classList.remove("is-error");
    }
  }

  function getActiveSide() {
    const sideInput = document.getElementById("side");
    const value = sideInput ? sideInput.value : null;
    const normalized = (value || "").toString().trim().toUpperCase();
    return normalized === "BUY" || normalized === "SELL" ? normalized : null;
  }

  function schedulePoll() {
    if (state.pollTimer) {
      clearTimeout(state.pollTimer);
    }
    if (state.paused) return;
    state.pollTimer = window.setTimeout(runPoll, POLL_MS);
  }

  function scheduleFetch() {
    if (state.debounceTimer) {
      clearTimeout(state.debounceTimer);
    }
    state.debounceTimer = window.setTimeout(runPoll, DEBOUNCE_MS);
  }

  async function runPoll() {
    const symbolInput = document.getElementById("symbol-input");
    const symbol = validateSymbol(symbolInput ? symbolInput.value : state.symbol);
    state.symbol = symbol || null;
    if (!symbol) {
      renderIdle();
      return;
    }
    const side = getActiveSide();
    const token = ++state.inflight;
    renderLoading(side);
    try {
      const url = `${API_BASE}/api/market/depth-summary/${encodeURIComponent(symbol)}?tolerance_bps=${state.tolerance}&levels=${LEVELS}`;
      const resp = await fetch(url);
      const data = await resp.json();
      if (token !== state.inflight) return;
      if (!resp.ok) {
        throw new Error(data?.detail || "Liquidity unavailable");
      }
      renderSummary(data, side);
    } catch (err) {
      if (token !== state.inflight) return;
      renderError("Liquidity unavailable", err?.message);
    } finally {
      schedulePoll();
    }
  }

  function initToleranceChips() {
    const { chips } = getPanelElements();
    if (!chips.length) return;
    const stored = readStoredTolerance();
    const initial = [5, 10, 25].includes(stored) ? stored : DEFAULT_TOLERANCE;
    state.tolerance = initial;
    chips.forEach((chip) => {
      const value = Number(chip.dataset.bps);
      const isActive = value === initial;
      chip.classList.toggle("is-active", isActive);
      if (isActive) {
        chip.setAttribute("aria-pressed", "true");
      } else {
        chip.setAttribute("aria-pressed", "false");
      }
      chip.addEventListener("click", () => {
        if (!Number.isFinite(value)) return;
        state.tolerance = value;
        persistTolerance(value);
        chips.forEach((btn) => {
          const btnValue = Number(btn.dataset.bps);
          const active = btnValue === value;
          btn.classList.toggle("is-active", active);
          btn.setAttribute("aria-pressed", active ? "true" : "false");
        });
        runPoll();
      });
    });
  }

  function initListeners() {
    const symbolInput = document.getElementById("symbol-input");
    const sideInput = document.getElementById("side");
    if (symbolInput) {
      symbolInput.addEventListener("input", scheduleFetch);
      symbolInput.addEventListener("change", scheduleFetch);
    }
    if (sideInput) {
      sideInput.addEventListener("change", () => {
        if (state.symbol) {
          runPoll();
        } else {
          renderIdle();
        }
      });
    }
    document.addEventListener("visibilitychange", () => {
      state.paused = document.hidden;
      if (state.paused) {
        if (state.pollTimer) clearTimeout(state.pollTimer);
      } else {
        runPoll();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const { panel } = getPanelElements();
    if (!panel) return;
    initToleranceChips();
    initListeners();
    renderIdle();
  });
})();
