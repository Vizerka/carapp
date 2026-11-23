(function () {
  const modal = document.getElementById('modalFuel');
  if (!modal) return;

  const fullTankEl = modal.querySelector('select[name="full_tank"]');
  const historyWrap = modal.querySelector('#newFuelHistory');
  const historyEl = modal.querySelector('#newFuelUnrecorded');
  function syncFuelHistory() {
    const full = fullTankEl.value === '1';
    historyWrap.hidden = !full;
    if (!full) historyEl.checked = false;
  }
  fullTankEl.addEventListener('change', syncFuelHistory);
  syncFuelHistory();

  const litersEl = modal.querySelector('input[name="liters"]');
  const totalEl  = modal.querySelector('input[name="total_cost"]');
  const pplEl    = modal.querySelector('input[name="price_per_l"]');

  if (!litersEl || !totalEl || !pplEl) return;

  let manual = false;

  function parseNum(v) {
    if (!v) return null;
    v = String(v).trim().replace(/\s+/g, '').replace(',', '.');
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function recalc() {
    if (manual) return;
    const liters = parseNum(litersEl.value);
    const total  = parseNum(totalEl.value);
    if (liters && total && liters > 0) {
      pplEl.value = (total / liters).toFixed(3);
    } else {
      pplEl.value = '';
    }
  }

  pplEl.addEventListener('input', () => {
    manual = (pplEl.value || '').trim() !== '';
  });

  litersEl.addEventListener('input', recalc);
  totalEl.addEventListener('input', recalc);

  modal.addEventListener('shown.bs.modal', () => {
    manual = (pplEl.value || '').trim() !== '';
    recalc();
  });
})();

(function () {
  const modal = document.getElementById('modalService');
  if (!modal) return;
  const form = modal.querySelector('form');
  const items = modal.querySelector('[data-service-items]');
  const template = modal.querySelector('[data-service-item-template]');
  const addButton = modal.querySelector('[data-service-item-add]');
  const cost = form.querySelector('input[name="cost"]');
  if (!items || !template || !addButton || !cost) return;

  let manualCost = false;

  function number(value) {
    const parsed = Number(String(value || '').trim().replace(/\s+/g, '').replace(',', '.'));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function recalculateCost() {
    if (manualCost) return;
    let total = 0;
    let hasPrice = false;
    items.querySelectorAll('[data-service-item-row]').forEach((row) => {
      const quantity = number(row.querySelector('[name="item_quantity[]"]')?.value) ?? 1;
      const price = number(row.querySelector('[name="item_unit_price[]"]')?.value);
      if (price !== null) {
        total += quantity * price;
        hasPrice = true;
      }
    });
    cost.value = hasPrice ? total.toFixed(2) : '';
  }

  function bindRow(row) {
    row.querySelectorAll('[name="item_quantity[]"], [name="item_unit_price[]"]').forEach((input) => {
      input.addEventListener('input', recalculateCost);
    });
    row.querySelector('[data-service-item-remove]')?.addEventListener('click', () => {
      const rows = items.querySelectorAll('[data-service-item-row]');
      if (rows.length === 1) {
        row.querySelectorAll('input').forEach((input) => {
          input.value = input.name === 'item_quantity[]' ? '1' : '';
        });
      } else {
        row.remove();
      }
      recalculateCost();
    });
  }

  items.querySelectorAll('[data-service-item-row]').forEach(bindRow);
  addButton.addEventListener('click', () => {
    const fragment = template.content.cloneNode(true);
    const row = fragment.querySelector('[data-service-item-row]');
    bindRow(row);
    items.appendChild(fragment);
    row.querySelector('[name="item_name[]"]')?.focus();
  });
  cost.addEventListener('input', () => {
    manualCost = cost.value.trim() !== '';
    if (!manualCost) recalculateCost();
  });
  modal.addEventListener('hidden.bs.modal', () => {
    manualCost = false;
  });
})();

(function () {
  const popovers = document.querySelectorAll('[data-fuel-history-popover]');
  if (!popovers.length) return;

  function closeAll(except) {
    popovers.forEach((details) => {
      if (details !== except) details.open = false;
    });
  }

  popovers.forEach((details) => {
    details.addEventListener('toggle', () => {
      if (details.open) closeAll(details);
    });
  });

  document.addEventListener('pointerdown', (event) => {
    popovers.forEach((details) => {
      if (details.open && !details.contains(event.target)) details.open = false;
    });
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeAll();
  });
})();
