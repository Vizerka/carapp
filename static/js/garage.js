const search = document.getElementById('garage-search');
const statusFilter = document.getElementById('garage-status');
const rows = Array.from(document.querySelectorAll('[data-garage-status]'));
const normalize = value => value.toLocaleLowerCase('pl').normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '').replace(/ł/g, 'l');

function filterGarage() {
  const terms = normalize(search.value).trim().split(/\s+/);
  for (const row of rows) {
    const label = normalize(row.dataset.garageSearch);
    row.hidden = !terms.every(term => label.includes(term))
      || Boolean(statusFilter.value && row.dataset.garageStatus !== statusFilter.value);
  }
  document.getElementById('garage-empty').hidden = rows.some(row => !row.hidden);
}

search.addEventListener('input', filterGarage);
statusFilter.addEventListener('change', filterGarage);
filterGarage();
