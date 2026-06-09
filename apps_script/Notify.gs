const A11Y_STATUS_SNAPSHOT_KEY = 'A11Y_STATUS_SNAPSHOT';

function notifyOnStatusChange() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const jobsSheet = ss.getSheetByName(A11Y_JOBS_SHEET);
  if (!jobsSheet) {
    console.log('Jobs シートがないため通知をスキップします。');
    return;
  }

  const props = PropertiesService.getScriptProperties();
  const snapshotJson = props.getProperty(A11Y_STATUS_SNAPSHOT_KEY);
  const previous = JSON.parse(snapshotJson || '{}');
  const current = {};
  const reviewByJob = getReviewSummaryByJob_();
  const jobs = readSheetObjects_(jobsSheet);
  let sent = 0;

  jobs.forEach(function(job) {
    const jobId = String(job.job_id || '').trim();
    if (!jobId) return;
    const status = String(job.status || '').trim();
    current[jobId] = status;
    const oldStatus = previous[jobId] || '';
    if (snapshotJson && status !== oldStatus && A11Y_TERMINAL_STATUSES.indexOf(status) !== -1) {
      notifyJob_(job, oldStatus, reviewByJob[jobId] || []);
      sent++;
    }
  });

  props.setProperty(A11Y_STATUS_SNAPSHOT_KEY, JSON.stringify(current));
  console.log('A11y status snapshot updated. notifications=' + sent);
}

function notifyJob_(job, oldStatus, reviews) {
  const subject = Utilities.formatString('[A11y] %s: %s', job.status, job.job_id || job.page_id || '(job)');
  const body = buildNotificationBody_(job, oldStatus, reviews);
  const to = String(job.reviewer || getScriptProperty_('NOTIFY_DEFAULT_EMAIL') || '').trim();
  if (to) {
    MailApp.sendEmail({to: to, subject: subject, body: body});
  } else {
    console.log('通知先メール未設定のため MailApp 通知をスキップ: ' + subject);
  }

  const webhook = getScriptProperty_('CHAT_WEBHOOK');
  if (webhook) {
    UrlFetchApp.fetch(webhook, {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify({text: subject + '\n' + body}),
      muteHttpExceptions: true
    });
  }
}

function buildNotificationBody_(job, oldStatus, reviews) {
  const lines = [
    'A11y ジョブの状態が変わりました。',
    '',
    'job_id: ' + (job.job_id || ''),
    'site: ' + (job.site || ''),
    'page_id: ' + (job.page_id || ''),
    'status: ' + (oldStatus || '(none)') + ' -> ' + (job.status || ''),
    'review_status: ' + (job.review_status || ''),
    'ai_output_link: ' + (job.ai_output_link || ''),
    'gold_output_link: ' + (job.gold_output_link || ''),
    'error: ' + (job.error || '')
  ];
  if (String(job.status || '') === 'needs_review' && reviews.length) {
    lines.push('', 'Review 要約:');
    reviews.slice(0, 5).forEach(function(item, index) {
      lines.push(Utilities.formatString(
        '%s. [%s] %s / %s / %s', index + 1, item.rule_id || '', item.message || '', item.location || '', item.suggestion || ''));
    });
    if (reviews.length > 5) lines.push('...ほか ' + (reviews.length - 5) + ' 件');
  }
  return lines.join('\n');
}

function getReviewSummaryByJob_() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(A11Y_REVIEW_SHEET);
  if (!sheet) return {};
  const grouped = {};
  readSheetObjects_(sheet).forEach(function(row) {
    const jobId = String(row.job_id || '').trim();
    if (!jobId) return;
    if (!grouped[jobId]) grouped[jobId] = [];
    grouped[jobId].push(row);
  });
  return grouped;
}

function readSheetObjects_(sheet) {
  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];
  const headers = values[0].map(function(v) { return String(v).trim(); });
  return values.slice(1).map(function(row) { return objectFromRow_(headers, row); });
}

function initializeStatusSnapshot_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const jobsSheet = ss.getSheetByName(A11Y_JOBS_SHEET);
  if (!jobsSheet) return;
  const snapshot = {};
  readSheetObjects_(jobsSheet).forEach(function(job) {
    const jobId = String(job.job_id || '').trim();
    if (jobId) snapshot[jobId] = String(job.status || '').trim();
  });
  PropertiesService.getScriptProperties().setProperty(A11Y_STATUS_SNAPSHOT_KEY, JSON.stringify(snapshot));
}
