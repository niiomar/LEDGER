const $ = id => document.getElementById(id);
let csrfToken = '';
const api = async (url, opt={}) => {
  if (opt.body) opt.body = JSON.stringify(opt.body);
  opt.headers = {'Content-Type': 'application/json'};
  if (csrfToken) opt.headers['X-CSRF-Token'] = csrfToken;
  opt.credentials = 'same-origin';
  const res = await fetch(url, opt);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Request failed');
  return data;
};

const ghc = n => 'Gh¢ ' + (parseFloat(n)||0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
const initials = name => name.split(' ').map(n => n[0]).join('').slice(0,2).toUpperCase();
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const today = () => new Date().toISOString().split('T')[0];
const currentMonth = () => new Date().toISOString().slice(0, 7);

// Custom Confirmation Modal Logic
function confirmAction(title, msg, callback) {
    $('modal-msg').innerHTML = msg;
    $('confirm-modal').style.display = 'flex';

    const confirmBtn = $('modal-confirm-btn');
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

    newBtn.addEventListener('click', () => {
        $('confirm-modal').style.display = 'none';
        callback();
    });
}


// Auth
async function doLogin() {
    const username = $('login-user').value;
    const password = $('login-pass').value;
    try {
        const data = await api('/api/login', {method: 'POST', body: {username, password}});
        csrfToken = data.csrf_token;
        $('login-overlay').style.display = 'none';
        $('app-shell').style.display = 'flex';
        initApp();
    } catch(e) {
        showAlert('login-alert', e.message, 'error');
    }
}

function doLogout() {
    api('/api/logout', {method: 'POST'}).finally(() => location.reload());
}

// Sidebar
function toggleSidebar() {
    $('sidebar').classList.toggle('collapsed');
}

// Navigation
function showTab(tab, el) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
  $('tab-' + tab).classList.add('active');
  if (el) el.classList.add('active');
  $('page-title').textContent = el ? el.innerText.trim() : tab.charAt(0).toUpperCase() + tab.slice(1);

  if (tab === 'dashboard') loadDashboard();
  if (tab === 'dues') loadDues();
  if (tab === 'ledger') loadLedger();
  if (tab === 'members') loadMembers();
  if (tab === 'query') runQuery();
}

function showAlert(id, msg, type='success') {
  const el = $(id);
  el.innerHTML = `<div class="alert ${type}"><i class="fa-solid fa-${type==='success'?'circle-check':'circle-exclamation'}"></i> ${esc(msg)}</div>`;
  setTimeout(() => el.innerHTML = '', 4000);
}

// Dashboard
async function loadDashboard() {
  const [summary, ledger, dues] = await Promise.all([
    api('/api/ledger/summary'),
    api('/api/ledger'),
    api('/api/dues')
  ]);

  $('stats-grid').innerHTML = `
    <div class="stat-card">
      <div class="label">Total Balance</div>
      <div class="value ${summary.balance >= 0 ? 'green' : 'red'}">${ghc(summary.balance)}</div>
      <div class="sub">Current available liquid cash</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Dues</div>
      <div class="value">${ghc(summary.total_dues)}</div>
      <div class="sub">Actual cash received from members</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Credits</div>
      <div class="value green">${ghc(summary.total_credits)}</div>
      <div class="sub">All income across all categories</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Debits</div>
      <div class="value red">${ghc(summary.total_debits)}</div>
      <div class="sub">Total recorded expenses paid</div>
    </div>
  `;

  $('topbar-meta').textContent = `Balance: ${ghc(summary.balance)}`;

  const recentRows = ledger.slice(0, 8);
  $('dash-ledger-table').querySelector('tbody').innerHTML = recentRows.length
    ? recentRows.map(r => `
      <tr>
        <td>${esc(r.date)}</td>
        <td>${esc(r.description)}</td>
        <td><span class="badge ${r.type.toLowerCase()}">${r.type}</span></td>
        <td>${ghc(r.amount)}</td>
        <td class="${r.running_balance >= 0 ? 'balance-pos' : 'balance-neg'}">${ghc(r.running_balance)}</td>
      </tr>`).join('')
    : '<tr class="empty-row"><td colspan="5">No transactions recorded yet.</td></tr>';

  const top = [...dues].sort((a,b) => b.amount - a.amount).slice(0, 8);
  $('dash-dues-table').querySelector('tbody').innerHTML = top.map(d => `
    <tr>
      <td>
        <div style="display:flex;align-items:center;gap:8px">
          <div class="avatar">${esc(initials(d.member_name))}</div>
          ${esc(d.member_name)}
        </div>
      </td>
      <td>${ghc(d.amount)}</td>
      <td class="text-muted">${esc(d.period_from)} &rarr; ${esc(d.period_to)}</td>
    </tr>`).join('');
}

