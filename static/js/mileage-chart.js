(function () {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const MIN_ZOOM = 100;
  const MAX_ZOOM = 1200;
  const ZOOM_STEP = 50;
  const DAY = 24 * 60 * 60 * 1000;

  const plDate = new Intl.DateTimeFormat('pl-PL', {
    day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC'
  });
  const plMonth = new Intl.DateTimeFormat('pl-PL', {
    month: 'short', year: 'numeric', timeZone: 'UTC'
  });
  const plKm = new Intl.NumberFormat('pl-PL');

  function svgElement(name, attributes) {
    const element = document.createElementNS(SVG_NS, name);
    Object.entries(attributes || {}).forEach(([key, value]) => {
      element.setAttribute(key, String(value));
    });
    return element;
  }

  function parseDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ''));
    if (!match) return NaN;
    return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function niceStep(value) {
    if (!Number.isFinite(value) || value <= 0) return 1;
    const power = Math.pow(10, Math.floor(Math.log10(value)));
    const fraction = value / power;
    const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
    return niceFraction * power;
  }

  function yScale(values) {
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const span = maximum - minimum;
    const margin = span > 0 ? span * .12 : Math.max(Math.abs(maximum) * .12, 1000);
    const paddedMin = minimum - margin;
    const paddedMax = maximum + margin;
    const step = niceStep((paddedMax - paddedMin) / 5);
    const min = Math.max(0, Math.floor(paddedMin / step) * step);
    const max = Math.max(min + step, Math.ceil(paddedMax / step) * step);
    const ticks = [];
    for (let value = min; value <= max + step / 2; value += step) ticks.push(value);
    return { min, max, ticks };
  }

  function positionedPoints(points, left, availableWidth) {
    const firstTime = points[0].time;
    const lastTime = points[points.length - 1].time;

    if (points.length === 1) {
      return points.map(point => ({ ...point, x: left + availableWidth / 2 }));
    }

    if (firstTime === lastTime) {
      return points.map((point, index) => ({
        ...point,
        x: left + availableWidth * index / (points.length - 1)
      }));
    }

    const result = points.map(point => ({
      ...point,
      x: left + (point.time - firstTime) / (lastTime - firstTime) * availableWidth
    }));

    // Punkty z tego samego dnia nadal są osobnymi zapisami. Rozsuwamy je o
    // kilka pikseli, zamiast pozwolić, by ostatni całkowicie przykrył pozostałe.
    for (let start = 0; start < result.length;) {
      let end = start + 1;
      while (end < result.length && result[end].time === result[start].time) end += 1;
      const count = end - start;
      if (count > 1) {
        const base = result[start].x;
        const leftBound = start > 0 ? (result[start - 1].x + base) / 2 : left;
        const rightBound = end < result.length
          ? (base + result[end].x) / 2
          : left + availableWidth;
        const spread = Math.min(60, rightBound - leftBound, 10 * (count - 1));
        const center = clamp(
          base,
          leftBound + spread / 2,
          rightBound - spread / 2
        );
        for (let index = 0; index < count; index += 1) {
          result[start + index].x = center - spread / 2 + spread * index / (count - 1);
        }
      }
      start = end;
    }

    return result;
  }

  function formatTick(time, interval) {
    const date = new Date(time);
    if (interval >= 300 * DAY) return String(date.getUTCFullYear());
    if (interval >= 35 * DAY) return plMonth.format(date);
    return plDate.format(date);
  }

  function createTooltip() {
    const tooltip = document.createElement('div');
    tooltip.className = 'mileage-chart-tooltip';
    tooltip.setAttribute('role', 'tooltip');
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function initMileageChart(layout) {
    const panel = layout.closest('.mileage-chart-panel');
    const yAxis = layout.querySelector('[data-mileage-y-axis]');
    const viewport = layout.querySelector('[data-mileage-scroll]');
    const svg = layout.querySelector('[data-mileage-svg]');
    const zoomOut = panel.querySelector('[data-mileage-zoom-out]');
    const zoomIn = panel.querySelector('[data-mileage-zoom-in]');
    const zoomReset = panel.querySelector('[data-mileage-zoom-reset]');
    const zoomValue = panel.querySelector('[data-mileage-zoom]');
    const range = panel.querySelector('[data-mileage-range]');
    const tooltip = createTooltip();

    let rawPoints;
    try {
      rawPoints = JSON.parse(layout.dataset.points || '[]');
    } catch (_error) {
      rawPoints = [];
    }

    const points = rawPoints.map((point, index) => ({
      id: Number(point.id) || 0,
      date: String(point.date || ''),
      time: parseDate(point.date),
      km: Number(point.km),
      label: String(point.label || 'Odczyt licznika'),
      order: index
    })).filter(point => Number.isFinite(point.time) && Number.isFinite(point.km))
      .sort((a, b) => a.time - b.time || a.id - b.id || a.order - b.order);

    if (!points.length) return;

    let zoom = MIN_ZOOM;
    let renderedWidth = 0;
    let resizeFrame = null;

    function hideTooltip() {
      tooltip.classList.remove('is-visible');
    }

    function placeTooltip(clientX, clientY) {
      const gap = 14;
      const bounds = tooltip.getBoundingClientRect();
      const left = clamp(clientX + gap, 8, window.innerWidth - bounds.width - 8);
      const top = clamp(clientY - bounds.height - gap, 8, window.innerHeight - bounds.height - 8);
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    }

    function showTooltip(point, clientX, clientY) {
      tooltip.textContent = '';
      const heading = document.createElement('strong');
      heading.textContent = `${plDate.format(new Date(point.time))} · ${plKm.format(point.km)} km`;
      const note = document.createElement('span');
      note.textContent = point.label;
      tooltip.append(heading, note);
      tooltip.classList.add('is-visible');
      placeTooltip(clientX, clientY);
    }

    function drawAxis(height, top, bottom, scale, yFor) {
      yAxis.textContent = '';
      const axisWidth = Math.max(yAxis.clientWidth, 1);
      const axisSvg = svgElement('svg', {
        width: axisWidth,
        height,
        viewBox: `0 0 ${axisWidth} ${height}`,
        'aria-hidden': 'true'
      });

      scale.ticks.forEach(value => {
        const y = yFor(value);
        const tick = svgElement('line', {
          x1: axisWidth - 7, x2: axisWidth, y1: y, y2: y,
          stroke: '#6f5795', 'stroke-width': 1
        });
        const label = svgElement('text', {
          x: axisWidth - 11, y: y + 4,
          fill: '#b0a4c6', 'font-size': 11,
          'text-anchor': 'end'
        });
        label.textContent = plKm.format(value);
        axisSvg.append(tick, label);
      });

      const title = svgElement('text', {
        x: 12,
        y: top + (height - top - bottom) / 2,
        fill: '#8f82a8',
        'font-size': 10,
        'text-anchor': 'middle',
        transform: `rotate(-90 12 ${top + (height - top - bottom) / 2})`
      });
      title.textContent = 'Przebieg [km]';
      axisSvg.appendChild(title);
      yAxis.appendChild(axisSvg);
    }

    function render(preserve) {
      hideTooltip();
      const viewportWidth = Math.max(viewport.clientWidth, 1);
      const height = Math.max(layout.clientHeight, 280);
      const width = Math.max(viewportWidth, Math.round(viewportWidth * zoom / 100));
      const top = 24;
      const bottom = 58;
      const left = 28;
      const right = 28;
      const plotHeight = height - top - bottom;
      const availableWidth = Math.max(1, width - left - right);
      const scale = yScale(points.map(point => point.km));
      const yFor = value => top + (scale.max - value) / (scale.max - scale.min) * plotHeight;
      const drawnPoints = positionedPoints(points, left, availableWidth)
        .map(point => ({ ...point, y: yFor(point.km) }));

      renderedWidth = width;
      svg.replaceChildren();
      svg.setAttribute('width', String(width));
      svg.setAttribute('height', String(height));
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      svg.style.width = `${width}px`;
      svg.style.height = `${height}px`;

      scale.ticks.forEach(value => {
        const y = yFor(value);
        svg.appendChild(svgElement('line', {
          x1: 0, x2: width, y1: y, y2: y,
          stroke: '#504063', 'stroke-width': 1,
          'stroke-dasharray': '4 6', opacity: .72
        }));
      });

      const firstTime = points[0].time;
      const lastTime = points[points.length - 1].time;
      if (firstTime === lastTime) {
        const label = svgElement('text', {
          x: width / 2, y: height - 20,
          fill: '#b0a4c6', 'font-size': 11, 'text-anchor': 'middle'
        });
        label.textContent = plDate.format(new Date(firstTime));
        svg.appendChild(label);
      } else {
        const tickCount = Math.max(2, Math.floor(availableWidth / 130) + 1);
        const interval = (lastTime - firstTime) / (tickCount - 1);
        for (let index = 0; index < tickCount; index += 1) {
          const ratio = index / (tickCount - 1);
          const x = left + availableWidth * ratio;
          const time = firstTime + (lastTime - firstTime) * ratio;
          svg.appendChild(svgElement('line', {
            x1: x, x2: x, y1: top, y2: height - bottom,
            stroke: '#504063', 'stroke-width': 1,
            'stroke-dasharray': '4 6', opacity: .45
          }));
          const label = svgElement('text', {
            x,
            y: height - 20,
            fill: '#b0a4c6',
            'font-size': 11,
            'text-anchor': index === 0 ? 'start' : index === tickCount - 1 ? 'end' : 'middle'
          });
          label.textContent = formatTick(time, interval);
          svg.appendChild(label);
        }
      }

      if (drawnPoints.length > 1) {
        const path = svgElement('path', {
          d: drawnPoints.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' '),
          fill: 'none',
          stroke: '#b899ff',
          'stroke-width': 2.5,
          'stroke-linejoin': 'round',
          'stroke-linecap': 'round'
        });
        svg.appendChild(path);
      }

      drawnPoints.forEach(point => {
        const circle = svgElement('circle', {
          cx: point.x, cy: point.y, r: 5,
          fill: '#a78bfa', stroke: '#130e20', 'stroke-width': 2,
          tabindex: 0,
          role: 'img',
          'aria-label': `${plDate.format(new Date(point.time))}, ${plKm.format(point.km)} km, ${point.label}`
        });
        circle.style.cursor = 'pointer';
        circle.addEventListener('pointerenter', event => showTooltip(point, event.clientX, event.clientY));
        circle.addEventListener('pointermove', event => placeTooltip(event.clientX, event.clientY));
        circle.addEventListener('pointerleave', hideTooltip);
        circle.addEventListener('focus', () => {
          const bounds = circle.getBoundingClientRect();
          showTooltip(point, bounds.left + bounds.width / 2, bounds.top);
        });
        circle.addEventListener('blur', hideTooltip);
        const title = svgElement('title');
        title.textContent = `${point.date} · ${plKm.format(point.km)} km · ${point.label}`;
        circle.appendChild(title);
        svg.appendChild(circle);
      });

      drawAxis(height, top, bottom, scale, yFor);
      zoomValue.textContent = `${zoom}%`;
      zoomOut.disabled = zoom <= MIN_ZOOM;
      zoomIn.disabled = zoom >= MAX_ZOOM;
      range.textContent = `${plDate.format(new Date(firstTime))} – ${plDate.format(new Date(lastTime))} · ${points.length} ${points.length === 1 ? 'odczyt' : 'odczytów'}`;

      if (preserve) {
        const anchorX = preserve.anchorX;
        viewport.scrollLeft = clamp(preserve.ratio * width - anchorX, 0, Math.max(0, width - viewport.clientWidth));
      }
    }

    function changeZoom(nextZoom, anchorX, reset) {
      const oldWidth = Math.max(renderedWidth, viewport.scrollWidth, 1);
      const ratio = reset ? 0 : (viewport.scrollLeft + anchorX) / oldWidth;
      const clamped = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
      if (clamped === zoom && !reset) return;
      zoom = clamped;
      render({ ratio, anchorX: reset ? 0 : anchorX });
      if (reset) viewport.scrollLeft = 0;
    }

    zoomOut.addEventListener('click', () => changeZoom(zoom - ZOOM_STEP, viewport.clientWidth / 2, false));
    zoomIn.addEventListener('click', () => changeZoom(zoom + ZOOM_STEP, viewport.clientWidth / 2, false));
    zoomReset.addEventListener('click', () => changeZoom(MIN_ZOOM, 0, true));
    viewport.addEventListener('scroll', hideTooltip, { passive: true });
    viewport.addEventListener('wheel', event => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const bounds = viewport.getBoundingClientRect();
      const anchorX = clamp(event.clientX - bounds.left, 0, viewport.clientWidth);
      changeZoom(zoom + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP), anchorX, false);
    }, { passive: false });

    const observer = new ResizeObserver(() => {
      if (resizeFrame !== null) cancelAnimationFrame(resizeFrame);
      const oldWidth = Math.max(renderedWidth, 1);
      const ratio = (viewport.scrollLeft + viewport.clientWidth / 2) / oldWidth;
      resizeFrame = requestAnimationFrame(() => {
        resizeFrame = null;
        render({ ratio, anchorX: viewport.clientWidth / 2 });
      });
    });
    observer.observe(layout);
    render();
  }

  function start() {
    document.querySelectorAll('[data-mileage-chart]').forEach(initMileageChart);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
