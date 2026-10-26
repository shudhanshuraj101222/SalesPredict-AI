(() => {
  const charts = window.salesPredictCharts || {};
  const palette = ['#3268d6', '#54a78d', '#eea84c', '#8c72cb', '#dd7185', '#53a6be', '#88a849', '#d1844a'];
  const currency = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
  const values = (items) => (items || []).map((item) => item.value);
  const labels = (items) => (items || []).map((item) => item.label);

  function lineChart(id, items, label = 'Revenue') {
    const canvas = document.getElementById(id);
    if (!canvas || !items?.length || !window.Chart) return;
    new Chart(canvas, {
      type: 'line',
      data: { labels: labels(items), datasets: [{ label, data: values(items), borderColor: palette[0], backgroundColor: '#3268d61a', fill: true, tension: 0.28, pointRadius: 2, borderWidth: 2 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (context) => `${label}: ${currency.format(context.raw)}` } } },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8, color: '#8792a3', font: { size: 9 } } }, y: { beginAtZero: true, grid: { color: '#edf0f4' }, ticks: { color: '#8792a3', font: { size: 9 }, callback: (value) => currency.format(value) } } },
      },
    });
  }
  function barChart(id, items, label = 'Revenue', horizontal = false) {
    const canvas = document.getElementById(id);
    if (!canvas || !items?.length || !window.Chart) return;
    new Chart(canvas, {
      type: 'bar',
      data: { labels: labels(items), datasets: [{ label, data: values(items), backgroundColor: items.map((_, index) => palette[index % palette.length]), borderRadius: 4, maxBarThickness: 34 }] },
      options: {
        indexAxis: horizontal ? 'y' : 'x', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (context) => `${label}: ${currency.format(context.raw)}` } } },
        scales: { x: { beginAtZero: true, grid: { display: horizontal ? true : false }, ticks: { color: '#8792a3', font: { size: 9 }, maxTicksLimit: 8 } }, y: { beginAtZero: true, grid: { color: '#edf0f4' }, ticks: { color: '#8792a3', font: { size: 9 } } } },
      },
    });
  }
  function monthlyChart(id, items) {
    const canvas = document.getElementById(id);
    if (!canvas || !items?.length || !window.Chart) return;
    new Chart(canvas, {
      data: {
        labels: labels(items),
        datasets: [
          { type: 'bar', label: 'Monthly revenue', data: values(items), backgroundColor: '#3268d633', borderRadius: 4, maxBarThickness: 34 },
          { type: 'line', label: 'Revenue trend', data: values(items), borderColor: palette[1], backgroundColor: palette[1], tension: 0.25, pointRadius: 3, borderWidth: 2 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: true, labels: { boxWidth: 9, color: '#8792a3', font: { size: 9 } } }, tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${currency.format(context.raw)}` } } },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8, color: '#8792a3', font: { size: 9 } } }, y: { beginAtZero: true, grid: { color: '#edf0f4' }, ticks: { color: '#8792a3', font: { size: 9 }, callback: (value) => currency.format(value) } } },
      },
    });
  }
  function comparisonChart(id, data) {
    const canvas = document.getElementById(id);
    if (!canvas || !data || !window.Chart) return;
    new Chart(canvas, {
      type: 'line',
      data: { labels: data.labels, datasets: [
        { label: 'Actual', data: data.actual, borderColor: palette[1], tension: 0.2 },
        { label: 'Predicted', data: data.predicted, borderColor: palette[0], borderDash: [5, 4], tension: 0.2 },
      ] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${currency.format(context.raw)}` } } }, scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8, color: '#8792a3', font: { size: 9 } } }, y: { beginAtZero: true, ticks: { color: '#8792a3', font: { size: 9 } } } } },
    });
  }

  monthlyChart('monthly-chart', charts.monthly);
  barChart('products-chart', charts.products, 'Revenue', true);
  lineChart('daily-chart', charts.daily);
  barChart('weekly-chart', charts.weekly);
  lineChart('analytics-month-chart', charts.monthly);
  barChart('analytics-products-chart', charts.products, 'Revenue', true);
  barChart('analytics-categories-chart', charts.categories, 'Revenue', true);
  lineChart('forecast-chart', charts.forecast, 'Predicted revenue');
  comparisonChart('performance-chart', charts.performance);
  comparisonChart('analytics-comparison-chart', charts.comparison);

  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
        event.preventDefault();
        return;
      }
      const submit = form.querySelector('button[type="submit"], button:not([type])');
      if (submit) {
        submit.disabled = true;
        submit.textContent = 'Working…';
      }
    });
  });
  document.querySelectorAll('table[data-sortable] th button[data-sort]').forEach((button, column) => {
    button.dataset.direction = 'ascending';
    button.addEventListener('click', () => {
      const table = button.closest('table');
      const body = table.querySelector('tbody');
      const direction = button.dataset.direction === 'ascending' ? 1 : -1;
      const numeric = button.dataset.sort === 'number';
      [...body.rows].sort((left, right) => {
        const a = left.cells[column].textContent.trim();
        const b = right.cells[column].textContent.trim();
        const order = numeric ? Number(a) - Number(b) : a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
        return order * direction;
      }).forEach((row) => body.appendChild(row));
      button.dataset.direction = direction === 1 ? 'descending' : 'ascending';
    });
  });
})();
