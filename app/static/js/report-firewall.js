document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
});

async function fetchStats(env = null) {
    try {
        let url = '/firewall/api/stats';
        if (env) url += `?env=${env}`;
        const resp = await fetch(url);
        if (resp.ok) {
            const data = await resp.json();
            updateUI(data);
            if (!env && data.available_environments) {
                updateEnvSelector(data.available_environments, data.environment);
            }
        }
    } catch (err) {
        console.error("No previous data found", err);
    }
}

function updateEnvSelector(envs, currentEnv) {
    const selector = document.getElementById('envSelector');
    selector.innerHTML = '';
    envs.forEach(e => {
        const opt = document.createElement('option');
        opt.value = e;
        opt.innerText = e;
        if (e === currentEnv) {
            opt.selected = true;
        }
        selector.appendChild(opt);
    });
}

function changeEnvironment() {
    const env = document.getElementById('envSelector').value;
    if (env) {
        fetchStats(env);
    }
}

function updateUI(data) {

    // Format Date
    if (data.collected_at) {
        const d = new Date(data.collected_at);
        document.getElementById('lastScanTime').innerText = `Last Update: ${d.toLocaleString()}`;
    }

    // Rating
    const score = data.rating.score;
    const grade = data.rating.grade;
    const breakdown = data.rating.breakdown || [];

    // SOC Metrics
    const totalActive = data.soc_metrics.total_active;
    const withIps = data.soc_metrics.with_ips;
    const ipsPercent = totalActive > 0 ? Math.round((withIps / totalActive) * 100) : 0;

    document.getElementById('totalActive').innerText = totalActive;
    document.getElementById('noLog').innerText = data.soc_metrics.no_log;
    document.getElementById('ipsCov').innerText = ipsPercent + '%';

    // IPS Coverage color
    const ipsCovEl = document.getElementById('ipsCov');
    if (ipsPercent < 50) ipsCovEl.style.color = 'var(--fgt-red)';
    else if (ipsPercent < 80) ipsCovEl.style.color = '#f97316';
    else ipsCovEl.style.color = 'var(--fgt-green)';

    // Findings processing
    let failCount = 0;
    let warnCount = 0;
    
    data.findings.forEach(f => {
        if (f.severity === 'Critical' || f.severity === 'High') {
            failCount++;
        } else {
            warnCount++;
        }
    });

    document.getElementById('failCount').innerText = failCount;
    document.getElementById('warnCount').innerText = warnCount;
    document.getElementById('passCount').innerText = Math.max(0, totalActive - failCount - warnCount);

    // VPN Metrics
    if (data.vpn_metrics) {
        document.getElementById('vpnTotal').innerText = data.vpn_metrics.up + data.vpn_metrics.down;
        document.getElementById('vpnUp').innerText = data.vpn_metrics.up;
        document.getElementById('vpnDown').innerText = data.vpn_metrics.down;

        // Salva os túneis globalmente para o Modal
        window.vpnTunnels = data.vpn_metrics.tunnels || [];
        
        // Remove os tooltips antigos (agora usamos o modal on click)
        const upContainer = document.getElementById('vpnUpContainer');
        const downContainer = document.getElementById('vpnDownContainer');
        if (upContainer) upContainer.removeAttribute('title');
        if (downContainer) downContainer.removeAttribute('title');
    }

    // Charts
    renderScoreChart(score, grade, breakdown);
    renderCharts(data.summary, data.soc_metrics);

    // Policy Health KPIs
    const summary = data.summary || {};
    const soc = data.soc_metrics || {};
    const noTrafficTotal = (summary.unused || 0) + (summary.never_used || 0);

    const setKpi = (id, val) => { const el = document.getElementById(id); if(el) el.innerText = val; };
    setKpi('kpiAnyAny',    summary.any_any   || 0);
    setKpi('kpiNoIps',     summary.no_ips    || 0);
    setKpi('kpiNoTraffic', noTrafficTotal);
    setKpi('kpiDisabled',  soc.disabled      || 0);

    // Cores dinâmicas nos KPIs
    const kpiColors = [
        { id: 'kpiAnyAny',    val: summary.any_any   || 0, el: document.querySelector('.kpi-critical .kpi-value') },
        { id: 'kpiNoIps',     val: summary.no_ips    || 0, el: document.querySelector('.kpi-high .kpi-value')     },
        { id: 'kpiNoTraffic', val: noTrafficTotal,         el: document.querySelector('.kpi-warning .kpi-value')   },
        { id: 'kpiDisabled',  val: soc.disabled || 0,      el: document.querySelector('.kpi-muted .kpi-value')     },
    ];

    
    // Insights
    if (data.is_ai_generated) {
        document.getElementById('aiBadge').style.display = 'block';
    } else {
        document.getElementById('aiBadge').style.display = 'none';
    }
    populateInsights(data.insights);

    // Global variable for policies
    window.allPolicies = data.processed_policies || [];
    
    // Store current data for AI request
    window.currentStats = {
        summary: data.summary,
        score: score,
        total_active: totalActive
    };

    // Render Policies Table
    setFilter('all');
}