// Dues
async function loadDues() {
  const rows = await api('/api/dues');
  $('dues-count').textContent = rows.length + ' records';
  $('dues-table').querySelector('tbody').innerHTML = rows.length
    ? rows.map((d, i) => `
      <tr>
        <td class="text-muted">${rows.length - i}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <div class="avatar">${esc(initials(d.member_name))}</div>${esc(d.member_name)}
          </div>
        </td>
        <td>${ghc(d.amount)}</td>
        <td>${esc(d.period_from)}</td>
        <td>${esc(d.period_to)}</td>
        <td class="text-muted">${esc(d.created_at.split(' ')[0])}</td>
        <td>
          <button class="btn sm danger" onclick="deleteDues(${d.id})">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>`).join('')
    : '<tr class="empty-row"><td colspan="7">No dues records yet.</td></tr>';
}

function onDuesPeriodChange() {
  const from = $('dues-from').value;
  const to   = $('dues-to').value;
  if (!from || !to) { $('dues-amount').value = ''; $('dues-amount-hint').textContent = ''; return; }
  const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  function mIdx(s) { const p=s.split(' '); return parseInt(p[1])*12+MONTHS.indexOf(p[0]); }
  const f = mIdx(from), t = mIdx(to);
  if (t < f) { $('dues-amount-hint').textContent = '⚠ To must be after From'; $('dues-amount').value=''; return; }
  const months = t - f + 1;
  const amount = months * 20;
  $('dues-amount').value = amount;
  $('dues-amount-hint').textContent = `(${months} month${months>1?'s':''} × Gh¢20)`;
}

function getNextMonthStr(monthStr) {
  const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const parts = monthStr.split(' ');
  if (parts.length !== 2) return null;

  let mIdx = MONTHS.indexOf(parts[0]);
  let year = parseInt(parts[1]);

  mIdx++;
  if (mIdx > 11) {
    mIdx = 0;
    year++;
  }
  return `${MONTHS[mIdx]} ${year}`;
}

function getMonthValue(monthStr) {
  const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const parts = monthStr.split(' ');
  if (parts.length !== 2) return 0;
  return parseInt(parts[1]) * 12 + MONTHS.indexOf(parts[0]);
}

async function autoFillNextMonth() {
  const memberId = $('dues-member').value;
  const fromSelect = $('dues-from');

  if (!memberId) {
    fromSelect.value = '';
    fromSelect.disabled = false;
    $('dues-to').value = '';
    onDuesPeriodChange();
    return;
  }

  try {
    const dues = await api(`/api/dues?member_id=${memberId}`);

    if (dues && dues.length > 0) {
      let latestRecord = dues[0];
      let maxVal = getMonthValue(latestRecord.period_to);

      for (let i = 1; i < dues.length; i++) {
          let val = getMonthValue(dues[i].period_to);
          if (val > maxVal) {
              maxVal = val;
              latestRecord = dues[i];
          }
      }

      const lastPaidMonth = latestRecord.period_to;
      const nextMonth = getNextMonthStr(lastPaidMonth);

      if (nextMonth) {
        fromSelect.value = nextMonth;
        fromSelect.disabled = true;
        showAlert('dues-alert', `Locked starting period to <b>${nextMonth}</b> to prevent gaps in the ledger.`, 'info');
      }
    } else {
      fromSelect.value = '';
      fromSelect.disabled = false;
    }

    $('dues-to').value = '';
    onDuesPeriodChange();

  } catch (e) {
    console.error("Failed to fetch member dues history", e);
  }
}

