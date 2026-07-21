/**
 * Report Action1 — Main JavaScript
 * Auto-refresh, chart helpers, toast notifications, sync button
 */

/* ================================================================
   Chart.js global defaults (dark theme)
   ================================================================ */
if (typeof Chart !== 'undefined') {
  Chart.defaults.color = '#8b949e';
  Chart.defaults.borderColor = '#30363d';
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.legend.labels.padding = 16;
}

/* ================================================================
   Color palette
   ================================================================ */
const COLORS = {
  accent:  '#00d4ff',
  green:   '#39d353',
  red:     '#f85149',
  yellow:  '#e3b341',
  purple:  '#bc8cff',
  orange:  '#f0883e',
  muted:   '#484f58',
  grid:    '#21262d',
};

const PALETTE = [
  '#00d4ff', '#39d353', '#e3b341', '#bc8cff',
  '#f0883e', '#f85149', '#58a6ff', '#56d364',
];

/* ================================================================
   Toast notifications
   ================================================================ */
const ToastManager = {
  show(message, type = 'info', duration = 3500) {
    const icons = { info: '📡', success: '✅', error: '❌', warning: '⚠️' };
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast-cyber ${type}`;
    toast.innerHTML = `<span>${icons[type] || '📡'}</span><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideIn 0.3s ease reverse';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }
};

/* ================================================================
   Auto-refresh status bar (every 30 seconds)
   ================================================================ */
const StatusRefresh = {
  interval: 30000,
  timer: null,

  start() {
    this.timer = setInterval(() => this.fetch(), this.interval);
  },

  stop() {
    if (this.timer) clearInterval(this.timer);
  },

  async fetch() {
    try {
      const res = await fetch('/action1/api/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.update(data);
    } catch (e) {
      console.warn('Status refresh failed:', e);
    }
  },

  update(data) {
    // Update sidebar status dot
    const dot = document.getElementById('api-status-dot');
    const label = document.getElementById('api-status-label');
    if (dot && label) {
      dot.className = `status-dot ${data.api_healthy ? 'online' : 'offline'}`;
      label.textContent = data.api_healthy ? 'API Online' : 'API Offline';
    }

    // Update sync time
    const syncEl = document.getElementById('last-sync-time');
    if (syncEl && data.synced_at) {
      const dt = new Date(data.synced_at);
      syncEl.textContent = dt.toLocaleTimeString();
    }

    // Update live KPI badges if they exist on the page
    const mapping = {
      'kpi-total-endpoints': data.total_endpoints,
      'kpi-online':          data.online,
      'kpi-offline':         data.offline,
      'kpi-running':         data.running_automations,
      'kpi-failed-24h':      data.failed_last_24h,
      'kpi-total-orgs':      data.total_orgs,
    };

    for (const [id, val] of Object.entries(mapping)) {
      const el = document.getElementById(id);
      if (el && val !== undefined) el.textContent = val.toLocaleString();
    }
  }
};

/* ================================================================
   Manual sync buttons
   ================================================================ */
function triggerSync(section = 'all') {
  const btnId = section === 'all' ? 'btn-sync' : `btn-sync-${section}`;
  const btn = document.getElementById(btnId);
  const originalHtml = btn ? btn.innerHTML : '';

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Syncing…';
  }

  fetch(`/action1/api/sync?section=${section}`)
    .then(r => r.json())
    .then(data => {
      const msg = section === 'all' ? 'Full sync initiated.' : `${section.charAt(0).toUpperCase() + section.slice(1)} sync initiated.`;
      ToastManager.show(msg + ' Data will refresh shortly.', 'success');
      setTimeout(() => {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = originalHtml;
        }
        StatusRefresh.fetch();
      }, 5000);
    })
    .catch(() => {
      ToastManager.show('Sync request failed.', 'error');
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
      }
    });
}

/**
 * Toggle visibility of a dashboard section
 */
function toggleCollapse(btn) {
  const card = btn.closest('.table-card');
  const body = card.querySelector('.table-card-body');
  const icon = btn.querySelector('i');

  if (body.style.display === 'none') {
    body.style.display = 'block';
    icon.classList.replace('bi-chevron-down', 'bi-chevron-up');
  } else {
    body.style.display = 'none';
    icon.classList.replace('bi-chevron-up', 'bi-chevron-down');
  }
}

/* ================================================================
   Chart builders
   ================================================================ */