function populateInsights(insights) {
    const list = document.getElementById('insightsList');
    list.innerHTML = '';
    if(!insights || insights.length === 0) {
        list.innerHTML = '<li>Nenhum insight disponível.</li>';
        return;
    }
    insights.forEach(text => {
        let iconColor = 'var(--fgt-blue)';
        let iconName = 'info';
        
        if(text.includes('Crítica') || text.includes('Alto Risco')) { iconColor = 'var(--fgt-red)'; iconName = 'alert-triangle'; }
        else if(text.includes('Excelente')) { iconColor = 'var(--fgt-green)'; iconName = 'check-circle'; }
        else if(text.includes('Navegação Insegura') || text.includes('Falta de Proteção')) { iconColor = '#f97316'; iconName = 'shield-alert'; }

        const li = document.createElement('li');
        li.innerHTML = `<i data-lucide="${iconName}" class="insights-icon" style="color: ${iconColor};"></i> <span>${text}</span>`;
        list.appendChild(li);
    });
    if(window.lucide) window.lucide.createIcons();
}

let vulnChart, typeChart, scoreChart;

function renderScoreChart(score, grade, breakdown) {
    const colorMap = {
        'A': '#34c759',
        'B': '#a4c935',
        'C': '#ff9500',
        'D': '#ffcc00',
        'F': '#ff3b30'
    };
    const color = colorMap[grade] || '#0ea5e9';

    if(scoreChart) scoreChart.destroy();
    
    const options = {
        series: [score],
        chart: { type: 'radialBar', height: 260, animations: { enabled: true, easing: 'easeinout', speed: 800 } },
        plotOptions: {
            radialBar: {
                hollow: { size: '65%' },
                dataLabels: {
                    name: { show: true, fontSize: '14px', color: '#94a3b8', offsetY: 20 },
                    value: { show: true, fontSize: '38px', color: '#f8fafc', fontWeight: 700, offsetY: -10, formatter: function(val) { return val; } }
                },
                track: { background: 'rgba(255,255,255,0.05)' }
            }
        },
        fill: { type: 'gradient', gradient: { shade: 'dark', type: 'horizontal', colorStops: [ { offset: 0, color: color, opacity: 1 }, { offset: 100, color: color, opacity: 0.8 } ] } },
        stroke: { lineCap: 'round' },
        labels: ['Score'],
    };

    scoreChart = new ApexCharts(document.querySelector("#scoreGauge"), options);
    scoreChart.render();

    document.getElementById('ratingGrade').innerText = grade;
    document.getElementById('ratingGrade').style.color = color;

    // Atualiza tooltip com breakdown da nota
    buildRatingTooltip(score, grade, color, breakdown);
}

