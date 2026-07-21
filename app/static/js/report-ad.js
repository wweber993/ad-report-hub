let allUsers = [];
let filteredUsers = [];
let stats = {};
let sortColumn = null;
let sortDirection = 'asc';
let createdDaysFilter = null;
let currentPage = 0;
const PAGE_SIZE = 50;
let currentFilters = {
    all: true,
    privileged: false,
    compliant: false,
    nonCompliant: false,
    lockedOut: false,
    neverExpires: false,
    disabled: false,
    inactive90: false
};

function _csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

const userListBody = document.getElementById('userListBody');
const searchInput = document.getElementById('userSearch');
const refreshBtn = document.getElementById('refreshBtn');
const exportBtn = document.getElementById('exportBtn');
const envFilter = document.getElementById('envFilter');

// Charts
let deptChart = null;

async function fetchData() {
    try {
        const [usersRes, statsRes] = await Promise.all([
            fetch('/ad/api/users'),
            fetch('/ad/api/stats')
        ]);

        allUsers = await usersRes.json();
        stats = await statsRes.json();

        if (allUsers.length === 0 && !stats.total) {
            showEmptyState();
            return;
        }

        hideEmptyState();
        updateDashboard();
    } catch (err) {
        console.error('Error fetching data:', err);
    }
}

function showEmptyState() {
    document.getElementById('summaryCards').innerHTML = '';
    const existing = document.getElementById('emptyState');
    if (existing) return;
    const es = document.createElement('div');
    es.id = 'emptyState';
    es.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;padding:80px 20px;text-align:center;';
    es.innerHTML = `
        <div style="width:80px;height:80px;border-radius:24px;background:rgba(56,189,248,0.08);display:flex;align-items:center;justify-content:center;margin-bottom:24px;">
            <i class="bi bi-inbox" style="font-size:2.2rem;color:#38bdf8;"></i>
        </div>
        <h4 style="color:#f8fafc;margin-bottom:12px;font-size:1.2rem;">Nenhum dado importado ainda</h4>
        <p style="color:#94a3b8;max-width:480px;font-size:.9rem;line-height:1.7;">
            Execute o coletor PowerShell no seu servidor Active Directory para importar o primeiro relatório.
            Os dados aparecerão automaticamente aqui.
        </p>
        <div style="margin-top:28px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:20px 28px;text-align:left;">
            <div style="font-size:.75rem;text-transform:uppercase;letter-spacing:1px;color:#38bdf8;margin-bottom:10px;">Como começar</div>
            <code style="color:#94a3b8;font-size:.82rem;">
                powershell -ExecutionPolicy Bypass -File .\scripts\report_ad.ps1
            </code>
        </div>
    `;
    document.querySelector('.fade-up').prepend(es);
}

function hideEmptyState() {
    document.getElementById('emptyState')?.remove();
}

function updateDashboard() {
    populateEnvFilter();
    renderSummaryCards();
    renderCharts();
    updateSecurityHealth();
    applyFiltersAndSearch();
    lucide.createIcons();
}

function populateEnvFilter() {
    const currentValue = envFilter.value;
    envFilter.innerHTML = '<option value="">Todos Ambientes</option>' + 
        (stats.environments || []).map(env => 
            `<option value="${env}" ${env === currentValue ? 'selected' : ''}>${env}</option>`
        ).join('');
}

function renderSummaryCards() {
    const container = document.getElementById('summaryCards');
    const c = stats.creationStats || { '7d': 0, '30d': 0, '60d': 0 };

    const cards = [
        { label: 'Total Usuários',    value: stats.total,          icon: 'users',          color: 'primary', filter: 'all' },
        { label: 'Usuários Ativos',   value: stats.active,         icon: 'user-check',     color: 'success', filter: 'compliant' },
        { label: 'Desativados',       value: stats.inactive,       icon: 'user-x',         color: 'muted',   filter: 'disabled' },
        { label: 'Bloqueados',        value: stats.lockedOut,      icon: 'lock',           color: 'danger',  filter: 'lockedOut' },
        { label: 'Privilegiados',     value: stats.privileged,     icon: 'shield-check',   color: 'danger',  filter: 'privileged' },
        { label: 'Não Conformes',     value: stats.nonCompliant,   icon: 'alert-triangle', color: 'warning', filter: 'nonCompliant' },
        { label: 'Usuários em Risco', value: stats.highRiskUsers,  icon: 'shield-alert',   color: 'danger' },
        { label: 'Novos (30 dias)',    value: c['30d'],             icon: 'calendar-plus',  color: 'primary', filterDays: 30 },
    ];

    container.innerHTML = cards.map(card => {
        const onclick = card.filter
            ? `onclick="setFilter('${card.filter}')"`
            : card.filterDays
                ? `onclick="setCreatedFilter(${card.filterDays})"`
                : '';
        return `
        <div class="glass-card stat-card card-${card.color}" ${onclick ? 'style="cursor:pointer"' : ''} ${onclick}>
            <div class="stat-icon">
                <i data-lucide="${card.icon}"></i>
            </div>
            <div class="stat-content">
                <div class="stat-value">${(card.value ?? 0).toLocaleString()}</div>
                <div class="stat-label">${card.label}</div>
            </div>
        </div>`;
    }).join('');
}

