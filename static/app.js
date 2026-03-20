const state = {
  loading: false,
  requestId: 0,
  activeController: null,
  dataset: null,
  reportSnapshot: null,
  viewer: null,
  reportUsers: [],
  selectedReportUserIds: [],
  reportUsersWarning: "",
  pagination: {
    currentPage: 1,
    perPage: 25,
  },
  filters: {
    search: "",
    departments: [],
    requesters: [],
    optionSearches: {
      departments: "",
      requesters: "",
    },
  },
};

const FILTER_CONFIG = {
  departments: { field: "department", elementId: "department-filter", fallback: "ยังไม่จับคู่แผนก" },
  requesters: { field: "requester_name", elementId: "requester-filter", fallback: "ไม่ระบุผู้แจ้ง" },
};

const PINNED_REPORT_USER_LOGINS = ["bic-weerapon", "bic-pannawat"];
let reportRefreshTimer = null;

function qs(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function normalizeText(value) {
  return String(value ?? "").trim().toLowerCase();
}

function formatInputDate(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function formatHours(value) {
  const numeric = Number(value || 0);
  if (Number.isNaN(numeric)) return "0";
  if (Number.isInteger(numeric)) return String(numeric);
  return numeric.toFixed(2).replace(/\.0+$/, "");
}

function formatCount(value) {
  return Number(value || 0).toLocaleString("en-US");
}

function formatIsoDateForCompare(value) {
  return String(value || "").slice(0, 10);
}

function csvCell(value) {
  const text = String(value ?? "").replace(/\r?\n/g, " ").trim();
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function truncateText(value, limit = 52) {
  const text = String(value ?? "").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 3)).trimEnd()}...`;
}

function formatReportUserLabel(user) {
  if (!user) return "";
  const name = String(user.name || user.login || user.id || "").trim();
  const login = String(user.login || "").trim();
  if (!login || login === name) return name;
  return `${name} (${login})`;
}

function formatSelectedReportUsers(userIds) {
  const labels = userIds.map((userId) => formatReportUserLabel(findReportUserById(userId) || { id: userId })).filter(Boolean);
  if (!labels.length) return "บัญชีปัจจุบัน";
  if (labels.length <= 2) return labels.join(", ");
  return `${labels[0]}, ${labels[1]} และอีก ${labels.length - 2} คน`;
}

function renderMetric(id, value) {
  const target = qs(id);
  if (target) target.textContent = value;
}

function setReportUserNote(message, warning = false) {
  const note = qs("report-user-note");
  if (!note) return;
  note.textContent = message;
  note.classList.toggle("warning", warning);
}

function getRequestedReportUserIds() {
  if (state.selectedReportUserIds.length) return state.selectedReportUserIds;
  return [];
}

function syncDateFilterMode(forceDisable = null) {
  const checkbox = qs("disable-date-filter");
  const fromInput = qs("from-date");
  const toInput = qs("to-date");
  if (!checkbox || !fromInput || !toInput) return false;
  const disabled = typeof forceDisable === "boolean" ? forceDisable : checkbox.checked;
  checkbox.checked = disabled;
  fromInput.disabled = disabled;
  toInput.disabled = disabled;
  if (disabled) {
    fromInput.value = "";
    toInput.value = "";
  }
  return disabled;
}

function findReportUserById(userId) {
  return state.reportUsers.find((user) => String(user.id) === String(userId));
}

function updateReportUserNoteFromSelection() {
  const scopePrefix = syncDateFilterMode()
    ? "ถ้าอัปเดตรายงานตอนนี้ จะแสดงงานทั้งหมดของผู้รับผิดชอบ"
    : "ถ้าอัปเดตรายงานตอนนี้ จะแสดง issue จาก time entry ของผู้รับผิดชอบ";
  const warning = Boolean(state.reportUsersWarning);
  setReportUserNote(
    `${scopePrefix} ${formatSelectedReportUsers(state.selectedReportUserIds)}${warning ? " • โหลดรายชื่ออัตโนมัติไม่สำเร็จ" : ""}`,
    warning,
  );
}

function renderReportUserFilter() {
  const container = qs("report-user-filter");
  if (!container) return;
  if (!state.reportUsers.length) {
    container.innerHTML = `<p class="filter-empty">ยังโหลดรายชื่อผู้รับผิดชอบไม่ได้</p>`;
    updateReportUserNoteFromSelection();
    return;
  }

  container.innerHTML = state.reportUsers
    .map((user) => {
      const value = String(user.id);
      const active = state.selectedReportUserIds.includes(value);
      return `
        <button
          class="filter-chip${active ? " active" : ""}"
          type="button"
          data-report-user-id="${escapeHtml(value)}"
        >
          ${escapeHtml(formatReportUserLabel(user))}
        </button>
      `;
    })
    .join("");
  updateReportUserNoteFromSelection();
}

function renderReportUserOptions(payload) {
  const allUsers = Array.isArray(payload?.users) ? payload.users : [];
  const preferredUsers = PINNED_REPORT_USER_LOGINS.map((login) =>
    allUsers.find((user) => normalizeText(user.login) === normalizeText(login)),
  ).filter(Boolean);
  state.reportUsers = preferredUsers.length ? preferredUsers : allUsers;
  state.reportUsersWarning = String(payload?.warning || "").trim();

  const fallbackUserId = String(payload?.current_user?.id || "");
  const availableIds = state.reportUsers.map((user) => String(user.id));
  const preservedIds = state.selectedReportUserIds.filter((userId) => availableIds.includes(userId));
  const defaultUserIds = preferredUsers.map((user) => String(user.id));
  if (preservedIds.length) {
    state.selectedReportUserIds = preservedIds;
  } else if (defaultUserIds.length) {
    state.selectedReportUserIds = defaultUserIds;
  } else if (fallbackUserId && availableIds.includes(fallbackUserId)) {
    state.selectedReportUserIds = [fallbackUserId];
  } else if (availableIds.length) {
    state.selectedReportUserIds = [availableIds[0]];
  } else {
    state.selectedReportUserIds = [];
  }
  renderReportUserFilter();
}

function toggleReportUserId(userId) {
  if (state.selectedReportUserIds.includes(userId)) {
    state.selectedReportUserIds = state.selectedReportUserIds.filter((value) => value !== userId);
  } else {
    state.selectedReportUserIds = [...state.selectedReportUserIds, userId];
  }
  renderReportUserFilter();
}

function scheduleReportRefresh(delay = 250) {
  if (reportRefreshTimer) {
    window.clearTimeout(reportRefreshTimer);
  }
  reportRefreshTimer = window.setTimeout(() => {
    reportRefreshTimer = null;
    state.pagination.currentPage = 1;
    loadReport();
  }, delay);
}

function getRequestedReportState() {
  const disableDateFilter = syncDateFilterMode();
  return {
    disableDateFilter,
    from: disableDateFilter ? "" : qs("from-date")?.value || "",
    to: disableDateFilter ? "" : qs("to-date")?.value || "",
    selectedUserIds: getRequestedReportUserIds(),
  };
}

function collectIssues(payload) {
  const grouped = new Map();
  (payload.yearly_reports || []).forEach((yearData) => {
    (yearData.issues || []).forEach((raw) => {
      const id = Number(raw.issue_id || 0);
      if (!id) return;
      const data = grouped.get(id) || {
        ...raw,
        hours: Number(raw.hours || 0),
        entries: Number(raw.entries || 0),
        issue_id: id,
        years: new Set(),
        first_spent_on: raw.first_spent_on,
        last_spent_on: raw.last_spent_on,
      };
      data.hours += Number(raw.hours || 0);
      data.entries += Number(raw.entries || 0);
      if (raw.first_spent_on) {
        if (!data.first_spent_on || raw.first_spent_on < data.first_spent_on) {
          data.first_spent_on = raw.first_spent_on;
        }
      }
      if (raw.last_spent_on) {
        if (!data.last_spent_on || raw.last_spent_on > data.last_spent_on) {
          data.last_spent_on = raw.last_spent_on;
        }
      }
      data.years.add(String(yearData.year || raw.year || ""));
      grouped.set(id, data);
    });
  });
  return Array.from(grouped.values()).map((issue) => ({
    ...issue,
    years_label: Array.from(issue.years).filter(Boolean).sort().join(", "),
    hours_label: formatHours(issue.hours),
  }));
}

function buildDataset(payload) {
  const issues = collectIssues(payload);
  const extras = new Map();
  (payload.entries || []).forEach((entry) => {
    const id = Number(entry.issue_id || 0);
    if (!id) return;
    const current = extras.get(id) || { activity: "", comment: "" };
    if (!current.activity && entry.activity) current.activity = entry.activity;
    if (!current.comment && entry.comments) current.comment = entry.comments;
    extras.set(id, current);
  });
  issues.forEach((issue) => {
    const extra = extras.get(issue.issue_id) || {};
    issue.activity_label = extra.activity || issue.activity_label || "ไม่ระบุกิจกรรม";
    issue.latest_comment = extra.comment || issue.latest_comment || "";
    issue.search_blob = normalizeText(
      [
        issue.issue_id,
        issue.subject,
        issue.project,
        issue.tracker_name,
        issue.status,
        issue.priority,
        issue.assigned_to_name,
        issue.requester_name,
        issue.department,
        issue.company_label,
        issue.years_label,
        issue.activity_label,
        issue.latest_comment,
      ].join(" "),
    );
  });
  return {
    issues,
    entries: payload.entries || [],
    generated_at: payload.generated_at,
    filters: payload.filters,
  };
}

function buildReportSnapshot(payload) {
  if (payload?.filters?.scope_mode !== "time_entries") {
    return null;
  }
  const from = formatIsoDateForCompare(payload.filters?.from);
  const to = formatIsoDateForCompare(payload.filters?.to);
  const userIds = Array.isArray(payload.filters?.user_ids) ? payload.filters.user_ids.map((value) => String(value)) : [];
  const entries = Array.isArray(payload.entries)
    ? payload.entries
        .map((entry) => ({
          ...entry,
          date: formatIsoDateForCompare(entry.date),
          hours: Number(entry.hours || 0),
          issue_id: Number(entry.issue_id || 0),
          user_id: String(entry.user_id || ""),
        }))
        .filter((entry) => entry.issue_id && entry.user_id && entry.date)
    : [];
  if (!from || !to || !userIds.length || !entries.length) {
    return null;
  }
  return {
    scopeMode: "time_entries",
    from,
    to,
    userIds,
    issueLookup: new Map(collectIssues(payload).map((issue) => [Number(issue.issue_id || 0), issue])),
    entries,
  };
}

function canRenderReportLocally(requestedState) {
  const snapshot = state.reportSnapshot;
  if (!snapshot || snapshot.scopeMode !== "time_entries") return false;
  if (requestedState.disableDateFilter) return false;
  if (!requestedState.from || !requestedState.to) return false;
  if (requestedState.from < snapshot.from || requestedState.to > snapshot.to) return false;
  if (!requestedState.selectedUserIds.length) return false;
  return requestedState.selectedUserIds.every((userId) => snapshot.userIds.includes(String(userId)));
}

function buildLocalPayloadFromSnapshot(requestedState) {
  const snapshot = state.reportSnapshot;
  if (!snapshot) return null;
  const selectedUserIds = requestedState.selectedUserIds.map((value) => String(value));
  const selectedIdSet = new Set(selectedUserIds);
  const filteredEntries = snapshot.entries.filter(
    (entry) =>
      selectedIdSet.has(entry.user_id) &&
      entry.date >= requestedState.from &&
      entry.date <= requestedState.to,
  );
  const issuesById = new Map();

  filteredEntries.forEach((entry) => {
    const template = snapshot.issueLookup.get(entry.issue_id);
    if (!template) return;
    const current = issuesById.get(entry.issue_id) || {
      ...template,
      hours: 0,
      entries: 0,
      first_spent_on: "",
      last_spent_on: "",
      years: new Set(),
    };
    current.hours += Number(entry.hours || 0);
    current.entries += 1;
    if (!current.first_spent_on || entry.date < current.first_spent_on) {
      current.first_spent_on = entry.date;
    }
    if (!current.last_spent_on || entry.date > current.last_spent_on) {
      current.last_spent_on = entry.date;
    }
    current.years.add(entry.date.slice(0, 4));
    issuesById.set(entry.issue_id, current);
  });

  const issues = Array.from(issuesById.values())
    .map((issue) => ({
      ...issue,
      year: Array.from(issue.years).filter(Boolean).sort().join(", "),
    }))
    .sort((left, right) => {
      const hoursDiff = Number(right.hours || 0) - Number(left.hours || 0);
      if (hoursDiff !== 0) return hoursDiff;
      const dateDiff = String(right.last_spent_on || "").localeCompare(String(left.last_spent_on || ""));
      if (dateDiff !== 0) return dateDiff;
      return Number(right.issue_id || 0) - Number(left.issue_id || 0);
    });

  const totalHours = filteredEntries.reduce((sum, entry) => sum + Number(entry.hours || 0), 0);
  const selectedUsers = selectedUserIds
    .map((userId) => findReportUserById(userId) || { id: userId, name: userId, login: userId })
    .filter(Boolean);

  return {
    generated_at: new Date().toISOString(),
    viewer: state.viewer,
    users: selectedUsers,
    entries: filteredEntries,
    filters: {
      from: requestedState.from,
      to: requestedState.to,
      user_ids: selectedUserIds,
      scope_mode: "time_entries",
    },
    yearly_reports: issues.length
      ? [
          {
            year: "",
            total_hours: totalHours,
            total_hours_label: formatHours(totalHours),
            total_entries: filteredEntries.length,
            issue_count: issues.length,
            matched_issue_count: 0,
            department_count: 0,
            departments: [],
            requesters: [],
            companies: [],
            unmatched_requesters: [],
            match_breakdown: { exact: 0, alias: 0, unmatched: 0 },
            issues,
          },
        ]
      : [],
  };
}

function getFieldValue(issue, field, fallback) {
  const raw = issue[field] ?? "";
  const normalized = normalizeText(raw);
  if (!normalized) return fallback;
  if (typeof raw === "string") {
    return raw.trim();
  }
  return String(raw);
}

function matchesSearch(issue) {
  const { search } = state.filters;
  if (search) {
    const needle = normalizeText(search);
    if (!issue.search_blob.includes(needle)) return false;
  }
  return true;
}

function matchesSidebarFilters(issue) {
  const { departments, requesters } = state.filters;
  const checks = [
    { values: departments, config: FILTER_CONFIG.departments },
    { values: requesters, config: FILTER_CONFIG.requesters },
  ];
  return checks.every(({ values, config }) => {
    if (!values.length) return true;
    const current = getFieldValue(issue, config.field, config.fallback);
    return values.includes(current);
  });
}

function matchesFilters(issue) {
  if (!state.dataset) return false;
  return matchesSearch(issue) && matchesSidebarFilters(issue);
}

function getFilteredIssues() {
  if (!state.dataset) return [];
  return state.dataset.issues.filter(matchesFilters);
}

function paginate(items) {
  const perPage = state.pagination.perPage;
  const totalPages = Math.max(1, Math.ceil(items.length / perPage));
  state.pagination.currentPage = Math.min(state.pagination.currentPage, totalPages);
  const start = (state.pagination.currentPage - 1) * perPage;
  const end = Math.min(start + perPage, items.length);
  return {
    items: items.slice(start, end),
    total: items.length,
    start,
    end,
    totalPages,
  };
}

function renderPagination(total, pagination) {
  const prev = qs("prev-page");
  const next = qs("next-page");
  const info = qs("page-info");
  if (!prev || !next || !info) return;
  if (total === 0) {
    prev.disabled = true;
    next.disabled = true;
    info.textContent = "0 รายการ";
    return;
  }
  prev.disabled = state.pagination.currentPage <= 1;
  next.disabled = state.pagination.currentPage >= pagination.totalPages;
  info.textContent = `${formatCount(pagination.start + 1)}-${formatCount(pagination.end)} / ${formatCount(total)} • หน้า ${state.pagination.currentPage}/${pagination.totalPages}`;
}

function updateExportButtonState(filteredIssues = null) {
  const button = qs("export-csv");
  if (!button) return;
  const issues = Array.isArray(filteredIssues) ? filteredIssues : getFilteredIssues();
  button.disabled = state.loading || !issues.length;
}

function buildIssueRow(issue, runNumber) {
  const issueLink = issue.issue_url
    ? `<a class="issue-link" href="${escapeHtml(issue.issue_url)}" target="_blank" rel="noreferrer">#${escapeHtml(issue.issue_id)}</a>`
    : `#${escapeHtml(issue.issue_id)}`;
  const isUnmatchedDept = issue.department === "ยังไม่จับคู่แผนก";
  const subjectLabel = truncateText(issue.subject || "-", 52);
  const issueMeta = issue.years_label ? `<span class="muted">ปี ${escapeHtml(issue.years_label)}</span>` : "";
  return `
    <tr>
      <td data-label="Run">
        <strong>${escapeHtml(runNumber)}</strong>
      </td>
      <td data-label="Issue">
        ${issueLink}
        <strong class="issue-subject" title="${escapeHtml(issue.subject || "-")}">${escapeHtml(subjectLabel)}</strong>
        ${issueMeta}
      </td>
      <td data-label="โปรเจกต์">
        <strong>${escapeHtml(issue.project)}</strong>
      </td>
      <td data-label="ผู้รับผิดชอบ">
        <strong>${escapeHtml(issue.assigned_to_name || "-")}</strong>
      </td>
      <td data-label="ผู้แจ้ง / แผนก">
        <strong>${escapeHtml(issue.requester_name || "-")}</strong>
        <span class="badge${isUnmatchedDept ? " unmatched" : ""}">${escapeHtml(issue.department || "ยังไม่จับคู่แผนก")}</span>
      </td>
      <td data-label="สถานะ">
        <strong>${escapeHtml(issue.status || "-")}</strong>
      </td>
    </tr>
  `;
}

