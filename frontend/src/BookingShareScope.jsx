import React from 'react'
import { Alert, Card, Checkbox, DatePicker, Empty, Input, Pagination, Skeleton, Space, Tabs, Typography } from 'antd'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import { recordValue } from './recordDisplay'
import { useLanguage } from './i18n'
import { metricLabels, sectionLabels } from './healthLabels'

import { initialBookingScope, scopeCount } from './bookingScope'

export default function BookingShareScope({ value, onChange }) {
  const { t } = useLanguage()
  const [page, setPage] = React.useState(1), [query, setQuery] = React.useState('')
  const [recordResult, setRecords] = React.useState(null), [optionResult, setOptions] = React.useState(null), [error, setError] = React.useState('')
  const scope = value || initialBookingScope()
  const { from, to } = scope.measurement_period
  const recordKey = `${page}:${query}`, optionKey = `${from}:${to}`
  const records = recordResult?.key === recordKey ? recordResult : null
  const options = optionResult?.key === optionKey ? optionResult : null
  const patch = (changes) => onChange({ ...scope, ...changes })
  const toggle = (key, id, checked) => patch({ [key]: checked ? [...scope[key], id] : scope[key].filter((item) => item !== id) })
  React.useEffect(() => {
    let active = true
    api.get('/records', { params: { page, page_size: 10, q: query, archived: 'active' } }).then(({ data }) => { if (active) setRecords({ ...data, key: recordKey }) }).catch((failure) => { if (active) setError(apiMessage(failure)) })
    return () => { active = false }
  }, [page, query, recordKey])
  React.useEffect(() => {
    let active = true
    api.get('/sharing/scope-options', { params: { from, to } }).then(({ data }) => { if (active) setOptions({ ...data, key: optionKey }) }).catch((failure) => { if (active) setError(apiMessage(failure)) })
    return () => { active = false }
  }, [from, to, optionKey])
  const reports = <><Input.Search aria-label={t('Search reports to share')} placeholder={t('Search reports to share')} onSearch={(text) => { setQuery(text); setPage(1) }} allowClear />{!records ? <Skeleton active /> : <><Space direction="vertical" className="full-width" style={{ marginTop: 12 }}>{records.records.map((record) => <Card size="small" key={record.id}>
    <Checkbox disabled={record.sensitive || record.archived} checked={scope.record_ids.includes(record.id)} onChange={(event) => toggle('record_ids', record.id, event.target.checked)}>{recordValue(record, 'title')} · {record.record_date} · {t('Text summary')}</Checkbox>
    <div className="share-attachment-options">{(record.attachments || []).map((file) => <Checkbox key={file.id} disabled={record.sensitive || record.archived || Boolean(record.sensitive_fields?.length)} checked={scope.attachment_ids.includes(file.id)} onChange={(event) => toggle('attachment_ids', file.id, event.target.checked)}>{t('Full original')}: {recordValue(file, 'filename')}</Checkbox>)}</div>
  </Card>)}</Space><Pagination current={page} total={records.total} pageSize={10} showSizeChanger={false} onChange={setPage} /></>}
    {scope.record_ids.length > 0 && <><Typography.Paragraph>{t('Visible text fields')}</Typography.Paragraph><Checkbox.Group value={scope.shared_fields} onChange={(shared_fields) => patch({ shared_fields })} options={Object.entries({ title: 'Title', record_type: 'Record type', record_date: 'Date', source_name: 'Source', condition: 'Condition', content: 'Text summary' }).map(([value, label]) => ({ value, label: t(label) }))} /></>}
  </>
  const profile = !options ? <Skeleton active /> : <Space direction="vertical" className="full-width">{Object.entries(options.profile?.sections || {}).map(([section, data]) => <Card size="small" key={section}>
    <Checkbox checked={scope.profile_sections.includes(section)} onChange={(event) => toggle('profile_sections', section, event.target.checked)}>{t('Whole category')}: {t(sectionLabels[section])}</Checkbox>
    <div className="share-attachment-options">{data.items.map((item, index) => { const item_id = item.id || `legacy-${index}`, selected = scope.profile_items.some((entry) => entry.section === section && entry.item_id === item_id); return <Checkbox key={item_id} disabled={item.sensitive || scope.profile_sections.includes(section)} checked={!item.sensitive && (selected || scope.profile_sections.includes(section))} onChange={(event) => patch({ profile_items: event.target.checked ? [...scope.profile_items, { section, item_id }] : scope.profile_items.filter((entry) => !(entry.section === section && entry.item_id === item_id)) })}>{item.name}</Checkbox> })}</div>
  </Card>)}</Space>
  const readings = <><Typography.Paragraph>{t('Select a date range (UTC), then specific readings.')}</Typography.Paragraph><DatePicker.RangePicker allowClear={false} value={[dayjs(from), dayjs(to)]} onChange={(dates) => { if (dates) patch({ measurement_period: { from: dates[0].format('YYYY-MM-DD'), to: dates[1].format('YYYY-MM-DD') }, measurement_ids: [] }) }} />{!options ? <Skeleton active /> : <>{options.truncated && <Alert type="info" message={t('Narrow the date range to see additional readings.')} />}<Checkbox.Group className="share-reading-options" value={scope.measurement_ids} onChange={(measurement_ids) => patch({ measurement_ids })} options={options.measurements.map((item) => ({ value: item.id, label: `${t(metricLabels[item.metric_type])} ${item.value}${item.secondary_value != null ? ` / ${item.secondary_value}` : ''} ${item.unit} · ${dayjs(item.measured_at).format('YYYY-MM-DD HH:mm')}` }))} />{!options.measurements.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('No eligible readings in this period')} />}</>}</>
  return <div className="booking-share-scope">{error && <Alert type="error" message={t(error)} />}<Typography.Paragraph type="secondary">{t('Choose only what this clinician may see. New records are not added automatically; access is read-only.')}</Typography.Paragraph><Tabs items={[{ key: 'reports', label: t('Reports and records'), children: reports }, { key: 'profile', label: t('Health history'), children: profile }, { key: 'readings', label: t('Readings'), children: readings }]} />{scope.attachment_ids.length > 0 && <Checkbox checked={scope.acknowledge_original_files} onChange={(event) => patch({ acknowledge_original_files: event.target.checked })}>{t('I agree to share the complete original files. Hidden text fields do not redact PDFs or images.')}</Checkbox>}<div><Checkbox checked={scope.allow_download} onChange={(event) => patch({ allow_download: event.target.checked })}>{t('Allow export of selected content and download of selected originals')}</Checkbox></div><Typography.Text type="secondary">{t('{count} selected items', { count: scopeCount(scope) })}</Typography.Text></div>
}