async function saveDues() {
  const member_id   = $('dues-member').value;
  const amount      = $('dues-amount').value;
  const period_from = $('dues-from').value;
  const period_to   = $('dues-to').value;
  if (!member_id || !amount || !period_from || !period_to) {
    showAlert('dues-alert','Please select a member and payment period.','error'); return;
  }
  try {
    await api('/api/dues', {method:'POST', body:{member_id, amount:parseFloat(amount), period_from, period_to}});
    showAlert('dues-alert','Dues recorded and ledger updated automatically.');
    clearForm('dues');
    loadDues();
    loadDashboard();
  } catch(e) { showAlert('dues-alert', e.message, 'error'); }
}

function deleteDues(id) {
  confirmAction("Delete Dues", "Are you sure you want to permanently delete this dues record? This action cannot be undone.", async () => {
      await api('/api/dues/' + id, {method:'DELETE'});
      loadDues();
  });
}

function clearForm(form) {
  if (form === 'dues') {
    $('dues-member').value='';
    $('dues-amount').value='';
    $('dues-amount-hint').textContent='';
    $('dues-from').value='';
    $('dues-from').disabled = false;
    $('dues-to').value='';
    $('dues-alert').innerHTML = '';
  } else if (form === 'ledger') {
    $('tx-type').value='Credit';
    $('tx-desc').value='';
    $('tx-amount').value='';
    $('tx-note').value='';
    $('tx-date').value = today();
  }
}

// Ledger
async function loadLedger() {
  const rows = await api('/api/ledger');
  $('ledger-count').textContent = rows.length + ' transactions';
  $('ledger-table').querySelector('tbody').innerHTML = rows.length
    ? rows.map((r, i) => `
      <tr>
        <td class="text-muted">${rows.length - i}</td>
        <td>${esc(r.date)}</td>
        <td>${esc(r.description)}</td>
        <td><span class="badge ${r.type.toLowerCase()}">${r.type}</span></td>
        <td>${ghc(r.amount)}</td>
        <td class="${r.running_balance >= 0 ? 'balance-pos' : 'balance-neg'}">${ghc(r.running_balance)}</td>
        <td class="text-muted">${esc(r.note) || '—'}</td>
        <td>
          <button class="btn sm danger" onclick="deleteLedger(${r.id})">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>`).join('')
    : '<tr class="empty-row"><td colspan="8">No transactions recorded yet.</td></tr>';
}

async function saveLedger() {
  const type        = $('tx-type').value;
  const description = $('tx-desc').value.trim();
  const amount      = $('tx-amount').value;
  const date        = $('tx-date').value;
  const note        = $('tx-note').value.trim();
  if (!description || !amount || !date) {
    showAlert('ledger-alert','Description, amount, and date are required.','error'); return;
  }
  try {
    await api('/api/ledger', {method:'POST', body:{type, description, amount:parseFloat(amount), date, note}});
    showAlert('ledger-alert','Transaction saved successfully.');
    clearForm('ledger');
    loadLedger();
  } catch(e) { showAlert('ledger-alert', e.message, 'error'); }
}

function deleteLedger(id) {
  confirmAction("Delete Transaction", "Deleting this transaction will completely recalculate the running balance for all future entries. Are you sure?", async () => {
      await api('/api/ledger/' + id, {method:'DELETE'});
      loadLedger();
  });
}

// Query & Print
async function runQuery() {
  const type      = $('q-type').value;
  const memberId  = $('q-member').value;
  const keyword   = $('q-keyword').value.trim();
  const dateFrom  = $('q-date-from').value;
  const dateTo    = $('q-date-to').value;

  let rows = [];

  if (type !== 'ledger') {
    let dues = await api('/api/dues' + (memberId ? '?member_id='+memberId : ''));
    if (keyword) dues = dues.filter(d => d.member_name.toLowerCase().includes(keyword.toLowerCase()));
    dues.forEach(d => rows.push({
      badge: 'dues', label: d.member_name,
      amount: d.amount, period: d.period_from + ' → ' + d.period_to,
      detail: ghc(d.amount) + ' paid'
    }));
  }

  if (type !== 'dues') {
    const params = new URLSearchParams();
    if (keyword)   params.set('keyword', keyword);
    if (dateFrom)  params.set('date_from', dateFrom + '-01');
    if (dateTo)    params.set('date_to', dateTo + '-31');
    let txns = await api('/api/ledger?' + params);
    if (memberId) txns = [];
    txns.forEach(t => rows.push({
      badge: t.type.toLowerCase(), label: t.description,
      amount: t.amount, period: t.date,
      detail: t.note || '—'
    }));
  }

  $('q-count').textContent = rows.length + ' result' + (rows.length !== 1 ? 's' : '');
  $('q-table').querySelector('tbody').innerHTML = rows.length
    ? rows.map(r => `
      <tr>
        <td><span class="badge ${r.badge}">${r.badge==='dues'?'Dues':r.badge.charAt(0).toUpperCase()+r.badge.slice(1)}</span></td>
        <td>${esc(r.label)}</td>
        <td>${ghc(r.amount)}</td>
        <td class="text-muted">${esc(r.period)}</td>
        <td class="text-muted">${esc(r.detail)}</td>
      </tr>`).join('')
    : '<tr class="empty-row"><td colspan="5">No records match your search.</td></tr>';
}

