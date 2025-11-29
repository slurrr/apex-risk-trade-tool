async function postExecute(payload) {
  const response = await fetch("/api/trade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, execute: true, preview: false }),
  });
  const data = await response.json();
  if (!response.ok) {
    const msg = data?.detail || "Execute request failed";
    throw new Error(msg);
  }
  return data;
}

function renderExecute(container, result) {
  container.innerHTML = `
    <div><strong>Executed:</strong> ${result.executed}</div>
    <div><strong>Exchange Order ID:</strong> ${result.exchange_order_id}</div>
    <div><strong>Side:</strong> ${result.side}</div>
    <div><strong>Size:</strong> ${result.size}</div>
    <div><strong>Notional:</strong> ${result.notional}</div>
    <div><strong>Estimated Loss:</strong> ${result.estimated_loss}</div>
    <div><strong>Warnings:</strong> ${(result.warnings || []).join(", ") || "None"}</div>
  `;
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("preview-form");
  const executeBtn = document.getElementById("execute-button");
  const executeResult = document.getElementById("execute-result");

  executeBtn.addEventListener("click", async () => {
    const payload = {
      symbol: document.getElementById("symbol").value.trim(),
      entry_price: parseFloat(document.getElementById("entry_price").value),
      stop_price: parseFloat(document.getElementById("stop_price").value),
      risk_pct: parseFloat(document.getElementById("risk_pct").value),
      side: document.getElementById("side").value.trim() || null,
      tp: document.getElementById("tp").value ? parseFloat(document.getElementById("tp").value) : null,
    };
    try {
      const result = await postExecute(payload);
      renderExecute(executeResult, result);
    } catch (err) {
      executeResult.innerHTML = `<div class="error">${err.message}</div>`;
    }
  });
});
