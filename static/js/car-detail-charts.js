    window.addEventListener('load', function () {
      // locale PL (ticki/tooltipy)
      if (window.luxon?.Settings) {
        luxon.Settings.defaultLocale = 'pl';
      }

      function num(v) {
        if (v === null || v === undefined) return NaN;
        return Number(String(v).trim().replace(/\s+/g, '').replace(',', '.'));
      }

      function drawTimeChart(canvasId, labelText) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        const isConsumption = canvasId === 'consChart';
        const controls = el.closest('[data-time-chart]');
        const fixedAxis = controls.querySelector('[data-chart-axis]');
        const viewport = controls.querySelector('[data-chart-viewport]');
        const plot = controls.querySelector('[data-chart-plot]');
        const period = controls.querySelector('[data-chart-period]');
        const scroll = controls.querySelector('[data-chart-scroll]');
        const latest = controls.querySelector('[data-chart-latest]');
        const dates = controls.querySelector('[data-chart-dates]');

        const labels = JSON.parse(el.dataset.labels || '[]'); // ["2026-01-22", ...]
        const values = JSON.parse(el.dataset.values || '[]'); // [136000, ...]
        if (!labels.length || !values.length) return;

        // parsing:false wymaga liczbowych znaczników czasu.
        const points = labels.map((d, i) => {
          const dt = luxon.DateTime.fromISO(String(d));
          return { x: dt.isValid ? dt.toMillis() : NaN, y: values[i] === null ? null : num(values[i]) };
        })
        .filter(p => Number.isFinite(p.x) && (Number.isFinite(p.y) || (isConsumption && p.y === null)))
        .sort((a, b) => a.x - b.x);

        if (!points.length) return;

        // Przebieg można dociągnąć do dziś; pomiar spalania kończy się przy tankowaniu.
        const last = points[points.length - 1];
        const todayStart = luxon.DateTime.local().startOf('day').toMillis();
        if (!isConsumption && last.x < todayStart) {
          points.push({ x: luxon.DateTime.local().toMillis(), y: last.y });
        }

        const minX = points[0].x;
        const maxX = Math.max(
          minX + 24 * 60 * 60 * 1000, // co najmniej jeden dzień przy pojedynczym pomiarze
          isConsumption ? last.x : luxon.DateTime.local().endOf('day').toMillis(),
          points[points.length - 1].x
        );

        // Wszystkie wpisy zostają na wykresie; okres zmienia tylko szerokość
        // płótna, a nie liczbę punktów w zbiorze danych.
        function plotWidth() {
          const screenWidth = Math.max(viewport.clientWidth, 1);
          if (period.value === 'all') return screenWidth;
          const months = Number(period.value);
          const periodStart = luxon.DateTime.fromMillis(maxX).minus({ months }).toMillis();
          const periodDuration = Math.min(maxX - minX, maxX - periodStart);
          return Math.min(28000, Math.max(screenWidth,
            Math.round(screenWidth * (maxX - minX) / periodDuration)
          ));
        }

        const initialWidth = plotWidth();
        plot.style.width = `${initialWidth}px`;
        function pixelRatio(width) {
          // Długie historie muszą zmieścić się w rozsądnym buforze canvas.
          return Math.min(window.devicePixelRatio || 1, 30000 / width,
            Math.sqrt(8000000 / (width * 240))
          );
        }

        const ctx = el.getContext('2d');
        const chart = new Chart(ctx, {
          type: 'line',
          data: {
            datasets: [{
              label: labelText,
              data: points,
              tension: 0.2,
              spanGaps: false,
              clip: 8,
              pointRadius: 4,
              pointHitRadius: 8
            }]
          },
          options: {
            parsing: false, // data jest już w formacie {x(ms), y}
            responsive: true,
            maintainAspectRatio: false,
            devicePixelRatio: pixelRatio(initialWidth),
            interaction: { mode: 'index', intersect: false },
            scales: {
              x: {
                type: 'time',
                min: minX,
                max: maxX,
                time: { tooltipFormat: 'yyyy-LL-dd' },
                ticks: { autoSkip: true, maxRotation: 0 }
              },
              // Obliczaj podziałkę i linie siatki, ale wartości pokaż w panelu
              // obok, który nie jest wewnątrz przewijanego kontenera.
              y: { beginAtZero: false, ticks: { display: false } }
            }
          }
        });

        function maxScroll() {
          return Math.max(0, plot.clientWidth - viewport.clientWidth);
        }

        function drawFixedAxis() {
          const y = chart.scales.y;
          fixedAxis.textContent = '';
          y.getTicks().forEach((tick, index) => {
            const pixel = y.getPixelForTick(index);
            if (!Number.isFinite(pixel)) return;
            const value = document.createElement('span');
            value.className = 'small text-body-secondary';
            value.style.position = 'absolute';
            value.style.right = '8px';
            value.style.top = `${pixel}px`;
            value.style.transform = 'translateY(-50%)';
            value.style.whiteSpace = 'nowrap';
            value.textContent = Array.isArray(tick.label)
              ? tick.label.join(' ') : String(tick.label ?? tick.value);
            fixedAxis.appendChild(value);
          });
        }

        function updateNavigation() {
          const available = maxScroll();
          const position = Math.min(available, viewport.scrollLeft);
          scroll.disabled = available <= 1;
          scroll.value = scroll.disabled ? 1000 : Math.round(position / available * 1000);
          latest.disabled = scroll.disabled || position >= available - 1;

          // Odczytujemy daty z faktycznego obszaru rysowania Chart.js, tak by
          // podpis odpowiadał również przestrzeni zajętej przez osie wykresu.
          const scale = chart.scales.x;
          const firstPixel = Math.max(chart.chartArea.left, position);
          const lastPixel = Math.min(chart.chartArea.right, position + viewport.clientWidth);
          const from = Math.max(minX, Math.min(maxX, scale.getValueForPixel(firstPixel)));
          const to = Math.max(minX, Math.min(maxX, scale.getValueForPixel(lastPixel)));
          dates.textContent = `${luxon.DateTime.fromMillis(from).toFormat('dd.LL.yyyy')} – ${luxon.DateTime.fromMillis(to).toFormat('dd.LL.yyyy')}`;
        }

        function resizePlot(preservePosition) {
          const oldMax = maxScroll();
          const fraction = preservePosition && oldMax > 1 ? viewport.scrollLeft / oldMax : 1;
          const width = plotWidth();
          plot.style.width = `${width}px`;
          chart.options.devicePixelRatio = pixelRatio(width);
          chart.resize(width, 240);
          drawFixedAxis();
          viewport.scrollLeft = fraction * maxScroll();
          updateNavigation();
        }

        resizePlot(false); // otwórz historię przy ostatnich danych
        viewport.addEventListener('scroll', updateNavigation);
        period.addEventListener('change', function () { resizePlot(true); });
        scroll.addEventListener('input', function () {
          viewport.scrollLeft = Number(scroll.value) / 1000 * maxScroll();
          updateNavigation();
        });
        latest.addEventListener('click', function () {
          viewport.scrollLeft = maxScroll();
          updateNavigation();
        });
        window.addEventListener('resize', function () { resizePlot(true); });

        // Gładzik przewija natywny kontener; Shift + kółko dodaje pionowy gest
        // do przesunięcia w poziomie, nie przechwytując zwykłego scrolla strony.
        viewport.addEventListener('wheel', function (event) {
          if (!event.shiftKey || event.deltaX) return;
          const before = viewport.scrollLeft;
          viewport.scrollLeft += event.deltaY;
          if (viewport.scrollLeft !== before) event.preventDefault();
        }, { passive: false });
      }

      drawTimeChart('odoChart', 'Przebieg [km]');
      drawTimeChart('consChart', 'L/100km');
    });