function exportToExcel(tableId, filename) {
  const table = $(tableId);
  const headerCells = [...table.querySelectorAll('thead th')];
  const colIndexes = headerCells.map((th, i) => th.textContent.trim() ? i : -1).filter(i => i !== -1);

  const csvField = v => {
    const s = String(v ?? '').replace(/\s+/g, ' ').trim();
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };

  const lines = [colIndexes.map(i => csvField(headerCells[i].textContent)).join(',')];
  table.querySelectorAll('tbody tr').forEach(tr => {
    const cells = tr.querySelectorAll('td');
    if (!cells.length || tr.classList.contains('empty-row')) return;
    lines.push(colIndexes.map(i => csvField(cells[i] && cells[i].textContent)).join(','));
  });

  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}_${today()}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function clearQuery() {
  ['q-type','q-member'].forEach(id => $(id).value = id.includes('type') ? 'all' : '');
  ['q-keyword','q-date-from','q-date-to'].forEach(id => $(id).value = '');
  runQuery();
}

function printQuery() {
    const printContents = $('q-table').outerHTML;
    const metaCount = $('q-count').innerText;

    const printWindow = window.open('', '', 'height=700,width=900');
    printWindow.document.write('<html><head><title>Print Records - GMM Kasoa Media</title>');
    printWindow.document.write('<style>');
    printWindow.document.write('body { font-family: "Segoe UI", system-ui, sans-serif; color: #1a1a18; padding: 20px; }');
    printWindow.document.write('h2 { font-size: 18px; margin-bottom: 5px; text-transform: uppercase; border-bottom: 2px solid #000; padding-bottom: 10px; }');
    printWindow.document.write('p { font-size: 13px; color: #5a5a54; margin-bottom: 20px; }');
    printWindow.document.write('table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }');
    printWindow.document.write('th, td { border: 1px solid #d0d0c6; padding: 10px 14px; text-align: left; }');
    printWindow.document.write('th { background-color: #f9f9f6; font-size: 11px; font-weight: 700; text-transform: uppercase; color: #8a8a82; }');
    printWindow.document.write('.badge { display: inline-block; padding: 3px 9px; border-radius: 4px; font-size: 11px; font-weight: 600; border: 1px solid #d0d0c6;}');
    printWindow.document.write('</style>');
    printWindow.document.write('</head><body>');
    printWindow.document.write('<h2>Filtered Records Query</h2>');
    printWindow.document.write('<p>Generated on: ' + new Date().toLocaleString() + ' | Total: ' + metaCount + '</p>');
    printWindow.document.write(printContents);
    printWindow.document.write('</body></html>');
    printWindow.document.close();

    setTimeout(() => {
        printWindow.print();
    }, 250);
}

// Members
async function loadMembers() {
  const [members, dues] = await Promise.all([api('/api/members'), api('/api/dues')]);
  const duesByMember = {};
  dues.forEach(d => { duesByMember[d.member_id] = (duesByMember[d.member_id]||0) + d.amount; });

  $('member-count').textContent = members.length + ' members';
  $('members-table').querySelector('tbody').innerHTML = members.map((m, i) => `
    <tr>
      <td class="text-muted">${i+1}</td>
      <td>
        <div style="display:flex;align-items:center;gap:8px">
          <div class="avatar">${esc(initials(m.name))}</div>
          <div class="editable-name" id="member-name-${m.id}" data-id="${m.id}" data-name="${esc(m.name)}">${esc(m.name)}</div>
        </div>
      </td>
      <td>${ghc(duesByMember[m.id] || 0)}</td>
      <td>
        <button class="btn sm danger" data-id="${m.id}" data-name="${esc(m.name)}" data-action="delete-member">
          <i class="fa-solid fa-trash"></i>
        </button>
      </td>
    </tr>`).join('');
}