function renderIssues(rows, startIndex = 0) {
  const body = qs("issues-body");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="6" class="table-empty">ไม่พบงานตามตัวกรองที่เลือก</td></tr>`;
    return;
  }
  body.innerHTML = rows.map((issue, index) => buildIssueRow(issue, formatCount(startIndex + index + 1))).join("");
}

function buildCsvFilename() {
  const from = state.dataset?.filters?.from || "";
  const to = state.dataset?.filters?.to || "";
  const scope = from || to ? `${from || "start"}_${to || "end"}` : "all-dates";
  return `redmine-report_${scope}_${formatInputDate(new Date())}.csv`;
}

function buildCsvContent(issues) {
  const headers = ["No.", "Issue ID", "Subject", "โปรเจกต์", "ผู้รับผิดชอบ", "ผู้แจ้ง", "แผนก", "สถานะ", "Redmine URL"];
  const rows = issues.map((issue, index) =>
    [
      index + 1,
      issue.issue_id,
      issue.subject || "",
      issue.project || "",
      issue.assigned_to_name || "",
      issue.requester_name || "",
      issue.department || "",
      issue.status || "",
      issue.issue_url || "",
    ]
      .map(csvCell)
      .join(","),
  );
  return `\uFEFF${headers.map(csvCell).join(",")}\r\n${rows.join("\r\n")}`;
}

function exportCsv() {
  const issues = getFilteredIssues();
  if (!issues.length) {
    showError("ไม่มีข้อมูลสำหรับ Export CSV");
    updateExportButtonState(issues);
    return;
  }
  const blob = new Blob([buildCsvContent(issues)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = buildCsvFilename();
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function computeAvailableValues(targetKey) {
  if (!state.dataset) return [];
  const config = FILTER_CONFIG[targetKey];
  return Array.from(
    new Set(
      state.dataset.issues
        .filter((issue) => {
          if (!matchesSearch(issue)) return false;
          return Object.keys(FILTER_CONFIG).every((key) => {
            if (key === targetKey) return true;
            const values = state.filters[key];
            if (!values.length) return true;
            const currentValue = getFieldValue(issue, FILTER_CONFIG[key].field, FILTER_CONFIG[key].fallback);
            return values.includes(currentValue);
          });
        })
        .map((issue) => getFieldValue(issue, config.field, config.fallback)),
    ),
  ).sort((a, b) => a.localeCompare(b, "th"));
}

function renderFilterOptions() {
  Object.keys(FILTER_CONFIG).forEach((key) => {
    const config = FILTER_CONFIG[key];
    const container = qs(config.elementId);
    if (!container) return;
    const available = computeAvailableValues(key);
    const preserved = state.filters[key].filter((value) => available.includes(value));
    const optionNeedle = normalizeText(state.filters.optionSearches[key] || "");
    const visible = optionNeedle
      ? available.filter((value) => normalizeText(value).includes(optionNeedle))
      : available;
    state.filters[key] = preserved;
    if (!available.length) {
      container.innerHTML = `<p class="filter-empty">ไม่มีตัวเลือกในช่วงข้อมูลนี้</p>`;
      return;
    }
    if (!visible.length) {
      container.innerHTML = `<p class="filter-empty">ไม่พบตัวเลือกที่ตรงกับคำค้น</p>`;
      return;
    }
    container.innerHTML = visible
      .map((value) => `
        <button
          class="filter-chip${preserved.includes(value) ? " active" : ""}"
          type="button"
          data-filter-value="${escapeHtml(value)}"
        >
          ${escapeHtml(value)}
        </button>
      `)
      .join("");
  });
}

function toggleFilterValue(key, value) {
  const current = state.filters[key] || [];
  if (current.includes(value)) {
    state.filters[key] = current.filter((item) => item !== value);
    return;
  }
  state.filters[key] = [...current, value];
}

function applyFilters() {
  if (!state.dataset) return;
  renderFilterOptions();
  const filtered = getFilteredIssues();
  const requesters = new Set(filtered.map((issue) => getFieldValue(issue, FILTER_CONFIG.requesters.field, FILTER_CONFIG.requesters.fallback)));
  renderMetric("metric-issues", formatCount(filtered.length));
  renderMetric("metric-requesters", formatCount(requesters.size));
  const pagination = paginate(filtered);
  renderIssues(pagination.items, pagination.start);
  renderPagination(filtered.length, pagination);
  updateExportButtonState(filtered);
  const statusLine = qs("status-line");
  if (statusLine) {
    const scopeLabel = state.dataset.filters?.scope_mode === "assigned" ? "โหมดทั้งหมด" : "โหมดช่วงวันที่";
    statusLine.textContent = filtered.length
      ? `${scopeLabel} • แสดง ${formatCount(pagination.start + 1)}-${formatCount(pagination.end)} จาก ${formatCount(filtered.length)} งาน`
      : `${scopeLabel} • ไม่พบงานที่ตรงกับตัวกรอง`;
  }
}

function renderPayload(payload, options = {}) {
  const { cacheSnapshot = true } = options;
  const dataset = buildDataset(payload);
  state.dataset = dataset;
  state.viewer = payload.viewer || state.viewer;
  if (cacheSnapshot) {
    state.reportSnapshot = buildReportSnapshot(payload);
  }
  state.pagination.currentPage = 1;
  if (Array.isArray(payload.filters?.user_ids) && payload.filters.user_ids.length) {
    state.selectedReportUserIds = payload.filters.user_ids.map((value) => String(value));
  }
  state.filters.search = "";
  Object.keys(FILTER_CONFIG).forEach((key) => (state.filters[key] = []));
  if (qs("search-input")) qs("search-input").value = "";
  if (payload.filters) {
    if (qs("from-date")) qs("from-date").value = payload.filters.from || "";
    if (qs("to-date")) qs("to-date").value = payload.filters.to || "";
    syncDateFilterMode(!payload.filters.from && !payload.filters.to);
  }
  renderReportUserFilter();
  if (payload.users?.length || payload.user) {
    const selectedUsers = Array.isArray(payload.users) && payload.users.length ? payload.users : [payload.user];
    const scopePrefix =
      payload.filters?.scope_mode === "assigned"
        ? "กำลังดูงานทั้งหมดของผู้รับผิดชอบ"
        : "กำลังดู issue จาก time entry ของผู้รับผิดชอบ";
    let note = `${scopePrefix} ${formatSelectedReportUsers(selectedUsers.map((user) => String(user.id)))}`;
    if (payload.viewer && selectedUsers.every((user) => Number(payload.viewer.id) !== Number(user.id))) {
      note += ` • เข้าระบบด้วย ${formatReportUserLabel(payload.viewer)}`;
    }
    setReportUserNote(note);
  }
  applyFilters();
}

async function loadReport() {
  const requestedState = getRequestedReportState();
  const { disableDateFilter, from, to, selectedUserIds } = requestedState;
  if (from && to && from > to) {
    const error = qs("error-box");
    if (error) {
      error.textContent = "วันที่เริ่มต้นต้องไม่มากกว่าวันที่สิ้นสุด";
      error.classList.remove("hidden");
    }
    return;
  }
  if (canRenderReportLocally(requestedState)) {
    if (state.activeController) {
      state.activeController.abort();
      state.activeController = null;
    }
    hideError();
    const localPayload = buildLocalPayloadFromSnapshot(requestedState);
    if (localPayload) {
      renderPayload(localPayload, { cacheSnapshot: false });
      return;
    }
  }
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  selectedUserIds.forEach((userId) => params.append("user_id", userId));
  const requestId = ++state.requestId;
  if (state.activeController) state.activeController.abort();
  const controller = new AbortController();
  state.activeController = controller;
  setLoading(true);
  hideError();
  try {
    const url = params.toString() ? `/api/report?${params.toString()}` : "/api/report";
    const response = await fetch(url, { headers: { Accept: "application/json" }, signal: controller.signal });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "โหลดข้อมูลไม่สำเร็จ");
    }
    if (requestId !== state.requestId) return;
    renderPayload(payload);
  } catch (error) {
    if (error.name === "AbortError" || requestId !== state.requestId) return;
    showError(error.message || "เกิดข้อผิดพลาดระหว่างโหลดข้อมูล");
  } finally {
    if (requestId === state.requestId) {
      setLoading(false);
      state.activeController = null;
    }
  }
}

async function loadReportUsers() {
  try {
    const response = await fetch("/api/report-users", { headers: { Accept: "application/json" } });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "โหลดรายชื่อผู้ใช้ไม่สำเร็จ");
    }
    renderReportUserOptions(payload);
  } catch (error) {
    state.reportUsers = [];
    state.reportUsersWarning = error.message || "โหลดรายชื่อผู้ใช้ไม่สำเร็จ";
    renderReportUserFilter();
  }
}

function showError(message) {
  const box = qs("error-box");
  if (!box) return;
  box.textContent = message;
  box.classList.remove("hidden");
}

function hideError() {
  const box = qs("error-box");
  if (!box) return;
  box.classList.add("hidden");
}

function setLoading(loading) {
  state.loading = loading;
  const button = document.querySelector(".primary-button");
  if (button) {
    button.disabled = loading;
    button.textContent = loading ? "กำลังโหลด..." : "อัปเดตรายงาน";
  }
  const statusLine = qs("status-line");
  if (statusLine && loading) {
    statusLine.textContent = "กำลังซิงก์ข้อมูลจาก Redmine...";
  }
  updateExportButtonState();
}

function initDefaultRange() {
  const fromInput = qs("from-date");
  const toInput = qs("to-date");
  if (fromInput && !fromInput.value) {
    fromInput.value = "2025-01-01";
  }
  if (toInput && !toInput.value) {
    toInput.value = formatInputDate(new Date());
  }
  syncDateFilterMode(false);
  updateReportUserNoteFromSelection();
}

function bindEvents() {
  qs("filters-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    state.pagination.currentPage = 1;
    loadReport();
  });

  qs("search-input")?.addEventListener("input", (event) => {
    state.filters.search = event.target.value;
    state.pagination.currentPage = 1;
    applyFilters();
  });

  qs("department-filter-search")?.addEventListener("input", (event) => {
    state.filters.optionSearches.departments = event.target.value;
    applyFilters();
  });

  qs("requester-filter-search")?.addEventListener("input", (event) => {
    state.filters.optionSearches.requesters = event.target.value;
    applyFilters();
  });

  qs("report-user-filter")?.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const chip = event.target.closest("[data-report-user-id]");
    if (!chip) return;
    const userId = chip.dataset.reportUserId;
    if (!userId) return;
    toggleReportUserId(userId);
    scheduleReportRefresh();
  });

  qs("report-user-clear")?.addEventListener("click", () => {
    state.selectedReportUserIds = [];
    renderReportUserFilter();
    scheduleReportRefresh();
  });

  qs("disable-date-filter")?.addEventListener("change", (event) => {
    syncDateFilterMode(event.target.checked);
    updateReportUserNoteFromSelection();
    scheduleReportRefresh();
  });

  ["from-date", "to-date"].forEach((id) => {
    qs(id)?.addEventListener("change", () => {
      syncDateFilterMode(false);
      updateReportUserNoteFromSelection();
      scheduleReportRefresh();
    });
  });

  Object.entries(FILTER_CONFIG).forEach(([key, config]) => {
    qs(config.elementId)?.addEventListener("click", (event) => {
      if (!(event.target instanceof Element)) return;
      const chip = event.target.closest("[data-filter-value]");
      if (!chip) return;
      const value = chip.dataset.filterValue;
      if (!value) return;
      toggleFilterValue(key, value);
      state.pagination.currentPage = 1;
      applyFilters();
    });
  });

  document.querySelectorAll("[data-filter-clear]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.filterClear;
      if (!key || !state.filters[key]) return;
      state.filters[key] = [];
      state.pagination.currentPage = 1;
      applyFilters();
    });
  });

  qs("rows-per-page")?.addEventListener("change", (event) => {
    state.pagination.perPage = Number(event.target.value);
    state.pagination.currentPage = 1;
    applyFilters();
  });

  qs("export-csv")?.addEventListener("click", () => {
    exportCsv();
  });

  qs("prev-page")?.addEventListener("click", () => {
    if (state.pagination.currentPage > 1) {
      state.pagination.currentPage -= 1;
      applyFilters();
    }
  });

  qs("next-page")?.addEventListener("click", () => {
    state.pagination.currentPage += 1;
    applyFilters();
  });
}

async function initApp() {
  initDefaultRange();
  bindEvents();
  await loadReportUsers();
  loadReport();
}

initApp();