function buildRatingTooltip(score, grade, color, breakdown) {
    const tooltipEl = document.getElementById('ratingTooltip');
    if (!tooltipEl) return;

    const gradeDescriptions = {
        'A': 'Excelente — Ambiente bem configurado e seguro.',
        'B': 'Bom — Pequenas melhorias necessárias.',
        'C': 'Razoável — Riscos moderados identificados.',
        'D': 'Insatisfatório — Riscos significativos presentes.',
        'F': 'Crítico — Ação imediata necessária!'
    };

    const severityColors = {
        'insecure_admin': '#ff3b30',
        'any_any':        '#ff3b30',
        'no_ips':         '#f97316',
        'web_risk':       '#f97316',
        'service_all':    '#ffcc00',
        'unused':         '#94a3b8',
        'never_used':     '#94a3b8',
        'low_timeout':    '#94a3b8'
    };

    let rowsHtml = '';
    if (breakdown.length === 0) {
        rowsHtml = '<div style="color:#34c759; margin-top:8px;">✅ Nenhuma penalidade aplicada.</div>';
    } else {
        breakdown.forEach(item => {
            const barWidth = Math.min(100, Math.round((item.impact / 50) * 100));
            const c = severityColors[item.key] || '#94a3b8';
            rowsHtml += `
                <div style="margin-top:10px;">
                    <div style="display:flex; justify-content:space-between; font-size:0.78rem; margin-bottom:3px;">
                        <span style="color:#e2e8f0;">${item.label}</span>
                        <span style="color:${c}; font-weight:600;">-${item.impact}pts &nbsp;<span style="color:#64748b;">(${item.count}x)</span></span>
                    </div>
                    <div style="background:rgba(255,255,255,0.08); border-radius:4px; height:5px; overflow:hidden;">
                        <div style="width:${barWidth}%; height:100%; background:${c}; border-radius:4px; transition:width 0.5s;"></div>
                    </div>
                </div>`;
        });
    }

    tooltipEl.innerHTML = `
        <div style="font-weight:700; font-size:0.9rem; color:${color}; display:flex; align-items:center; gap:6px;">
            <span style="font-size:1.3rem;">${grade}</span>
            <span style="font-size:1.1rem;">${score}/100</span>
        </div>
        <div style="font-size:0.78rem; color:#94a3b8; margin-top:4px; margin-bottom:10px;">${gradeDescriptions[grade] || ''}</div>
        <div style="font-size:0.75rem; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; border-top:1px solid #334155; padding-top:8px; margin-top:4px;">Penalidades aplicadas</div>
        ${rowsHtml}
    `;
}

function renderCharts(summary, socMetrics) {
    const criticalHigh = summary.insecure_admin + summary.any_any + summary.no_ips + summary.web_risk;
    const medium = summary.service_all;
    const low = summary.unused + summary.never_used + summary.low_timeout;

    const vulnOptions = {
        series: [criticalHigh, medium, low],
        chart: {
            type: 'donut',
            height: 190,
            fontFamily: 'Outfit, sans-serif',
            foreColor: '#94a3b8',
            events: {
                dataPointSelection: function(event, chartContext, config) {
                    const labels = ['critical_high', 'medium', 'low'];
                    const sel = labels[config.dataPointIndex];
                    if (sel === 'critical_high') setFilter('no_ips');
                    else if (sel === 'medium') setFilter('service_all');
                    else if (sel === 'low') setFilter('inactive');
                }
            }
        },
        labels: ['Critical/High', 'Medium', 'Low'],
        colors: ['#ff3b30', '#ff9500', '#0ea5e9'],
        legend: { position: 'bottom' },
        dataLabels: { enabled: false },
        plotOptions: { pie: { donut: { size: '65%' } } },
        stroke: { show: true, colors: ['#1e293b'], width: 2 },
        theme: { mode: 'dark' },
        tooltip: { theme: 'dark' }
    };

    if (vulnChart) vulnChart.destroy();
    vulnChart = new ApexCharts(document.querySelector("#vulnChart"), vulnOptions);
    vulnChart.render();

    // Corrigido: inclui no_ips com contagem correta do summary
    const noIpsCount   = summary.no_ips   || 0;
    const anyAnyCount  = summary.any_any  || 0;
    const svcAllCount  = summary.service_all || 0;
    const webRiskCount = summary.web_risk  || 0;
    const adminCount   = summary.insecure_admin || 0;
    const unusedCount  = (summary.unused || 0) + (summary.never_used || 0);

    const typeOptions = {
        series: [{ name: 'Ocorrências', data: [noIpsCount, anyAnyCount, svcAllCount, webRiskCount, adminCount, unusedCount] }],
        chart: {
            type: 'bar',
            height: 280,
            toolbar: { show: false },
            fontFamily: 'Outfit, sans-serif',
            foreColor: '#94a3b8',
            events: {
                dataPointSelection: function(event, chartContext, config) {
                    const filterMap = ['no_ips', 'any_any', 'service_all', 'web_risk', 'all', 'inactive'];
                    const sel = filterMap[config.dataPointIndex];
                    if (sel) setFilter(sel);
                }
            }
        },
        plotOptions: {
            bar: {
                borderRadius: 4,
                distributed: true,
                horizontal: true
            }
        },
        colors: ['#f97316', '#ff3b30', '#ffcc00', '#f97316', '#ff3b30', '#0ea5e9'],
        dataLabels: { enabled: true, style: { fontSize: '11px' } },
        xaxis: {
        categories: ['Sem IPS', 'Any-Any', 'Service ALL', 'Sem WebFilter', 'Admin Inseguro', 'Sem Tráfego']
        },
        legend: { show: false },
        theme: { mode: 'dark' },
        tooltip: { theme: 'dark' },
        grid: { borderColor: '#334155' }
    };

    if (typeChart) typeChart.destroy();
    typeChart = new ApexCharts(document.querySelector("#typeChart"), typeOptions);
    typeChart.render();
}

