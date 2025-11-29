function normalizePosition(position) {
  return {
    symbol: position.symbol || position.market || "-",
    side: position.side || position.positionSide || position.direction || "-",
    size: position.size || position.qty || position.quantity || "-",
    entry: position.entryPrice || position.avgPrice || position.entry_price || "-",
    pnl: position.unrealizedPnl || position.unrealizedPnlUsd || position.pnl || "-",
  };
}

async function fetchPositions() {
  const resp = await fetch("/api/positions");
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
    const info = normalizePosition(pos);
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${info.symbol}</td>
      <td>${info.side}</td>
      <td>${info.size}</td>
      <td>${info.entry}</td>
      <td>${info.pnl}</td>
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

document.addEventListener("DOMContentLoaded", () => {
  const refreshBtn = document.getElementById("refresh-positions");
  refreshBtn.addEventListener("click", loadPositions);
  loadPositions();
});