function updateSecurityHealth() {
    const circle = document.getElementById('healthCircle');
    const value = document.getElementById('healthValue');
    const status = document.getElementById('healthStatus');
    const insightsList = document.getElementById('healthInsightsList');
    
    const score = stats.healthScore || 0;
    circle.style.setProperty('--health-percent', `${score}%`);
    value.innerText = `${score}%`;
    
    if (score > 80) {
        status.innerText = 'Ambiente Saudável';
        status.className = 'text-success fw-bold small';
    } else if (score > 50) {
        status.innerText = 'Atenção Requerida';
        status.className = 'text-warning fw-bold small';
    } else {
        status.innerText = 'Risco Crítico';
        status.className = 'text-danger fw-bold small';
    }

    insightsList.innerHTML = (stats.healthInsights || []).map(insight => `
        <li class="mb-2 d-flex align-items-start gap-2">
            <i data-lucide="info" style="width: 12px; margin-top: 3px; flex-shrink: 0;"></i>
            <span>${insight}</span>
        </li>
    `).join('');
}

function renderCharts() {
    const deptOptions = {
        series: [{
            name: 'Não Conformes',
            data: (stats.topDepartments || []).map(d => d.count)
        }],
        chart: { type: 'bar', height: 300, toolbar: { show: false }, background: 'transparent' },
        plotOptions: { bar: { borderRadius: 8, horizontal: true, barHeight: '60%' } },
        colors: ['#38bdf8'],
        xaxis: { categories: (stats.topDepartments || []).map(d => d.name), labels: { style: { colors: '#94a3b8' } } },
        yaxis: { labels: { style: { colors: '#94a3b8' } } },
        grid: { borderColor: 'rgba(148, 163, 184, 0.1)' },
        theme: { mode: 'dark' }
    };

    if (deptChart) deptChart.destroy();
    deptChart = new ApexCharts(document.querySelector("#deptChart"), deptOptions);
    deptChart.render();
}

function applyFiltersAndSearch() {
    const headerTerm = searchInput.value.toLowerCase();
    const tableSearchInput = document.getElementById('tableSearch');
    const tableTerm = tableSearchInput ? tableSearchInput.value.toLowerCase() : '';
    const term = tableTerm || headerTerm;
    const env = envFilter.value;
    
    filteredUsers = allUsers.filter(user => {
        const matchesSearch = !term || 
            (user.DisplayName && user.DisplayName.toLowerCase().includes(term)) ||
            (user.Username && user.Username.toLowerCase().includes(term)) ||
            (user.Email && user.Email.toLowerCase().includes(term)) ||
            (user.DisplayDepartment && user.DisplayDepartment.toLowerCase().includes(term));
            
        const matchesEnv = !env || user.Environment === env;
        
        let matchesStatus = true;
        if (currentFilters.privileged && !user.isPrivileged) matchesStatus = false;
        if (currentFilters.nonCompliant && user.isCompliant) matchesStatus = false;
        if (currentFilters.compliant && !user.isCompliant) matchesStatus = false;
        if (currentFilters.lockedOut && !user.LockedOut) matchesStatus = false;
        if (currentFilters.neverExpires && !user.PasswordNeverExpires) matchesStatus = false;
        if (currentFilters.disabled && user.Enabled) matchesStatus = false;
        if (currentFilters.inactive90 && (user.DaysSinceLastLogon === null || user.DaysSinceLastLogon < 90)) matchesStatus = false;

        let matchesCreated = true;
        if (createdDaysFilter !== null) {
            if (!user.AccountCreated || user.AccountCreated === 'Nunca') {
                matchesCreated = false;
            } else {
                const createdDate = new Date(user.AccountCreated);
                const now = new Date();
                const diffTime = Math.abs(now - createdDate);
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                if (diffDays > createdDaysFilter) matchesCreated = false;
            }
        }

        return matchesSearch && matchesEnv && matchesStatus && matchesCreated;
    });

    currentPage = 0;
    applySort();
    updateFilterUI();
    renderTable();
}