/**
 * Doughnut chart: Online vs Offline endpoints
 */
function buildOnlineOfflineChart(canvasId, online, offline) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Online', 'Offline'],
      datasets: [{
        data: [online, offline],
        backgroundColor: [COLORS.green, COLORS.red],
        borderColor: '#1c2128',
        borderWidth: 3,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { position: 'bottom' },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed.toLocaleString()}`
          }
        }
      }
    }
  });
}

/**
 * Horizontal bar chart: Endpoints per Organization
 */
function buildEndpointsPerOrgChart(canvasId, labels, online, offline) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Online',
          data: online,
          backgroundColor: COLORS.green + '99',
          borderColor: COLORS.green,
          borderWidth: 1,
          borderRadius: 4,
        },
        {
          label: 'Offline',
          data: offline,
          backgroundColor: COLORS.red + '99',
          borderColor: COLORS.red,
          borderWidth: 1,
          borderRadius: 4,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: {
        legend: { position: 'top' }
      },
      scales: {
        x: {
          stacked: true,
          grid: { color: COLORS.grid },
          ticks: { precision: 0 }
        },
        y: {
          stacked: true,
          grid: { display: false },
          ticks: {
            font: { size: 11 }
          }
        }
      },
      barThickness: 25,
      maxBarThickness: 35,
      categoryPercentage: 0.9,
      barPercentage: 0.9,
    }
  });
}

/**
 * Doughnut chart: OS distribution
 */
function buildOsChart(canvasId, labels, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: PALETTE,
        borderColor: '#1c2128',
        borderWidth: 3,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '60%',
      plugins: {
        legend: { position: 'bottom' }
      }
    }
  });
}

/**
 * Line chart: Automation execution history timeline
 */
function buildHistoryTimeline(canvasId, labels, success, failed) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Success',
          data: success,
          backgroundColor: COLORS.green + '33',
          borderColor: COLORS.green,
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 3,
        },
        {
          label: 'Failed',
          data: failed,
          backgroundColor: COLORS.red + '33',
          borderColor: COLORS.red,
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 3,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top' }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxTicksLimit: 14 }
        },
        y: {
          grid: { color: COLORS.grid },
          ticks: { precision: 0 },
          beginAtZero: true
        }
      }
    }
  });
}

/**
 * Bar chart: Top organizations by endpoint count
 */
function buildTopOrgsChart(canvasId, labels, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Endpoints',
        data: data,
        backgroundColor: COLORS.accent + '88',
        borderColor: COLORS.accent,
        borderWidth: 1,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: COLORS.grid }, ticks: { precision: 0 } }
      }
    }
  });
}

/* ================================================================
   DataTables initialization helper
   ================================================================ */
function initDataTable(tableId, options = {}) {
  if (typeof $ === 'undefined' || typeof $.fn.DataTable === 'undefined') return;

  const defaults = {
    pageLength: 25,
    lengthMenu: [10, 25, 50, 100],
    language: {
      search: '',
      searchPlaceholder: '🔍 Search…',
      lengthMenu: 'Show _MENU_',
      info: 'Showing _START_–_END_ of _TOTAL_',
      paginate: {
        previous: '‹',
        next: '›'
      }
    },
    dom: '<"d-flex align-items-center px-3 pt-3 pb-2 gap-3"lf>rtip',
    responsive: true,
    order: [],
  };

  $(`#${tableId}`).DataTable({ ...defaults, ...options });
}

/**
 * Filter the scheduled automations table by organization
 */
function filterScheduledTable() {
  const filter = document.getElementById('filter-org-scheduled').value;
  const table = document.getElementById('table-scheduled');
  if (!table) return;
  
  const rows = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');
  
  for (let row of rows) {
    const org = row.getAttribute('data-org');
    if (filter === 'all' || org === filter) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  }
}

/* ================================================================
   DOM Ready
   ================================================================ */
document.addEventListener('DOMContentLoaded', () => {
  // Start status polling
  StatusRefresh.start();

  // Mobile sidebar toggle
  const toggleBtn = document.getElementById('sidebar-toggle');
  const sidebar = document.querySelector('.sidebar');
  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', () => sidebar.classList.toggle('open'));
  }

  // Tooltip init (Bootstrap 5)
  if (typeof bootstrap !== 'undefined') {
    document.querySelectorAll('[data-bs-toggle="tooltip"]')
      .forEach(el => new bootstrap.Tooltip(el));
  }
});