let currentFilter = 'all';

function setFilter(filterType) {
    currentFilter = filterType;
    let filtered = window.allPolicies;

    // Atualiza highlight dos botões
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('filter-active');
        if (btn.dataset.filter === filterType) btn.classList.add('filter-active');
    });
    
    if (filterType === 'inactive') {
        filtered = window.allPolicies.filter(p => p.risks.unused || p.risks.never_used);
    } else if (filterType === 'no_ips') {
        filtered = window.allPolicies.filter(p => p.risks.no_ips);
    } else if (filterType === 'web_risk') {
        filtered = window.allPolicies.filter(p => p.risks.web_risk);
    } else if (filterType === 'any_any') {
        filtered = window.allPolicies.filter(p => p.risks.any_any);
    } else if (filterType === 'service_all') {
        filtered = window.allPolicies.filter(p => p.risks.service_all);
    } else if (filterType === 'disabled') {
        filtered = window.allPolicies.filter(p => p.risks.disabled);
    } else if (filterType === 'unused_60d') {
        filtered = window.allPolicies.filter(p => p.risks.unused);
    }

    populatePoliciesTable(filtered, filterType);
}

function populatePoliciesTable(policies, filterType) {
    const tbody = document.getElementById('policiesTableBody');
    const emptyMsg = document.getElementById('tableEmptyMsg');
    tbody.innerHTML = '';

    if (policies.length === 0) {
        const filterLabels = {
            'no_ips': 'Sem IPS',
            'web_risk': 'Sem WebFilter',
            'any_any': 'Any-to-Any',
            'inactive': 'Sem Tráfego',
            'disabled': 'Desativadas',
            'unused_60d': 'Sem Tráfego há +60 dias',
            'service_all': 'Service ALL'
        };
        const label = filterLabels[filterType] || filterType;
        if (emptyMsg) {
            emptyMsg.style.display = 'flex';
            emptyMsg.querySelector('.empty-label').innerText = `Nenhuma regra encontrada para o filtro "${label}"`;
        }
        return;
    }
    if (emptyMsg) emptyMsg.style.display = 'none';

    policies.forEach(p => {
        const tr = document.createElement('tr');

        const isDisabled = p.risks.disabled || p.status === 'disable';
        
        let statusBadge = isDisabled
            ? '<span class="badge" style="background:rgba(100,116,139,0.2);color:#94a3b8;border-color:#475569;">Desativada</span>'
            : '<span style="color:var(--fgt-green); font-weight:600;">Ativa</span>';
        
        let riskTags = '';
        if(isDisabled)                         riskTags += '<span class="badge" style="background:rgba(100,116,139,0.15);color:#94a3b8;border:1px solid #475569;margin-right:2px;">Desativada</span>';
        if(p.risks.any_any)                    riskTags += '<span class="badge badge-critical" style="margin-right:2px;">Any-Any</span>';
        if(p.risks.no_ips)                     riskTags += '<span class="badge badge-high" style="margin-right:2px;">Sem IPS</span>';
        if(p.risks.web_risk)                   riskTags += '<span class="badge badge-high" style="margin-right:2px;">Sem WebFilter</span>';
        if(p.risks.service_all)                riskTags += '<span class="badge badge-medium" style="margin-right:2px;">Service ALL</span>';
        if(p.risks.unused)                     riskTags += '<span class="badge badge-medium" style="margin-right:2px;">Sem Tráfego +60d</span>';
        if(p.risks.never_used)                 riskTags += '<span class="badge badge-medium" style="margin-right:2px;">Sem Tráfego</span>';
        if(riskTags === '')                    riskTags  = '<span class="badge badge-low">OK</span>';

        tr.style.cursor = 'pointer';
        if (isDisabled) tr.style.opacity = '0.65';
        tr.onclick = () => showPolicyDetails(p.id);

        tr.innerHTML = `
            <td>${p.id}</td>
            <td><strong>${p.name}</strong></td>
            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${p.src}">${p.src}</td>
            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${p.dst}">${p.dst}</td>
            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${p.service}">${p.service}</td>
            <td>${statusBadge}</td>
            <td style="font-size: 0.8rem; color: #666;">${p.last_used}</td>
            <td>${riskTags}</td>
        `;
        tbody.appendChild(tr);
    });
}