function updateFilterUI() {
    const buttons = ['All', 'Privileged', 'Compliant', 'NonCompliant', 'LockedOut', 'NeverExpires', 'Disabled', 'Inactive90'];
    buttons.forEach(b => {
        const btn = document.getElementById(`filter${b}`);
        if (btn) btn.classList.remove('active');
    });

    const activeKey = Object.keys(currentFilters).find(k => currentFilters[k]);
    if (activeKey) {
        const activeBtn = document.getElementById(`filter${activeKey.charAt(0).toUpperCase() + activeKey.slice(1)}`);
        if (activeBtn) activeBtn.classList.add('active');

        const kpiCards = document.querySelectorAll('#summaryCards .stat-card');
        kpiCards.forEach(card => {
            card.style.borderColor = 'var(--card-border)';
            card.style.background = 'var(--card-bg)';
        });

        const activeCard = Array.from(kpiCards).find(c => (c.getAttribute('onclick') || '').includes(`'${activeKey}'`));
        if (activeCard) {
            activeCard.style.borderColor = 'var(--accent-primary)';
            activeCard.style.background = 'rgba(56, 189, 248, 0.05)';
        }
    }

    // Highlight creation filter card (Novos 30d)
    const kpiCards = document.querySelectorAll('#summaryCards .stat-card');
    kpiCards.forEach(card => {
        const onclickAttr = card.getAttribute('onclick') || '';
        if (onclickAttr.includes('setCreatedFilter')) {
            const isActive = createdDaysFilter === 30;
            if (!isActive) {
                card.style.borderColor = 'var(--card-border)';
                card.style.background = 'var(--card-bg)';
            } else {
                card.style.borderColor = 'var(--accent-primary)';
                card.style.background = 'rgba(56, 189, 248, 0.1)';
            }
        }
    });
}

function renderTable() {
    const start = currentPage * PAGE_SIZE;
    const pageUsers = filteredUsers.slice(start, start + PAGE_SIZE);
    const totalPages = Math.ceil(filteredUsers.length / PAGE_SIZE);

    userListBody.innerHTML = pageUsers.map(user => `
        <tr onclick="openUserDetails('${user.Username}')" style="cursor: pointer">
            <td>
                <div class="d-flex align-items-center gap-2">
                    <div class="stat-icon mb-0" style="width: 32px; height: 32px; font-size: 10px; border-radius: 8px; background: rgba(56, 189, 248, 0.05)">
                        ${(user.DisplayName || user.Username).substring(0, 2).toUpperCase()}
                    </div>
                    <div>
                        <div class="fw-bold d-flex align-items-center gap-1" style="font-size: 0.9rem">
                            ${user.DisplayName || user.Username}
                            ${user.isPrivileged ? '<i data-lucide="shield-alert" class="text-danger" style="width: 14px;" title="Usuário Privilegiado"></i>' : ''}
                            ${user.isException ? '<i data-lucide="shield-check" class="text-info" style="width: 14px;" title="Exceção Ativa"></i>' : ''}
                        </div>
                        <div class="small text-secondary" style="font-size: 0.75rem">${user.Username}</div>
                    </div>
                </div>
            </td>
            <td class="small">${user.Email || '-'}</td>
            <td class="small">${user.DisplayDepartment || '-'}</td>
            <td><span class="badge bg-secondary bg-opacity-10 text-secondary">${user.Environment || 'N/A'}</span></td>
            <td class="small">${formatDate(user.LastLogonDate)}</td>
            <td>
                <span class="badge ${user.Enabled ? 'bg-success' : 'bg-danger'} bg-opacity-10 ${user.Enabled ? 'text-success' : 'text-danger'}">
                    ${user.Enabled ? 'Ativo' : 'Inativo'}
                </span>
            </td>
            <td>
                <span class="risk-badge risk-${getRiskLevel(user.riskScore)}">${user.riskScore}%</span>
            </td>
        </tr>
    `).join('');

    // Pagination controls
    renderPagination(totalPages);
    lucide.createIcons();
}

