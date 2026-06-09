const A11Y_JOBS_SHEET = 'Jobs';
const A11Y_REVIEW_SHEET = 'Review';
const A11Y_CONFIG_SHEET = 'Config';
const A11Y_TERMINAL_STATUSES = ['done', 'error', 'needs_review'];
const A11Y_STATUS_VALUES = ['', 'queued', 'running', 'done', 'error', 'needs_review'];
const A11Y_REVIEW_STATUS_VALUES = ['', 'pending', 'approved', 'rejected'];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('A11y')
    .addItem('選択行を実行（キュー投入）', 'enqueueSelected')
    .addItem('選択行を再実行', 'requeueSelected')
    .addItem('選択行を承認', 'approveSelected')
    .addSeparator()
    .addItem('今すぐ実行（直接）', 'runSelectedNow')
    .addSeparator()
    .addItem('シート整備', 'setupSheetUx')
    .addItem('通知トリガを設置', 'installTriggers')
    .addToUi();
}

function enqueueSelected() {
  const result = updateSelectedJobRows_(function(row, headers) {
    const status = String(row.status || '').trim();
    if (status === 'done' || status === 'running') {
      const proceed = confirm_(Utilities.formatString(
        'job_id=%s は status=%s です。queued に変更しますか？', row.job_id || '(未設定)', status));
      if (!proceed) return null;
    }
    const updates = {status: 'queued'};
    if (!String(row.created_at || '').trim()) updates.created_at = nowIso_();
    return updates;
  });
  toast_(Utilities.formatString('%s 行を queued にしました。', result.updated));
}

function requeueSelected() {
  const result = updateSelectedJobRows_(function() {
    return {status: 'queued', error: ''};
  });
  toast_(Utilities.formatString('%s 行を再実行キューに戻しました。', result.updated));
}

function approveSelected() {
  const autoPromote = getConfigValue_('auto_promote_gold').toLowerCase() === 'true';
  const result = updateSelectedJobRows_(function() {
    const updates = {review_status: 'approved'};
    if (autoPromote) updates.promote_requested = 'true';
    return updates;
  });
  toast_(Utilities.formatString('%s 行を承認しました%s。', result.updated, autoPromote ? '（gold 反映を予約）' : ''));
}

function runSelectedNow() {
  const endpoint = getScriptProperty_('RUNNER_ENDPOINT');
  if (!endpoint) {
    enqueueSelected();
    toast_('RUNNER_ENDPOINT が未設定のため queued にしました。定期実行で処理されます。');
    return;
  }

  const jobs = getSelectedJobRows_();
  const jobIds = jobs.rows.map(function(item) { return item.row.job_id; }).filter(Boolean);
  if (jobIds.length === 0) throw new Error('選択行に job_id がありません。');

  const token = getScriptProperty_('RUNNER_TOKEN');
  const headers = {'Content-Type': 'application/json'};
  if (token) headers.Authorization = 'Bearer ' + token;
  const response = UrlFetchApp.fetch(endpoint, {
    method: 'post',
    contentType: 'application/json',
    headers: headers,
    payload: JSON.stringify({job_ids: jobIds}),
    muteHttpExceptions: true
  });
  const code = response.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error('ランナー呼び出しに失敗しました: HTTP ' + code + ' ' + response.getContentText());
  }
  toast_(Utilities.formatString('%s 件を直接実行リクエストしました。', jobIds.length));
}

function getSelectedJobRows_() {
  const sheet = SpreadsheetApp.getActiveSheet();
  if (sheet.getName() !== A11Y_JOBS_SHEET) throw new Error('Jobs シートで行を選択してください。');
  const range = sheet.getActiveRange();
  if (!range) throw new Error('対象行を選択してください。');
  const headers = getHeaders_(sheet);
  const rows = [];
  const first = Math.max(range.getRow(), 2);
  const last = range.getLastRow();
  for (let rowNumber = first; rowNumber <= last; rowNumber++) {
    const values = sheet.getRange(rowNumber, 1, 1, headers.length).getValues()[0];
    rows.push({rowNumber: rowNumber, row: objectFromRow_(headers, values)});
  }
  return {sheet: sheet, headers: headers, rows: rows};
}

function updateSelectedJobRows_(callback) {
  const selected = getSelectedJobRows_();
  let updated = 0;
  selected.rows.forEach(function(item) {
    const updates = callback(item.row, selected.headers, item.rowNumber);
    if (!updates) return;
    Object.keys(updates).forEach(function(key) {
      const col = selected.headers.indexOf(key) + 1;
      if (col > 0) selected.sheet.getRange(item.rowNumber, col).setValue(updates[key]);
    });
    updated++;
  });
  return {updated: updated};
}

function getHeaders_(sheet) {
  return sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(function(v) { return String(v).trim(); });
}

function objectFromRow_(headers, values) {
  const row = {};
  headers.forEach(function(header, index) {
    if (header) row[header] = values[index];
  });
  return row;
}

function getColumnIndex_(headers, name) {
  return headers.indexOf(name) + 1;
}

function nowIso_() {
  return Utilities.formatDate(new Date(), 'Asia/Tokyo', "yyyy-MM-dd'T'HH:mm:ssXXX");
}

function toast_(message) {
  SpreadsheetApp.getActiveSpreadsheet().toast(message, 'A11y', 5);
}

function confirm_(message) {
  const ui = SpreadsheetApp.getUi();
  return ui.alert('A11y', message, ui.ButtonSet.YES_NO) === ui.Button.YES;
}

function getScriptProperty_(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}

function getConfigValue_(key) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(A11Y_CONFIG_SHEET);
  if (!sheet) return '';
  const values = sheet.getDataRange().getValues();
  for (let i = 1; i < values.length; i++) {
    if (String(values[i][0]).trim() === key) return String(values[i][1] || '').trim();
  }
  return '';
}