function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fwmProfile(icon, label, active, name) {
    const c   = active ? 'var(--fgt-green)' : 'var(--fgt-red)';
    const bg  = active ? 'rgba(52,199,89,0.1)' : 'rgba(255,59,48,0.08)';
    const chk = active ? 'bi-check-circle-fill' : 'bi-x-circle-fill';
    const sub = (active && name) ? `<span class="fwm-profile-sub" title="${escHtml(name)}">${escHtml(name)}</span>` : '';
    return `<div class="fwm-profile-card" style="border-color:${c}30;background:${bg};">
      <i class="bi ${icon} fwm-profile-icon" style="color:${c};"></i>
      <div class="fwm-profile-info">
        <div class="fwm-profile-name">${label}</div>
        <div class="fwm-profile-status"><i class="bi ${chk}" style="color:${c};"></i>${active ? 'Ativo' : 'Ausente'}</div>
        ${sub}
      </div>
    </div>`;
}

function fwmProfileLog(log) {
    const val = (log || 'disable').toLowerCase();
    const on  = val !== 'disable';
    const c   = on ? 'var(--fgt-green)' : '#f59e0b';
    const bg  = on ? 'rgba(52,199,89,0.1)' : 'rgba(245,158,11,0.08)';
    const chk = on ? 'bi-check-circle-fill' : 'bi-exclamation-circle-fill';
    const lbl = { all: 'Completo', utm: 'UTM Only', disable: 'Desabilitado' }[val] || val;
    return `<div class="fwm-profile-card" style="border-color:${c}30;background:${bg};">
      <i class="bi bi-journal-text fwm-profile-icon" style="color:${c};"></i>
      <div class="fwm-profile-info">
        <div class="fwm-profile-name">Log de Tráfego</div>
        <div class="fwm-profile-status"><i class="bi ${chk}" style="color:${c};"></i>${lbl}</div>
      </div>
    </div>`;
}

function fwmProfileBool(icon, label, active) {
    const c   = active ? 'var(--fgt-green)' : '#64748b';
    const bg  = active ? 'rgba(52,199,89,0.1)' : 'rgba(100,116,139,0.07)';
    const chk = active ? 'bi-check-circle-fill' : 'bi-dash-circle';
    return `<div class="fwm-profile-card" style="border-color:${c}30;background:${bg};">
      <i class="bi ${icon} fwm-profile-icon" style="color:${c};"></i>
      <div class="fwm-profile-info">
        <div class="fwm-profile-name">${label}</div>
        <div class="fwm-profile-status"><i class="bi ${chk}" style="color:${c};"></i>${active ? 'Habilitado' : 'Desabilitado'}</div>
      </div>
    </div>`;
}