function renderPagination(totalPages) {
    let pg = document.getElementById('tablePagination');
    if (!pg) {
        pg = document.createElement('div');
        pg.id = 'tablePagination';
        pg.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:14px 24px;border-top:1px solid rgba(255,255,255,0.05);';
        document.querySelector('.table-responsive').parentElement.appendChild(pg);
    }

    if (totalPages <= 1) {
        pg.innerHTML = `<span class="text-secondary small">${filteredUsers.length} resultado(s)</span>`;
        return;
    }

    const start = currentPage * PAGE_SIZE + 1;
    const end   = Math.min((currentPage + 1) * PAGE_SIZE, filteredUsers.length);
    pg.innerHTML = `
        <span class="text-secondary small">${start}–${end} de ${filteredUsers.length} usuários</span>
        <div class="d-flex gap-2">
            <button class="btn btn-sm btn-outline-secondary" onclick="changePage(-1)" ${currentPage === 0 ? 'disabled' : ''}>
                <i class="bi bi-chevron-left"></i>
            </button>
            <span class="text-secondary small d-flex align-items-center px-2">Pág. ${currentPage + 1} / ${totalPages}</span>
            <button class="btn btn-sm btn-outline-secondary" onclick="changePage(1)" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>
                <i class="bi bi-chevron-right"></i>
            </button>
        </div>
    `;
}

