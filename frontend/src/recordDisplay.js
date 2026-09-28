import { t } from './i18n'

// Only server-identified sample fields carry approved translations. Real titles,
// uploaded filenames and patient-authored text always retain their exact value.
export function recordValue(record, field) {
  return record?.sample_display?.[field] ? t(record.sample_display[field]) : record?.[field]
}