function showPolicyDetails(id) {
    const p = window.allPolicies.find(x => x.id === id);
    if (!p) return;

    const isDisabled = p.risks.disabled || p.status === 'disable';
    const isDeny     = ['deny', 'drop'].includes((p.action || '').toLowerCase());

    const split      = s => s ? s.split(',').map(x => x.trim()).filter(Boolean) : [];
    const srcList    = split(p.src);
    const dstList    = split(p.dst);
    const svcList    = split(p.service);
    const srcIfList  = split(p.src_intf);
    const dstIfList  = split(p.dst_intf);

    const makeTags = (items, cls, max = 12) => {
        if (!items.length) return `<span class="fw-tag-empty">qualquer</span>`;
        const vis  = items.slice(0, max);
        const rest = items.length - max;
        let html   = vis.map(t => `<span class="fw-tag ${cls}" title="${escHtml(t)}">${escHtml(t)}</span>`).join('');
        if (rest > 0) html += `<span class="fw-tag fw-tag-more">+${rest}</span>`;
        return html;
    };

    const actionColor = isDeny ? 'var(--fgt-red)' : 'var(--fgt-green)';
    const actionIcon  = isDeny ? 'bi-ban' : 'bi-arrow-right-circle-fill';
    const actionText  = (p.action || 'accept').toUpperCase();
    const statusBg    = isDisabled ? 'rgba(100,116,139,0.2)' : 'rgba(52,199,89,0.15)';
    const statusColor = isDisabled ? '#94a3b8' : 'var(--fgt-green)';
    const statusText  = isDisabled ? 'DESATIVADA' : 'ATIVA';
    const riskCount   = Object.entries(p.risks).filter(([k, v]) => v && k !== 'disabled').length;

    const srcIfText = srcIfList.length ? srcIfList.join(' / ') : null;
    const dstIfText = dstIfList.length ? dstIfList.join(' / ') : null;

    // ── Header ────────────────────────────────────────────────────
    let html = `
    <div class="fwm-header">
      <div class="fwm-title-row">
        <span class="fwm-policy-id">ID ${p.id}</span>
        <span class="fwm-policy-name">${escHtml(p.name)}</span>
      </div>
      <div class="fwm-badges">
        <span class="fwm-badge-status" style="background:${statusBg};color:${statusColor};border-color:${statusColor}40;">
          <i class="bi ${isDisabled ? 'bi-toggle-off' : 'bi-toggle-on'}"></i>${statusText}
        </span>
        <span class="fwm-badge-action" style="background:${isDeny ? 'rgba(255,59,48,0.15)' : 'rgba(52,199,89,0.15)'};color:${actionColor};border-color:${actionColor}40;">
          <i class="bi ${actionIcon}"></i>${actionText}
        </span>
        ${riskCount > 0
          ? `<span class="fwm-badge-risk"><i class="bi bi-exclamation-triangle-fill"></i>${riskCount} risco${riskCount > 1 ? 's' : ''}</span>`
          : `<span class="fwm-badge-ok"><i class="bi bi-patch-check-fill"></i>Sem riscos</span>`}
      </div>
    </div>`;

    // ── Traffic Flow ──────────────────────────────────────────────
    html += `<div class="fwm-section">
      <div class="fwm-section-label"><i class="bi bi-diagram-2"></i> Fluxo de Tráfego</div>

      <!-- Interface banner -->
      <div class="fwm-intf-bar">
        <div class="fwm-intf-node fwm-intf-node-src">
          <i class="bi bi-hdd-network fwm-intf-icon"></i>
          <div class="fwm-intf-role">Interface Origem</div>
          ${srcIfText
            ? `<div class="fwm-intf-name">${escHtml(srcIfText)}</div>`
            : `<div class="fwm-intf-name-empty">não informada</div>`}
        </div>

        <div class="fwm-intf-connector">
          <div class="fwm-intf-svc-list">${makeTags(svcList, 'fw-tag-svc', 10)}</div>
          <div class="fwm-intf-arrow">
            <div class="fwm-intf-line"></div>
            <div class="fwm-intf-action-pill" style="color:${actionColor};border-color:${actionColor}50;background:${isDeny ? 'rgba(255,59,48,0.13)' : 'rgba(52,199,89,0.13)'};">
              <i class="bi ${actionIcon}"></i>${actionText}
            </div>
            <div class="fwm-intf-line"></div>
          </div>
        </div>

        <div class="fwm-intf-node fwm-intf-node-dst">
          <i class="bi bi-hdd-network fwm-intf-icon"></i>
          <div class="fwm-intf-role">Interface Destino</div>
          ${dstIfText
            ? `<div class="fwm-intf-name">${escHtml(dstIfText)}</div>`
            : `<div class="fwm-intf-name-empty">não informada</div>`}
        </div>
      </div>

      <!-- Address columns -->
      <div class="fwm-addr-grid">
        <div class="fwm-addr-col">
          <div class="fwm-addr-col-label"><i class="bi bi-box-arrow-in-right" style="color:#7dd3fc;"></i> Endereços de Origem</div>
          <div class="fwm-addr-tags">${makeTags(srcList, 'fw-tag-src')}</div>
        </div>
        <div class="fwm-addr-col fwm-addr-col-svc">
          <div class="fwm-addr-col-label" style="text-align:center;"><i class="bi bi-diagram-3" style="color:#94a3b8;"></i> Serviços / Portas</div>
          <div class="fwm-addr-tags fwm-addr-tags-center">${makeTags(svcList, 'fw-tag-svc')}</div>
        </div>
        <div class="fwm-addr-col">
          <div class="fwm-addr-col-label"><i class="bi bi-box-arrow-right" style="color:#d8b4fe;"></i> Endereços de Destino</div>
          <div class="fwm-addr-tags">${makeTags(dstList, 'fw-tag-dst')}</div>
        </div>
      </div>
    </div>`;

    // ── Bottom: 2-column (profiles left, risks right) ─────────────
    const risks = [];
    if (isDisabled)          risks.push({ sev:'muted',    icon:'bi-toggle-off',          title:'Regra Desativada',    msg:'Não está processando tráfego. Se desnecessária, remova para reduzir a superfície de ataque.' });
    if (p.risks.any_any)     risks.push({ sev:'critical', icon:'bi-exclamation-octagon', title:'Any-to-Any',          msg:'Origem e destino como "ALL" — permite tráfego irrestrito. Restrinja ao mínimo necessário. (NIST PR.AC-4 / CIS v8 #3.3)' });
    if (p.risks.service_all) risks.push({ sev:'high',     icon:'bi-diagram-3',           title:'Service ALL',         msg:'Todas as portas e protocolos liberados. Especifique apenas os serviços necessários. (NIST PR.PT-3 / CIS v8 #4.8)' });
    if (p.risks.no_ips)      risks.push({ sev:'high',     icon:'bi-shield-x',            title:'Sem IPS',             msg:'Tráfego exposto à Internet sem inspeção de intrusões. Adicione um sensor IPS. (NIST DE.CM-1 / CIS v8 #13.2)' });
    if (p.risks.web_risk)    risks.push({ sev:'high',     icon:'bi-globe2',              title:'Sem WebFilter',       msg:'Tráfego HTTP/HTTPS outbound sem filtro de conteúdo. Habilite um WebFilter Profile. (NIST PR.PT-4 / CIS v8 #9.6)' });
    if (p.risks.unused)      risks.push({ sev:'medium',   icon:'bi-clock-history',       title:'Sem Tráfego +60d',    msg:'Regra inativa há mais de 60 dias. Considere desativar ou remover. (NIST PR.IP-1 / CIS v8 #12.4)' });
    if (p.risks.never_used)  risks.push({ sev:'medium',   icon:'bi-slash-circle',        title:'Nunca Utilizada',     msg:'Regra criada mas jamais gerou tráfego. Recomendamos remoção para limpeza do ruleset. (NIST PR.IP-1 / CIS v8 #12.4)' });

    const riskCols  = { critical:'#ff3b30', high:'#f97316', medium:'#f59e0b', muted:'#94a3b8' };
    const riskBgs   = { critical:'rgba(255,59,48,0.07)', high:'rgba(249,115,22,0.07)', medium:'rgba(245,158,11,0.07)', muted:'rgba(100,116,139,0.07)' };

    let risksHtml = '';
    if (risks.length === 0) {
        risksHtml = `<div class="fwm-ok-row"><i class="bi bi-patch-check-fill" style="font-size:1.1rem;color:var(--fgt-green);"></i><span>Nenhum risco identificado — regra dentro das melhores práticas.</span></div>`;
    } else {
        risks.forEach(r => {
            const c  = riskCols[r.sev]  || '#94a3b8';
            const bg = riskBgs[r.sev] || 'rgba(100,116,139,0.07)';
            risksHtml += `
            <div class="fwm-risk-row" style="border-left-color:${c};background:${bg};">
              <i class="bi ${r.icon}" style="color:${c};font-size:1rem;flex-shrink:0;margin-top:2px;"></i>
              <div class="fwm-risk-content">
                <div class="fwm-risk-title" style="color:${c};">${r.title}</div>
                <div class="fwm-risk-msg">${r.msg}</div>
              </div>
            </div>`;
        });
    }

    html += `
    <div class="fwm-bottom-grid">
      <div class="fwm-col-profiles">
        <div class="fwm-section-label"><i class="bi bi-shield-shaded"></i> Perfis de Segurança</div>
        <div class="fwm-profiles-stack">
          ${fwmProfile('bi-shield-shaded',  'IPS',       p.has_ips, p.ips_sensor || '')}
          ${fwmProfile('bi-funnel-fill',    'WebFilter', p.has_wf,  p.webfilter  || '')}
          ${fwmProfileLog(p.log)}
          ${p.nat !== undefined ? fwmProfileBool('bi-arrow-left-right', 'NAT', p.nat) : ''}
        </div>
      </div>
      <div class="fwm-col-risks">
        <div class="fwm-section-label"><i class="bi bi-clipboard2-pulse"></i> Compliance &amp; Riscos</div>
        ${risksHtml}
      </div>
    </div>`;

    // ── Footer ────────────────────────────────────────────────────
    html += `
    <div class="fwm-footer">
      <div class="fwm-footer-item"><i class="bi bi-clock-history"></i> Último uso: <strong>${escHtml(p.last_used || '—')}</strong></div>
      ${p.comments ? `<div class="fwm-footer-item fwm-comment"><i class="bi bi-chat-left-text"></i> ${escHtml(p.comments)}</div>` : ''}
    </div>`;

    const hdr = document.querySelector('#policyModal .modal-header > div');
    if (hdr) hdr.innerHTML = `<i class="bi bi-shield-shaded" style="color:var(--fgt-blue);margin-right:6px;"></i>Regra <span style="color:#94a3b8;font-weight:400;">#${p.id}</span>`;

    document.getElementById('policyModalBody').innerHTML = html;
    openModal('policyModal');
}