function changePage(delta) {
    const totalPages = Math.ceil(filteredUsers.length / PAGE_SIZE);
    currentPage = Math.max(0, Math.min(currentPage + delta, totalPages - 1));
    renderTable();
    document.getElementById('usersTable')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function exportToCSV() {
    if (filteredUsers.length === 0) {
        alert("Não há dados filtrados para exportar.");
        return;
    }

    const headers = ["Nome Exibição", "Username", "Email", "Departamento", "Cargo", "Ambiente", "Último Logon", "Dias sem Logon", "Status", "Risco (%)", "Conformidade"];
    const rows = filteredUsers.map(u => [
        `"${u.DisplayName || u.Name}"`,
        `"${u.Username}"`,
        `"${u.Email || ''}"`,
        `"${u.DisplayDepartment || ''}"`,
        `"${u.Title || ''}"`,
        `"${u.Environment || ''}"`,
        `"${formatDate(u.LastLogonDate)}"`,
        u.DaysSinceLastLogon || 0,
        u.Enabled ? "Ativo" : "Desativado",
        u.riskScore,
        u.isCompliant ? "Sim" : "Não"
    ]);

    let csvContent = "data:text/csv;charset=utf-8,\uFEFF"; // Add BOM for Excel
    csvContent += headers.join(",") + "\n";
    rows.forEach(row => {
        csvContent += row.join(",") + "\n";
    });

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    const timestamp = new Date().toISOString().split('T')[0];
    const envName = envFilter.value || "todos";
    
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `report_ad_filtered_${envName}_${timestamp}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Global variable to store current modal user
let currentModalUser = null;

function openUserDetails(username) {
    const user = allUsers.find(u => u.Username === username);
    if (!user) return;
    currentModalUser = user;

    document.getElementById('modalUserName').innerText = user.DisplayName || user.Username;
    document.getElementById('modalUserEmail').innerText = user.Email || 'Sem email cadastrado';
    document.getElementById('detailUsername').innerText = user.Username;
    document.getElementById('detailEnvironment').innerText = user.Environment || '-';
    document.getElementById('detailDept').innerText = user.DisplayDepartment || '-';
    document.getElementById('detailTitle').innerText = user.Title || '-';
    document.getElementById('detailCreated').innerText = formatDate(user.AccountCreated);
    document.getElementById('detailLastLogon').innerText = formatDate(user.LastLogonDate);
    document.getElementById('detailModified').innerText = formatDate(user.Modified) || '-';
    document.getElementById('detailOU').innerText = user.DistinguishedName || user.OU || '-';
    
    document.getElementById('detailPwdAge').innerText = (user.PasswordAgeDays || 0) + ' dias';
    document.getElementById('detailPwdExpires').innerText = user.PasswordNeverExpires ? 'Nunca' : 'Sim';
    document.getElementById('detailBadLogon').innerText = user.BadLogonCount || '0';
    
    const statusBadge = document.getElementById('modalAccountStatus');
    const headerStatus = document.getElementById('modalHeaderStatus');
    const userIcon = document.getElementById('modalUserIcon');
    
    if (user.Enabled) {
        statusBadge.innerText = 'Ativo';
        statusBadge.className = 'badge bg-success bg-opacity-10 text-success';
        headerStatus.innerText = 'CONTA ATIVA';
        headerStatus.className = 'badge bg-success';
        userIcon.style.background = 'rgba(16, 185, 129, 0.1)';
        userIcon.style.color = '#10b981';
    } else {
        statusBadge.innerText = 'Inativo / Desativado';
        statusBadge.className = 'badge bg-danger bg-opacity-10 text-danger';
        headerStatus.innerText = 'CONTA DESATIVADA';
        headerStatus.className = 'badge bg-danger';
        userIcon.style.background = 'rgba(239, 68, 68, 0.1)';
        userIcon.style.color = '#ef4444';
    }
    
    const riskBadge = document.getElementById('modalRiskBadge');
    const riskLevel = getRiskLevel(user.riskScore);
    riskBadge.innerText = riskLevel.toUpperCase();
    riskBadge.className = `risk-badge risk-${riskLevel}`;
    
    const progress = document.getElementById('modalRiskProgress');
    progress.style.width = `${user.riskScore}%`;
    progress.style.backgroundColor = riskLevel === 'low' ? '#10b981' : riskLevel === 'medium' ? '#f59e0b' : '#ef4444';
    
    const factorsList = document.getElementById('modalRiskFactors');
    factorsList.innerHTML = (user.riskFactors || []).map(factor => `
        <li class="mb-2 d-flex align-items-start gap-2 text-secondary">
            <i data-lucide="alert-circle" style="width: 12px; margin-top: 3px; flex-shrink: 0; color: ${riskLevel === 'low' ? '#10b981' : '#f59e0b'}"></i>
            <span>${factor}</span>
        </li>
    `).join('');

    const groupsContainer = document.getElementById('modalUserGroups');
    const privilegedGroupsLower = (stats.privilegedGroups || []).map(pg => pg.toLowerCase());
    
    groupsContainer.innerHTML = (user.Groups || []).map(g => {
        const isPriv = privilegedGroupsLower.includes(g.toLowerCase());
        return `<span class="group-pill ${isPriv ? 'privileged-group' : ''}">
            ${isPriv ? '<i data-lucide="shield-alert" style="width: 12px; margin-right: 5px;"></i>' : ''}
            ${g}
        </span>`;
    }).join('');

    // Update Exception UI
    updateExceptionModalUI();

    document.getElementById('userDetailsModal').style.display = 'flex';
    lucide.createIcons();
}

function updateExceptionModalUI() {
    const user = currentModalUser;
    const statusText = document.getElementById('exceptionStatusText');
    const approveBtn = document.getElementById('approveExceptionBtn');
    const removeBtn = document.getElementById('removeExceptionBtn');
    const form = document.getElementById('exceptionForm');

    form.style.display = 'none';

    if (user.isException) {
        statusText.innerHTML = `
            <div class="mb-1"><span class="text-info fw-bold">Exceção Ativa:</span> ${user.exceptionReason}</div>
            <div class="small text-secondary">
                <i data-lucide="user-check" style="width: 12px; height: 12px; vertical-align: middle;"></i> 
                Aprovado por: <b>${user.exceptionApprovedBy}</b> em ${user.exceptionApprovalDate}
            </div>
        `;
        approveBtn.style.display = 'none';
        removeBtn.style.display = 'block';
    } else {
        statusText.innerText = "Este usuário segue as regras globais de segurança.";
        approveBtn.style.display = 'block';
        removeBtn.style.display = 'none';
    }
}

function toggleExceptionForm() {
    const form = document.getElementById('exceptionForm');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
    if (form.style.display === 'block') {
        document.getElementById('exceptionReason').value = "";
        document.getElementById('exceptionReason').focus();
    }
}

async function saveException() {
    const reason = document.getElementById('exceptionReason').value;
    if (!reason) {
        alert("Por favor, informe o motivo da exceção.");
        return;
    }

    const csrfToken = _csrfToken();
    try {
        const res = await fetch(`/ad/api/exceptions/${currentModalUser.Username}`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            body: JSON.stringify({ reason })
        });
        if (res.ok) {
            await fetchData(); // Refresh all data
            // Find updated user object
            currentModalUser = allUsers.find(u => u.Username === currentModalUser.Username);
            updateExceptionModalUI();
            lucide.createIcons();
        }
    } catch (err) {
        console.error("Error saving exception:", err);
    }
}

async function removeException() {
    if (!confirm("Tem certeza que deseja remover esta exceção? O usuário voltará a ser avaliado pelas regras globais.")) return;

    const csrfToken = _csrfToken();
    try {
        const res = await fetch(`/ad/api/exceptions/${currentModalUser.Username}`, {
            method: 'DELETE',
            headers: { 'X-CSRF-Token': csrfToken }
        });
        if (res.ok) {
            await fetchData();
            currentModalUser = allUsers.find(u => u.Username === currentModalUser.Username);
            updateExceptionModalUI();
            lucide.createIcons();
        }
    } catch (err) {
        console.error("Error removing exception:", err);
    }
}

function formatDate(dateStr) {
    if (!dateStr || dateStr === 'Nunca') return 'Nunca';
    try {
        const date = new Date(dateStr);
        if (isNaN(date)) return dateStr;
        return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return dateStr; }
}

function getRiskLevel(score) {
    if (score < 30) return 'low';
    if (score < 60) return 'medium';
    if (score < 80) return 'high';
    return 'critical';
}

function setFilter(type) {
    currentFilters = { all: false, privileged: false, compliant: false, nonCompliant: false, lockedOut: false, neverExpires: false, disabled: false, inactive90: false };
    currentFilters[type] = true;
    applyFiltersAndSearch();
}

function setCreatedFilter(days) {
    if (createdDaysFilter === days) {
        createdDaysFilter = null;
    } else {
        createdDaysFilter = days;
    }
    applyFiltersAndSearch();
}

function toggleSort(col) {
    if (sortColumn === col) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = col;
        sortDirection = 'asc';
    }
    // Update sort indicator icons
    document.querySelectorAll('#usersTable th').forEach(th => {
        th.querySelectorAll('.sort-icon').forEach(el => el.remove());
    });
    const headers = ['name','email','department','environment','lastLogon','status','risk'];
    const thIdx = headers.indexOf(col);
    const ths = document.querySelectorAll('#usersTable th');
    if (thIdx >= 0 && ths[thIdx]) {
        const icon = document.createElement('i');
        icon.className = `bi bi-sort-${sortDirection === 'asc' ? 'up' : 'down'} sort-icon ms-1`;
        icon.style.fontSize = '.75rem';
        ths[thIdx].appendChild(icon);
    }
    applySort();
    renderTable();
}

function applySort() {
    if (!sortColumn) return;
    
    filteredUsers.sort((a, b) => {
        let valA, valB;
        switch(sortColumn) {
            case 'name':
                valA = (a.DisplayName || a.Username || '').toLowerCase();
                valB = (b.DisplayName || b.Username || '').toLowerCase();
                break;
            case 'email':
                valA = (a.Email || '').toLowerCase();
                valB = (b.Email || '').toLowerCase();
                break;
            case 'department':
                valA = (a.Department || '').toLowerCase();
                valB = (b.Department || '').toLowerCase();
                break;
            case 'environment':
                valA = (a.Environment || '').toLowerCase();
                valB = (b.Environment || '').toLowerCase();
                break;
            case 'lastLogon':
                valA = a.LastLogonDate && a.LastLogonDate !== 'Nunca' ? new Date(a.LastLogonDate).getTime() : 0;
                valB = b.LastLogonDate && b.LastLogonDate !== 'Nunca' ? new Date(b.LastLogonDate).getTime() : 0;
                break;
            case 'status':
                valA = a.Enabled ? 1 : 0;
                valB = b.Enabled ? 1 : 0;
                break;
            case 'risk':
                valA = a.riskScore || 0;
                valB = b.riskScore || 0;
                break;
            default:
                valA = ''; valB = '';
        }
        
        if (valA < valB) return sortDirection === 'asc' ? -1 : 1;
        if (valA > valB) return sortDirection === 'asc' ? 1 : -1;
        return 0;
    });
}

// Event Listeners
searchInput.addEventListener('input', applyFiltersAndSearch);
envFilter.addEventListener('change', applyFiltersAndSearch);
document.getElementById('tableSearch')?.addEventListener('input', applyFiltersAndSearch);
refreshBtn.addEventListener('click', fetchData);
exportBtn.addEventListener('click', exportToCSV);
document.getElementById('closeDetailsBtn').addEventListener('click', () => {
    document.getElementById('userDetailsModal').style.display = 'none';
});

window.onclick = function(event) {
    const modal = document.getElementById('userDetailsModal');
    if (event.target == modal) {
        modal.style.display = "none";
    }
}

// Initial Load
fetchData();
setInterval(fetchData, 300000);
