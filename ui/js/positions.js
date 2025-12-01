(function () {
  const API_BASE = window.API_BASE || "http://localhost:8000";

  function formatNumber(value) {
    if (value === null || value === undefined || value === "") return "";
    const num = Number(value);
    if (Number.isNaN(num)) return value;
    return num.toFixed(2);
  }

  async function fetchPositions() {
    const resp = await fetch(`${API_BASE}/api/positions`);
    const data = await resp.json();
    if (!resp.ok) {
      const msg = data?.detail || "Unable to load positions";
      throw new Error(msg);
    }
    return data;
  }

  function renderPositions(positions) {
    const tbody = document.querySelector("#positions-table tbody");
    const emptyState = document.getElementById("positions-empty");
    tbody.innerHTML = "";
    if (!positions || positions.length === 0) {
      emptyState.style.display = "block";
      return;
    }
    emptyState.style.display = "none";

    positions.forEach((pos) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${pos.symbol || ""}</td>
        <td>${pos.side || ""}</td>
        <td>${pos.size ?? ""}</td>
        <td>${formatNumber(pos.entry_price)}</td>
        <td>${formatNumber(pos.pnl)}</td>
      `;
      tbody.appendChild(row);
    });
  }

  async function loadPositions() {
    const errorBox = document.getElementById("positions-error");
    errorBox.textContent = "";
    try {
      const positions = await fetchPositions();
      renderPositions(positions);
    } catch (err) {
      errorBox.textContent = err.message;
    }
  }

  function startStream() {
    const errorBox = document.getElementById("positions-error");
    try {
      const wsUrl = (API_BASE.replace(/^http/, "ws")) + "/ws/stream";
      const socket = new WebSocket(wsUrl);
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "positions" && Array.isArray(msg.payload)) {
            renderPositions(msg.payload);
          }
        } catch (err) {
          // ignore malformed frames
        }
      };
      socket.onerror = () => {
        errorBox.textContent = "Stream disconnected; falling back to manual refresh.";
      };
      socket.onclose = () => {
        errorBox.textContent = "Stream closed; refresh to reconnect.";
      };
    } catch (err) {
      errorBox.textContent = err.message;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const refreshBtn = document.getElementById("refresh-positions");
    refreshBtn.addEventListener("click", loadPositions);
    loadPositions();
    startStream();
  });
})();