// VPN Modal Logic
function showVpnModal(status) {
    if (!window.vpnTunnels) return;
    const filtered = window.vpnTunnels.filter(v => v.status === status);
    const titleStatus = status.toUpperCase();
    const color = status === 'up' ? 'var(--fgt-green)' : 'var(--fgt-red)';
    const icon = status === 'up' ? 'check-circle' : 'x-circle';
    
    document.getElementById('vpnModalTitle').innerHTML = `<i data-lucide="${icon}" style="width: 18px; margin-right: 6px; color: ${color};"></i> Túneis VPN - ${titleStatus}`;
    
    let html = '';
    if (filtered.length === 0) {
        html = `<div style="text-align: center; padding: 20px; color: #94a3b8;">Nenhum túnel ${titleStatus} encontrado.</div>`;
    } else {
        html = `
        <table class="custom-table" style="width: 100%; border-collapse: collapse; margin-top: 10px;">
            <thead>
                <tr>
                    <th style="text-align: left; padding: 8px; border-bottom: 1px solid var(--fgt-border); color: #94a3b8; font-size: 0.8rem;">Nome da VPN</th>
                    <th style="text-align: left; padding: 8px; border-bottom: 1px solid var(--fgt-border); color: #94a3b8; font-size: 0.8rem;">Gateway</th>
                </tr>
            </thead>
            <tbody>
        `;
        filtered.forEach(vpn => {
            html += `
                <tr>
                    <td style="padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.05); color: #e2e8f0; font-weight: 500;">${vpn.name}</td>
                    <td style="padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.05); color: #94a3b8;">${vpn.gateway || 'N/A'}</td>
                </tr>
            `;
        });
        html += `</tbody></table>`;
    }
    
    document.getElementById('vpnModalBody').innerHTML = html;
    openModal('vpnModal');
    if(window.lucide) { lucide.createIcons(); }
}