$('members-table').addEventListener('click', e => {
  const nameEl = e.target.closest('.editable-name');
  if (nameEl) { editMemberName(Number(nameEl.dataset.id), nameEl.dataset.name); return; }
  const delBtn = e.target.closest('[data-action="delete-member"]');
  if (delBtn) deleteMember(Number(delBtn.dataset.id), delBtn.dataset.name);
});

function editMemberName(id, currentName) {
    const cell = $(`member-name-${id}`);
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentName;
    input.className = 'edit-input';
    input.onblur = () => saveMemberName(id, input.value, currentName);
    input.onkeydown = (e) => {
        if (e.key === 'Enter') saveMemberName(id, input.value, currentName);
        if (e.key === 'Escape') cell.innerText = currentName;
    };
    cell.innerHTML = '';
    cell.appendChild(input);
    input.focus();
}

async function saveMemberName(id, newName, oldName) {
    if (!newName.trim() || newName.trim() === oldName) {
        $(`member-name-${id}`).innerText = oldName;
        return;
    }
    try {
        await api(`/api/members/${id}`, {method: 'PUT', body: {name: newName}});
        loadMembers();
        loadMemberDropdowns();
    } catch(e) {
        alert(e.message);
        $(`member-name-${id}`).innerText = oldName;
    }
}

async function addMember() {
  const name = $('new-member-name').value.trim();
  if (!name) { showAlert('member-alert','Please enter a name.','error'); return; }
  try {
    await api('/api/members', {method:'POST', body:{name}});
    showAlert('member-alert','Member added successfully.');
    $('new-member-name').value = '';
    loadMemberDropdowns();
    loadMembers();
  } catch(e) { showAlert('member-alert', e.message, 'error'); }
}

function deleteMember(id, name) {
  confirmAction("Remove Member", `Are you completely sure you want to remove <b>${esc(name)}</b> from the roster? This will instantly destroy all their dues records.`, async () => {
      await api('/api/members/' + id, {method:'DELETE'});
      loadMemberDropdowns();
      loadMembers();
  });
}

