import dayjs from 'dayjs'

export function initialBookingScope() {
  return { record_ids: [], attachment_ids: [], profile_sections: [], profile_items: [], measurement_ids: [], shared_fields: ['title', 'record_type', 'record_date', 'source_name'], measurement_period: { from: dayjs().subtract(30, 'day').format('YYYY-MM-DD'), to: dayjs().format('YYYY-MM-DD') }, allow_download: false, acknowledge_original_files: false }
}
export const scopeCount = (scope) => ['record_ids', 'attachment_ids', 'profile_sections', 'profile_items', 'measurement_ids'].reduce((count, key) => count + (scope?.[key]?.length || 0), 0)