function openModal(id) {
    document.getElementById(id).style.display = 'flex';
}
function closeModal(id) {
    document.getElementById(id).style.display = 'none';
}

async function submitChangePassword() {
    const current_password = document.getElementById('currentPwd').value;
    const new_password = document.getElementById('newPwd').value;

    if(!current_password || !new_password) {
        alert('Preencha os dois campos.'); return;
    }

    try {
        const response = await fetch('/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password, new_password })
        });
        const result = await response.json();
        
        if(response.ok) {
            alert(result.message);
            closeModal('pwdModal');
            document.getElementById('currentPwd').value = '';
            document.getElementById('newPwd').value = '';
        } else {
            alert(result.error || 'Erro ao trocar senha.');
        }
    } catch(e) {
        alert('Erro de comunicação.');
    }
}

async function requestAIInsights() {
    if (!window.currentStats) return;

    const btn = document.getElementById('btnGenerateInsights');
    const list = document.getElementById('insightsList');
    
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader" class="spin" style="width: 12px; margin-right: 4px;"></i> Gerando...';
    if(window.lucide) window.lucide.createIcons();

    try {
        const response = await fetch('/firewall/api/generate_insights', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(window.currentStats)
        });
        const result = await response.json();

        if (response.ok && result.insights) {
            populateInsights(result.insights);
            document.getElementById('aiBadge').style.display = 'block';
        } else {
            alert(result.message || 'Erro ao gerar insights.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro ao conectar com o servidor.');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="sparkles" style="width: 12px; margin-right: 4px;"></i> Gerar Insights';
        if(window.lucide) window.lucide.createIcons();
    }
}