// Reports
async function generateReport(type = 'monthly') {
    const container = $('report-container');
    container.innerHTML = '<div style="text-align:center; padding:40px;"><div class="spinner"></div><p>Generating report...</p></div>';

    try {
        let data, titlePeriod;

        // Fetch global summary for the overall balance
        const globalSummary = await api('/api/ledger/summary');

        if (type === 'all') {
            data = await api(`/api/reports/comprehensive`);
            titlePeriod = 'All-Time Comprehensive Report';
        } else {
            const month = $('report-month').value;
            if (!month) { alert('Please select a month'); return; }
            data = await api(`/api/reports/monthly?month=${month}`);
            const [year, mon] = month.split('-');
            titlePeriod = new Date(year, mon-1).toLocaleString('default', { month: 'long', year: 'numeric' });
        }

        // Fetch the raw dues table to grab the fully merged coverage periods
        const rawDues = await api('/api/dues');

        // Dynamically build the dues section based on the report type
        let duesTableHtml = '';
        if (type === 'all') {
            duesTableHtml = `
                <h4 style="margin-bottom:10px; margin-top:25px; text-transform:uppercase; color:var(--text3); font-size:12px; letter-spacing:0.05em;">Member Dues Coverage</h4>
                <table style="margin-bottom:30px;">
                    <thead>
                        <tr>
                            <th>Type</th>
                            <th>Description</th>
                            <th>Member Name</th>
                            <th>Amount (Gh¢)</th>
                            <th>Coverage Period</th>
                            <th>Detail</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rawDues.length ? rawDues.map(d => `
                            <tr>
                                <td><span class="badge credit">Credit</span></td>
                                <td>Dues</td>
                                <td>${esc(d.member_name)}</td>
                                <td>${ghc(d.amount)}</td>
                                <td class="text-muted">${esc(d.period_from)} &rarr; ${esc(d.period_to)}</td>
                                <td class="text-muted">${ghc(d.amount)} paid</td>
                            </tr>
                        `).join('') : '<tr><td colspan="6" style="text-align:center">No dues records found</td></tr>'}
                    </tbody>
                </table>
            `;
        } else {
            duesTableHtml = `
                <h4 style="margin-bottom:10px; margin-top:25px; text-transform:uppercase; color:var(--text3); font-size:12px; letter-spacing:0.05em;">Dues Collected (Receipts)</h4>
                <table style="margin-bottom:30px;">
                    <thead>
                        <tr>
                            <th>Date Paid</th>
                            <th>Member</th>
                            <th>Coverage Period</th>
                            <th>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.dues.length ? data.dues.map(d => `
                            <tr>
                                <td>${esc(d.created_at.split(' ')[0])}</td>
                                <td>${esc(d.member_name)}</td>
                                <td>${esc(d.period_from)}${d.period_to ? ' &rarr; ' + esc(d.period_to) : ''}</td>
                                <td>${ghc(d.amount)}</td>
                            </tr>
                        `).join('') : '<tr><td colspan="4" style="text-align:center">No dues collected for this period</td></tr>'}
                    </tbody>
                </table>
            `;
        }

        let html = `
            <div class="report-header">
                <h1>GMM Kasoa Media - Financial Report</h1>
                <p>Period: ${titlePeriod}</p>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="label">Total Balance</div>
                    <div class="value ${globalSummary.balance >= 0 ? 'green' : 'red'}">${ghc(globalSummary.balance)}</div>
                    <div class="sub">Current available liquid cash</div>
                </div>
                <div class="stat-card">
                    <div class="label">Total Dues</div>
                    <div class="value">${ghc(data.summary.dues)}</div>
                    <div class="sub">Actual cash received from members</div>
                </div>
                <div class="stat-card">
                    <div class="label">Total Credits</div>
                    <div class="value green">${ghc(data.summary.credits)}</div>
                    <div class="sub">All income across all categories</div>
                </div>
                <div class="stat-card">
                    <div class="label">Total Debits</div>
                    <div class="value red">${ghc(data.summary.debits)}</div>
                    <div class="sub">Total recorded expenses paid</div>
                </div>
            </div>

            ${duesTableHtml}

            <h4 style="margin-bottom:10px; text-transform:uppercase; color:var(--text3); font-size:12px; letter-spacing:0.05em;">Ledger Transactions</h4>
            <table style="margin-bottom:30px;">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Description</th>
                        <th>Type</th>
                        <th>Amount</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.ledger.length ? data.ledger.map(r => `
                        <tr>
                            <td>${esc(r.date)}</td>
                            <td>${esc(r.description)}</td>
                            <td><span class="badge ${r.type.toLowerCase()}">${r.type}</span></td>
                            <td>${ghc(r.amount)}</td>
                        </tr>
                    `).join('') : '<tr><td colspan="4" style="text-align:center">No ledger entries for this period</td></tr>'}
                </tbody>
            </table>
        `;
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = `<div class="alert error">${e.message}</div>`;
    }
}

// Init
async function loadMemberDropdowns() {
  const members = await api('/api/members');
  const opts = '<option value="">— Select member —</option>' +
    members.map(m => `<option value="${m.id}">${esc(m.name)}</option>`).join('');
  $('dues-member').innerHTML = opts;
  $('q-member').innerHTML = '<option value="">— All Members —</option>' +
    members.map(m => `<option value="${m.id}">${esc(m.name)}</option>`).join('');

  const months = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const years = [2024, 2025, 2026];
  let pOpts = '<option value="">— Select period —</option>';
  years.forEach(y => months.forEach(m => pOpts += `<option value="${m} ${y}">${m} ${y}</option>`));
  $('dues-from').innerHTML = pOpts;
  $('dues-to').innerHTML = pOpts;
}

function updateTime() {
    const now = new Date();
    $('current-time').textContent = now.toLocaleString();
}

function initApp() {
    $('tx-date').value = today();
    $('report-month').value = currentMonth();
    loadMemberDropdowns();
    loadDashboard();
    setInterval(updateTime, 1000);
    updateTime();
}

window.onload = async () => {
    try {
        const data = await api('/api/session');
        if (data.authenticated) {
            csrfToken = data.csrf_token;
            $('login-overlay').style.display = 'none';
            $('app-shell').style.display = 'flex';
            initApp();
        }
    } catch (e) {
        // Not logged in (or server unreachable) - leave the login screen showing.
    }
};
