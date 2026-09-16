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
