import { t } from './i18n'
import { contextLabels, metricLabels, recordLabels, sectionLabels } from './healthLabels'

export function scopeLabel(scope) {
  const labels = { records: '{count} record summaries', attachments: '{count} original files', profile: '{count} health history categories', measurements: '{count} readings' }
  return labels[scope.kind] ? t(labels[scope.kind], { count: scope.count }) : scope.label || ''
}

const detailLabels = {
  grant_id: 'Sharing permission', appointment_id: 'Appointment', slot_id: 'Time slot', recipient_id: 'Recipient',
  attachment_id: 'Original file ID', record_id: 'Record ID', measurement_id: 'Reading ID', annotation_id: 'Note ID',
  filename: 'Filename', size: 'Size in bytes', version: 'Version', source_version: 'Source version',
  revision: 'Revision', profile_revision: 'Health history revision', extraction_id: 'Extraction ID', candidate_id: 'Candidate ID',
  shared_fields: 'Shared text fields', changed_fields: 'Changed fields', sensitive_fields: 'Hidden fields', sensitive: 'Sensitive',
  scope: 'Shared content', objects: 'Content accessed', kind: 'Content type', count: 'Count', label: 'Description',
  action: 'Action', reason: 'Reason', method: 'Method', result: 'Result', source: 'Source', record_type: 'Record type',
  batch_id: 'Import batch', external_id: 'Hospital document ID', status: 'Status', processed_pages: 'Processed pages', total_pages: 'Total pages',
  candidate_count: 'Reading candidates', fact_count: 'Health history candidates', measurement_count: 'Readings',
  section: 'Health history category', sections: 'Health history categories', item_id: 'Item ID', metric_type: 'Measurement',
  context: 'Measurement context', from: 'From', to: 'To', starts_at: 'Starts at', expires_at: 'Expires at',
  allow_download: 'Download allowed', preview: 'Preview', simulation: 'Simulation', source_type: 'Source type',
  title: 'Title', content: 'Text summary', condition: 'Condition', record_date: 'Date', source_name: 'Source',
}

// Translate only structural keys and known codes. File names, names, notes, and
// arbitrary historical values are user content and deliberately remain verbatim.
export function auditDetails(value, key = '') {
  if (value === null || value === undefined) return value
  if (Array.isArray(value)) return value.map((item) => auditDetails(item, key))
  if (typeof value === 'object') {
    if (['records', 'attachments', 'profile', 'measurements'].includes(value.kind) && Number.isInteger(value.count)) return scopeLabel(value)
    return Object.fromEntries(Object.entries(value).map(([name, entry]) => [t(detailLabels[name] || name.replaceAll('_', ' ')), auditDetails(value.kind === 'attachment' && name === 'label' && entry === '未授权文件' ? t('File outside the sharing scope') : entry, name)]))
  }
  if (['shared_fields', 'changed_fields', 'sensitive_fields'].includes(key)) return t(detailLabels[value] || value)
  if (['section', 'sections'].includes(key)) return sectionLabels[value] || value
  if (key === 'record_type') return recordLabels[value] || value
  if (key === 'metric_type') return metricLabels[value] || value
  if (key === 'context') return contextLabels[value] || value
  if (['reason', 'method', 'result', 'status', 'source_type'].includes(key)) {
    const codes = { appointment_cancelled: 'Appointment cancelled', allowed: 'Allowed', blocked: 'Blocked', complete: 'Complete', partial: 'Partial', failed: 'Failed', pending: 'Pending', document_index: 'Document text index', text: 'Text', owner: 'Owner', hospital: 'Hospital', self: 'Personal entry' }
    return t(codes[value] || value)
  }
  if (typeof value === 'boolean') return t(value ? 'Yes' : 'No')
  return value
}
