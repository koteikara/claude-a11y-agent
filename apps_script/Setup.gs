function setupSheetUx() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(A11Y_JOBS_SHEET);
  if (!sheet) throw new Error('Jobs シートが見つかりません。');
  const headers = getHeaders_(sheet);
  const statusCol = getColumnIndex_(headers, 'status');
  const reviewStatusCol = getColumnIndex_(headers, 'review_status');
  if (!statusCol) throw new Error('Jobs.status 列が見つかりません。');

  const maxRows = Math.max(sheet.getMaxRows() - 1, 1);
  const statusRange = sheet.getRange(2, statusCol, maxRows, 1);
  const statusRule = SpreadsheetApp.newDataValidation()
    .requireValueInList(A11Y_STATUS_VALUES, true)
    .setAllowInvalid(false)
    .build();
  statusRange.setDataValidation(statusRule);

  if (reviewStatusCol) {
    const reviewRange = sheet.getRange(2, reviewStatusCol, maxRows, 1);
    const reviewRule = SpreadsheetApp.newDataValidation()
      .requireValueInList(A11Y_REVIEW_STATUS_VALUES, true)
      .setAllowInvalid(false)
      .build();
    reviewRange.setDataValidation(reviewRule);
  }

  const preserved = sheet.getConditionalFormatRules().filter(function(rule) {
    const ranges = rule.getRanges();
    return !ranges.some(function(range) {
      return range.getSheet().getName() === A11Y_JOBS_SHEET && range.getColumn() === statusCol;
    });
  });

  const specs = [
    {value: 'queued', color: '#eeeeee'},
    {value: 'running', color: '#cfe2f3'},
    {value: 'done', color: '#d9ead3'},
    {value: 'error', color: '#f4cccc'},
    {value: 'needs_review', color: '#fce5cd'}
  ];
  const rules = specs.map(function(spec) {
    return SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo(spec.value)
      .setBackground(spec.color)
      .setRanges([statusRange])
      .build();
  });
  sheet.setConditionalFormatRules(preserved.concat(rules));
  toast_('status / review_status のプルダウンと色分けを適用しました。');
}

function installTriggers() {
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'notifyOnStatusChange') ScriptApp.deleteTrigger(trigger);
  });
  ScriptApp.newTrigger('notifyOnStatusChange').timeBased().everyMinutes(5).create();
  initializeStatusSnapshot_();
  toast_('notifyOnStatusChange の時間主導トリガを設置しました（5分間隔）。');
}
