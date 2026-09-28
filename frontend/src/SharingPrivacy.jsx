import { t, useLanguage } from './i18n'
import React from 'react'
import { PlusOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, DatePicker, Descriptions, Empty, Form, Input, List, Modal, Pagination, Popconfirm, Select, Skeleton, Space, Steps, Table, Tabs, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { Link, useSearchParams } from 'react-router-dom'
import api, { apiMessage } from './api'
import { recordValue } from './recordDisplay'
import Guidance from './Guidance'
import DocumentPreview from './DocumentPreview'
import { metricLabels, sectionLabels, recordLabels, contextLabels } from './healthLabels'
import { scopeLabel, auditDetails } from './sharingLabels'
import './sharing.css'

const { Title, Paragraph, Text } = Typography
const fields = { get title() { return t("标题") }, get record_type() { return t("资料类型") }, get record_date() { return t("资料日期") }, get source_name() { return t("来源机构") }, get condition() { return t("疾病名称") }, get content() { return t("文字摘要") } }
const profileFields = { get name() { return t("名称") }, get detail() { return t("说明") }, get relationship() { return t("亲属关系") }, get dose() { return t("剂量") }, get frequency() { return t("频次") }, get severity() { return t("反应程度") }, get start_date() { return t("开始日期") }, get end_date() { return t("结束日期") } }
const statuses = { get active() { return t("生效中") }, get scheduled() { return t("尚未开始") }, get expired() { return t("已到期") }, get revoked() { return t("已撤销") } }
const profileStatuses = { get unknown() { return t("尚未记录") }, get none() { return t("本人确认没有") }, get recorded() { return t("已有记录") } }
const actions = { get document_indexed() { return t("整理全文") }, get record_classified() { return t("调整分类") }, get health_fact_confirmed() { return t("确认健康信息") }, get appointment_booked() { return t("Appointment booked") }, get view() { return t("查看") }, get download() { return t("下载") }, get record_created() { return t("新增档案") }, get edit() { return t("编辑档案") }, get attachment_added() { return t("添加原文件") }, get attachment_view() { return t("预览原文件") }, get attachment_deleted() { return t("删除原文件") }, get health_profile_updated() { return t("更新健康史") }, get archive() { return t("归档") }, get restore() { return t("恢复归档") }, get privacy_updated() { return t("修改隐私设置") }, get note_added() { return t("添加备注") }, get correction_added() { return t("提交纠错") }, get correction_response() { return t("模拟机构答复") }, get record_imported() { return t("同步医院资料") }, get report_extraction_prepared() { return t("识别报告") }, get extraction_text_reviewed() { return t("校正识别文字") }, get report_reading_confirmed() { return t("确认导入指标") }, get measurement_created() { return t("新增指标") }, get measurement_corrected() { return t("更正指标") }, get measurement_voided() { return t("作废指标") }, get grant_created() { return t("创建档案授权") }, get share_scope_created() { return t("确认共享范围") }, get grant_revoked() { return t("撤销授权") }, get simulated_recipient_access() { return t("模拟接收方访问") }, get share_owner_preview() { return t("本人预览共享内容") }, get shared_file_access() { return t("模拟接收方访问原件") }, get shared_file_owner_preview() { return t("本人预览共享原件") }, get access_reviewed() { return t("复核访问记录") } }
const reasons = { get allowed() { return t("符合当前授权") }, get revoked() { return t("授权已撤销") }, get expired() { return t("授权已到期") }, get scheduled() { return t("授权尚未生效") }, get recipient_mismatch() { return t("接收方不匹配") }, get download_not_allowed() { return t("未开放下载") }, get scope_private_or_archived() { return t("资料已设私密、归档或不再有效") }, get attachment_not_granted() { return t("文件不在授权范围") }, get file_unavailable() { return t("文件已删除") }, get file_version_changed() { return t("原文件版本已改变") } }
const dateText = (value) => dayjs(value).format('YYYY-MM-DD HH:mm')
const readingText = (item) => `${metricLabels[item.metric_type]} ${item.value}${item.secondary_value != null ? ` / ${item.secondary_value}` : ''} ${item.unit}`
const sourceText = (event) => event.source === 'mock' ? t('模拟接收人') : event.source === 'simulation' ? t('模拟医院') : event.source === 'system' || event.actor_name === 'System' ? t('系统整理') : t('本人')

export function SharedContent({ data = {}, onFile }) {
  useLanguage()
  return <div className="share-preview-content">
    {data.records?.length > 0 && <section><Title level={5}>{t("档案文字摘要")}</Title>{data.records.map((record, index) => <Card size="small" key={index}><Descriptions column={1} items={Object.entries(record).filter(([key]) => fields[key]).map(([key, value]) => ({ key, label: fields[key] || key, children: <span className="share-pre-wrap">{key === 'record_type' ? recordLabels[value] || value : recordValue(record, key) || '—'}</span> }))} /></Card>)}</section>}
    {data.attachments?.length > 0 && <section><Title level={5}>{t("单独授权的完整原文件")}</Title><Paragraph type="secondary">{t("这些文件未自动打码。未选择的附件及 OCR 全文不会随文字摘要开放。")}</Paragraph><List dataSource={data.attachments} renderItem={(file) => <List.Item actions={onFile ? [<Button key="view" onClick={() => onFile(file)}>{t("预览原件")}</Button>, ...(file.download_url ? [<Button key="download" onClick={() => onFile(file, true)}>{t("下载原件")}</Button>] : [])] : []}><List.Item.Meta title={recordValue(file, 'filename')} description={`${Math.ceil(file.size / 1024)} KB`} /></List.Item>} /></section>}
    {data.profile?.length > 0 && <section><Title level={5}>{t("健康史快照")}</Title>{data.profile.map((section) => <Card size="small" key={section.section} title={t('{section} · Snapshot version {revision}', { section: sectionLabels[section.section], revision: section.revision })}><Text type="secondary">{profileStatuses[section.status]}</Text>{section.items.map((item) => <Descriptions key={item.id} column={1} size="small" items={Object.entries(item).filter(([key, value]) => profileFields[key] && value).map(([key, value]) => ({ key, label: profileFields[key], children: value }))} />)}</Card>)}</section>}
    {data.measurements?.length > 0 && <section><Title level={5}>{t("指标读数快照")}</Title><Paragraph type="secondary">{data.measurement_period?.from}{t(" 至 ")}{data.measurement_period?.to}{t("（UTC 日期）。不含个人备注、报告识别全文或其他读数。")}</Paragraph><List dataSource={data.measurements} renderItem={(item) => <List.Item><List.Item.Meta title={readingText(item)} description={`${dateText(item.measured_at)} · ${contextLabels[item.context] || item.context || t('未填场景')}`} /></List.Item>} /></section>}
  </div>
}

export default function SharingPrivacyPage() {
  useLanguage()
  const [params, setParams] = useSearchParams()
  const activeTab = ['permissions', 'activity', 'audit'].includes(params.get('tab')) ? params.get('tab') : 'permissions'
  const linkedGrantOpened = React.useRef(false)
  const [form] = Form.useForm()
  const [data, setData] = React.useState({ grants: [], recipients: [], events: [], total: 0, audit: [], auditTotal: 0 })
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [refresh, setRefresh] = React.useState(0)
  const [page, setPage] = React.useState(1)
  const [auditPage, setAuditPage] = React.useState(1)
  const [filters, setFilters] = React.useState({ action: '', result: '', review: '' })
  const [open, setOpen] = React.useState(false)
  const [draft, setDraft] = React.useState(null)
  const [preview, setPreview] = React.useState(null)
  const [grant, setGrant] = React.useState(null)
  const [viewer, setViewer] = React.useState(null)
  const [records, setRecords] = React.useState({ key: '', records: [], total: 0 })
  const [recordPage, setRecordPage] = React.useState(1)
  const [search, setSearch] = React.useState('')
  const [recordQuery, setRecordQuery] = React.useState('')
  const [recordType, setRecordType] = React.useState('')
  const [recordRange, setRecordRange] = React.useState(null)
  const [range, setRange] = React.useState(() => { const today = dayjs(new Date().toISOString().slice(0, 10)); return [today.subtract(30, 'day'), today] })
  const [options, setOptions] = React.useState({ key: '', measurements: [] })
  const recordIds = Form.useWatch('record_ids', form) || []
  const attachmentIds = Form.useWatch('attachment_ids', form) || []
  const profileSections = Form.useWatch('profile_sections', form) || []
  const profileKeys = Form.useWatch('profile_keys', form) || []
  const measurementIds = Form.useWatch('measurement_ids', form) || []
  const recordFrom = recordRange?.[0]?.format('YYYY-MM-DD') || ''
  const recordTo = recordRange?.[1]?.format('YYYY-MM-DD') || ''
  const from = range[0].format('YYYY-MM-DD'), to = range[1].format('YYYY-MM-DD')
  const recordKey = JSON.stringify([recordPage, recordQuery, recordType, recordFrom, recordTo, refresh])
  const optionKey = JSON.stringify([from, to, refresh])
  const disabled = loading || saving || Boolean(error)
  const count = recordIds.length + attachmentIds.length + profileSections.length + profileKeys.length + measurementIds.length
  const reload = () => { setLoading(true); setRefresh((value) => value + 1); window.dispatchEvent(new Event('notifications:changed')) }

  React.useEffect(() => {
    let active = true
    Promise.all([api.get('/sharing/grants'), api.get('/sharing/recipients'), api.get('/sharing/access-events', { params: { page, page_size: 10, ...filters } }), api.get('/sharing/audit-events', { params: { page: auditPage, page_size: 10 } })])
      .then(([a, b, c, d]) => { if (active) { setData({ grants: a.data.grants, recipients: b.data.recipients, ...c.data, audit: d.data.events, auditTotal: d.data.total }); setError(''); setGrant((old) => old ? a.data.grants.find((item) => item.id === old.id) || null : null) } })
      .catch((failure) => { if (active) setError(apiMessage(failure)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [page, auditPage, filters, refresh])
  React.useEffect(() => {
    if (!open) return
    let active = true
    api.get('/records', { params: { page: recordPage, page_size: 20, q: recordQuery, type: recordType, from: recordFrom, to: recordTo, archived: 'active' } }).then(({ data: result }) => { if (active) setRecords({ ...result, key: recordKey }) }).catch((failure) => { if (active) setRecords({ key: recordKey, records: [], total: 0, error: apiMessage(failure) }) })
    return () => { active = false }
  }, [open, recordPage, recordQuery, recordType, recordFrom, recordTo, recordKey])
  React.useEffect(() => {
    if (!open) return
    let active = true
    api.get('/sharing/scope-options', { params: { from, to } }).then(({ data: result }) => { if (active) setOptions({ ...result, key: optionKey }) }).catch((failure) => { if (active) setOptions({ key: optionKey, measurements: [], error: apiMessage(failure) }) })
    return () => { active = false }
  }, [open, from, to, optionKey])
  React.useEffect(() => {
    const linked = data.grants.find((item) => String(item.id) === params.get('grant'))
    if (linked && !linkedGrantOpened.current) { linkedGrantOpened.current = true; setGrant(linked) }
  }, [data.grants, params])

  function openShare() {
    form.resetFields()
    form.setFieldsValue({ starts_at: dayjs(), expires_at: dayjs().add(7, 'day'), record_ids: Number(params.get('record')) ? [Number(params.get('record'))] : [], attachment_ids: [], profile_sections: [], profile_keys: [], measurement_ids: [], shared_fields: Object.keys(fields).slice(0, 4), allow_download: false, acknowledge_original_files: false })
    setDraft(null); setRecordPage(1); setOpen(true)
  }
  function setSelection(name, values, value, checked) { form.setFieldValue(name, checked ? [...values, value] : values.filter((item) => item !== value)) }
  function clearRecords() { form.setFieldsValue({ record_ids: [], attachment_ids: [], acknowledge_original_files: false }); setRecordPage(1) }
  async function reviewDraft() {
    setSaving(true)
    try {
      const { profile_keys = [], ...values } = await form.validateFields()
      const payload = { ...values, profile_items: profile_keys.map((key) => { const [section, ...id] = key.split(':'); return { section, item_id: id.join(':') } }), measurement_period: { from, to }, starts_at: values.starts_at.toISOString(), expires_at: values.expires_at.toISOString() }
      const response = await api.post('/sharing/grants/draft-preview', payload)
      setDraft({ payload: { ...payload, preview_token: response.data.preview_token }, content: response.data })
    } catch (failure) { if (!failure.errorFields) message.error(apiMessage(failure)) }
    finally { setSaving(false) }
  }
  async function confirm() {
    setSaving(true)
    try { await api.post('/sharing/grants', draft.payload); setOpen(false); message.success(t('已保存固定内容的共享授权。')); reload() }
    catch (failure) { message.error(apiMessage(failure)); if (failure.response?.status === 409) setDraft(null) }
    finally { setSaving(false) }
  }
  async function revoke(id) {
    setSaving(true)
    try { await api.patch(`/sharing/grants/${id}/revoke`); setGrant(null); setPreview(null); setViewer(null); reload() }
    catch (failure) { message.error(apiMessage(failure)) }
    finally { setSaving(false) }
  }
  function download(blob, name) { const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }
  async function access(simulation = false, action = 'view') {
    setSaving(true)
    try {
      const response = await api.post(`/sharing/grants/${grant.id}/${simulation ? 'simulate-access' : 'preview'}`, { action })
      if (action === 'download' && simulation) download(new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' }), 'shared-health-snapshot.json')
      else setPreview(response.data)
    } catch (failure) { if (failure.response?.status === 403) setPreview({ blocked: true, message: reasons[failure.response.data.reason] || apiMessage(failure) }); else message.error(apiMessage(failure)) }
    finally { setSaving(false); reload() }
  }
  async function viewFile(file, savingFile = false) {
    const path = savingFile ? file.download_url : file.preview_url || `/api/records/${file.record_id}/attachments/${file.id}`
    if (!path) return
    if (!savingFile) { setViewer({ ...file, url: path }); return }
    setSaving(true)
    try { const response = await api.get(path.replace(/^\/api/, ''), { responseType: 'blob' }); download(response.data, file.filename) }
    catch (failure) { let detail = t('无法打开文件，授权或资料状态可能已改变。'); if (failure.response?.data instanceof Blob) { try { detail = JSON.parse(await failure.response.data.text()).message || detail } catch { /* Keep fallback. */ } } message.error(t(detail)) }
    finally { setSaving(false); if (file.preview_url) reload() }
  }
  async function reviewEvent(event) {
    setSaving(true)
    try { await api.patch(`/sharing/${event.event_kind === 'scope' ? 'scope-events' : 'access-events'}/${event.id}/review`); reload() }
    catch (failure) { message.error(apiMessage(failure)) }
    finally { setSaving(false) }
  }
  function filter(key, value) { setLoading(true); setFilters((old) => ({ ...old, [key]: value })); setPage(1) }

  const recordsPanel = <>
    <Input.Search aria-label={t("搜索可共享档案")} placeholder={t("标题、疾病或记录内容")} value={search} onChange={(event) => setSearch(event.target.value)} onSearch={(value) => { setRecordQuery(value); clearRecords() }} enterButton={t("搜索")} allowClear />
    <Space wrap className="share-filter-row"><Select aria-label={t("资料类型")} value={recordType} onChange={(value) => { setRecordType(value); clearRecords() }} options={[{ value: '', label: t('全部类型') }, ...Object.entries(recordLabels).map(([value, label]) => ({ value, label }))]} /><DatePicker.RangePicker aria-label={t("资料日期范围")} value={recordRange} onChange={(value) => { setRecordRange(value); clearRecords() }} /></Space><Paragraph type="secondary">{t("文字摘要和完整原件分别选择。翻页保留选择，改变筛选会清除。")}</Paragraph>
    {records.key !== recordKey ? <Skeleton active /> : records.error ? <Alert type="error" message={t(records.error)} /> : <div className="share-record-options">{records.records.map((record) => {
      const locked = record.sensitive || record.archived || Boolean(record.archived_at)
      return <Card size="small" key={record.id}><Checkbox disabled={locked} checked={recordIds.includes(record.id)} onChange={(event) => setSelection('record_ids', recordIds, record.id, event.target.checked)}><b>{recordValue(record, 'title')}</b><span className="share-record-meta">{recordLabels[record.record_type]} · {record.record_date}{t(" · 文字摘要")}</span></Checkbox><div className="share-attachment-options">{(record.attachments || []).map((file) => <Checkbox key={file.id} disabled={locked || Boolean(record.sensitive_fields?.length)} checked={attachmentIds.includes(file.id)} onChange={(event) => setSelection('attachment_ids', attachmentIds, file.id, event.target.checked)}>{t("完整原件：")}{recordValue(file, 'filename')}</Checkbox>)}{(locked || Boolean(record.sensitive_fields?.length)) && <Text type="secondary">{t("敏感、隐藏字段或归档限制：完整原件不可选。")}</Text>}</div></Card>
    })}</div>}
    <Pagination current={recordPage} total={records.total} pageSize={20} showSizeChanger={false} onChange={setRecordPage} />
    {recordIds.length > 0 && <Form.Item label={t("这些档案的哪些文字可以看")} name="shared_fields"><Checkbox.Group options={Object.entries(fields).map(([value, label]) => ({ value, label }))} /></Form.Item>}
    {attachmentIds.length > 0 && <Form.Item name="acknowledge_original_files" valuePropName="checked" rules={[{ validator: (_, value) => value ? Promise.resolve() : Promise.reject(new Error(t('请确认原件的完整可见范围。'))) }]}><Checkbox>{t("我已检查并同意共享完整原件；隐藏文字字段不会自动给 PDF 或图片打码。")}</Checkbox></Form.Item>}
  </>
  const profilePanel = options.key !== optionKey ? <Skeleton active /> : options.error ? <Alert type="error" message={t(options.error)} /> : <><Paragraph type="secondary">{t("选择整个类别或具体条目。敏感条目不开放，后续新增内容不会自动加入。")}</Paragraph>{Object.entries(options.profile?.sections || {}).map(([key, section]) => <Card size="small" key={key} className="share-profile-option"><Checkbox checked={profileSections.includes(key)} onChange={(event) => setSelection('profile_sections', profileSections, key, event.target.checked)}>{t('Whole category: {category} ({status}, excluding sensitive items)', { category: sectionLabels[key], status: profileStatuses[section.status] })}</Checkbox><div className="share-attachment-options">{section.items.map((item, index) => { const value = `${key}:${item.id || `legacy-${index}`}`; return <Checkbox key={value} disabled={item.sensitive || profileSections.includes(key)} checked={!item.sensitive && (profileSections.includes(key) || profileKeys.includes(value))} onChange={(event) => setSelection('profile_keys', profileKeys, value, event.target.checked)}>{item.name}{item.sensitive && <Tag>{t("敏感")}</Tag>}</Checkbox> })}</div></Card>)}</>
  const readingsPanel = <><Paragraph>{t("按 UTC 日期筛选后，选择具体读数。已更正、作废或来源受隐私限制的读数不会列入。")}</Paragraph><DatePicker.RangePicker aria-label={t("指标日期范围")} allowClear={false} value={range} onChange={(value) => { if (value) { setRange(value); form.setFieldValue('measurement_ids', []) } }} />{options.key !== optionKey ? <Skeleton active /> : options.error ? <Alert type="error" message={t(options.error)} /> : <>{options.truncated && <Alert type="info" message={t("该期间超过 500 条读数，请缩小范围查看更多。")} />}<Form.Item name="measurement_ids"><Checkbox.Group className="share-reading-options" options={options.measurements.map((item) => ({ value: item.id, label: `${readingText(item)} · ${dateText(item.measured_at)} · ${contextLabels[item.context] || item.context || t('未填场景')}` }))} /></Form.Item>{!options.measurements.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("此期间没有可共享的有效读数")} />}</>}</>
  const activityPanel = <Card><Paragraph type="secondary">{t("记录本地接收方模拟的查看、下载和拦截。本人预览会出现在“档案操作记录”。")}</Paragraph><Space wrap>{[['action', t('操作'), [['view', t('查看')], ['download', t('下载')]]], ['result', t('结果'), [['allowed', t('允许')], ['blocked', t('已拦截')]]], ['review', t('复核状态'), [['pending', t('未复核')], ['reviewed', t('已复核')]]]].map(([key, label, values]) => <Select key={key} aria-label={t('Access {label}', { label })} value={filters[key]} onChange={(value) => filter(key, value)} options={[{ value: '', label: t('All {label}', { label }) }, ...values.map(([value, text]) => ({ value, label: text }))]} />)}</Space><List dataSource={data.events} locale={{ emptyText: t('暂无符合条件的访问记录') }} renderItem={(event) => <List.Item actions={[event.reviewed_at ? <Tag key="reviewed">{t("已复核")}</Tag> : <Button key="review" disabled={disabled} onClick={() => reviewEvent(event)}>{t("标为已复核")}</Button>]}><List.Item.Meta title={<Space wrap><Text strong>{event.recipient.full_name}</Text><Tag>{event.source === 'mock' ? t('模拟接收人') : t('历史演示数据')}</Tag><Tag>{actions[event.action]}</Tag><Tag color={event.result === 'blocked' ? 'red' : 'green'}>{event.result === 'blocked' ? t('已拦截') : t('允许')}</Tag></Space>} description={<>{recordValue(event.record, 'title')} · {dateText(event.occurred_at)}<br />{reasons[event.reason] || event.reason}</>} /></List.Item>} /><Pagination current={page} total={data.total} pageSize={10} showSizeChanger={false} onChange={(value) => { setLoading(true); setPage(value) }} /></Card>

  return <div className="page-stack sharing-page">
    <div className="page-heading"><div><Title level={1}>{t("共享与访问")}</Title><Paragraph>{t("明确选资料，再决定谁能看、可以看多久。")}</Paragraph></div><Button type="primary" icon={<PlusOutlined />} disabled={disabled} onClick={openShare}>{t("新建共享")}</Button></div>
    <Guidance id="sharing-scope" title={t("共享范围与演示边界")}><Paragraph>{t("每次授权固定确认的内容，新资料不会自动开放。可撤销后续访问；已看过或保存的资料无法远程收回。医生、健康管理师为演示接收人，没有真实外部账号连接。")}</Paragraph><Paragraph>{t("下载权限控制本站导出接口，无法阻止浏览器对已预览内容另存或截图。")}</Paragraph></Guidance>
    {error && <Alert type="error" message={t(error)} action={<Button onClick={reload}>{t("重试")}</Button>} />}
    {loading ? <Skeleton active /> : !error && <Tabs activeKey={activeTab} onChange={(tab) => { const next = new URLSearchParams(params); next.set("tab", tab); setParams(next, { replace: true }) }} items={[
      { key: 'permissions', label: t('Sharing permissions ({count})', { count: data.grants.length }), children: data.grants.length ? <div className="grant-list">{data.grants.map((item) => <Card key={item.id}><Space wrap><Title level={4}>{item.recipient.full_name}</Title><Tag>{statuses[item.status]}</Tag><Tag>{t("演示接收人")}</Tag></Space><Paragraph>{item.scope_summary?.map(scopeLabel).join(' · ') || t('{count} record summaries', { count: item.records.length })} · {item.allow_download ? t('可查看和导出') : t('仅查看')}</Paragraph><Paragraph type="secondary">{t("截止 ")}{dateText(item.expires_at)} · {item.scope_mode === 'fixed_snapshot' ? t('固定范围与版本') : t('旧版文字授权，范围未扩展')}</Paragraph><Space><Button onClick={() => setGrant(item)}>{t("查看授权")}</Button>{['active', 'scheduled'].includes(item.status) && <Popconfirm title={t("撤销此授权的后续访问？")} onConfirm={() => revoke(item.id)}><Button danger>{t("撤销")}</Button></Popconfirm>}</Space></Card>)}</div> : <Empty description={t("尚未创建共享授权")} /> },
      { key: 'activity', label: t('Access history ({count})', { count: data.total }), children: activityPanel },
      { key: 'audit', label: t('档案操作记录'), children: <Card><Paragraph type="secondary">{t("查看本人、系统整理、模拟医院和模拟接收人做过什么。展开可看操作详情。")}</Paragraph><Table rowKey="id" dataSource={data.audit} scroll={{ x: 730 }} pagination={false} expandable={{ expandedRowRender: (event) => <pre className="share-audit-details">{JSON.stringify(auditDetails(event.details), null, 2)}</pre>, rowExpandable: (event) => Object.keys(event.details || {}).length > 0 }} columns={[{ title: t('时间'), dataIndex: 'created_at', render: dateText }, { title: t('操作'), dataIndex: 'action', render: (value) => actions[value] || value.replaceAll('_', ' ') }, { title: t('资料'), render: (_, event) => event.record_id ? <Link to={`/records/${event.record_id}`}>{t("档案 #")}{event.record_id}</Link> : event.details?.measurement_id ? <Link to={`/insights?reading=${event.details.measurement_id}`}>{t("指标 #")}{event.details.measurement_id}</Link> : event.details?.grant_id ? t(`授权 #${event.details.grant_id}`) : t('个人资料') }, { title: t('操作者'), render: (_, event) => <>{sourceText(event)}{sourceText(event) === t('本人') && <><br /><Text type="secondary">{event.actor_name}</Text></>}</> }, { title: t('结果'), dataIndex: 'result', render: (value) => value === 'blocked' ? t('已拦截') : t('完成') }]} /><Pagination current={auditPage} total={data.auditTotal} pageSize={10} showSizeChanger={false} onChange={(value) => { setLoading(true); setAuditPage(value) }} /></Card> },
    ]} />}
    <Modal width={860} title={t("新建共享")} open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden><Steps current={draft ? 1 : 0} size="small" items={[{ title: t('选择接收人、内容与期限') }, { title: t('预览并确认授权') }]} />
      <Form form={form} layout="vertical" disabled={disabled} className="share-form" style={{ display: draft ? 'none' : 'block' }}>
        <div className="two-field-row"><Form.Item label={t("演示接收人")} name="recipient_id" rules={[{ required: true, message: t('请选择接收人') }]}><Select options={data.recipients.map((item) => ({ value: item.id, label: `${item.full_name} · ${({ Doctor: t('医生'), 'General practitioner': t('全科医生'), 'Health manager': t('健康管理师') })[item.role] || item.role} · ${item.organisation}` }))} /></Form.Item><Form.Item label={t("共享用途")} name="purpose" rules={[{ required: true, message: t('请填写共享用途') }]}><Input maxLength={200} placeholder={t("例如：复诊时查看最近检查")} /></Form.Item></div>
        {['record_ids', 'attachment_ids', 'profile_sections', 'profile_keys'].map((name) => <Form.Item key={name} name={name} hidden><Input /></Form.Item>)}
        <Text strong>{t("选择资料 · 已选 ")}{count}{t(" 项")}</Text><Tabs items={[{ key: 'records', label: t('报告与记录'), forceRender: true, children: recordsPanel }, { key: 'profile', label: t('健康史'), forceRender: true, children: profilePanel }, { key: 'readings', label: t('指标读数'), forceRender: true, children: readingsPanel }]} />
        <div className="two-field-row"><Form.Item label={t("开始时间")} name="starts_at" rules={[{ required: true }]}><DatePicker showTime /></Form.Item><Form.Item label={t("截止时间")} name="expires_at" rules={[{ required: true }]}><DatePicker showTime /></Form.Item></div><Form.Item name="allow_download" valuePropName="checked"><Checkbox>{t("允许导出所选文字、健康史、指标，并下载单独选中的原文件")}</Checkbox></Form.Item><Paragraph type="secondary">{t("接收人仅可读。原件、健康史及指标默认不选；OCR 全文不会随文字摘要自动开放。")}</Paragraph><Button type="primary" disabled={disabled || !count} loading={saving} onClick={reviewDraft}>{t("预览实际共享内容")}</Button>
      </Form>
      {draft && <><Alert className="share-filter-row" type="info" showIcon message={t('Review what {recipient} can see', { recipient: data.recipients.find((item) => item.id === draft.payload.recipient_id)?.full_name || t('Recipient') })} description={t('{start} to {end} · {permission} · Current scope and versions are fixed after confirmation', { start: dateText(draft.payload.starts_at), end: dateText(draft.payload.expires_at), permission: draft.payload.allow_download ? t('View and export') : t('View only') })} /><SharedContent data={draft.content} onFile={viewFile} /><Space className="share-filter-row"><Button onClick={() => setDraft(null)}>{t("返回修改")}</Button><Button type="primary" loading={saving} disabled={disabled} onClick={confirm}>{t("确认授权")}</Button></Space></>}
    </Modal>
    <Modal title={t("授权详情")} open={Boolean(grant)} onCancel={() => setGrant(null)} footer={<Button onClick={() => setGrant(null)}>{t("关闭")}</Button>}>{grant && <><Space><Text strong>{grant.recipient.full_name}</Text><Tag>{statuses[grant.status]}</Tag></Space><Paragraph>{grant.purpose}</Paragraph><Paragraph>{dateText(grant.starts_at)}{t(" 至 ")}{dateText(grant.expires_at)}</Paragraph><Paragraph type="secondary">{t("只模拟这条授权，未联系真实医生。到期、撤销或隐私设置变化会拦截后续访问。")}</Paragraph><Space wrap><Button type="primary" disabled={disabled} onClick={() => access()}>{t("预览共享内容")}</Button></Space></>}</Modal>
    <Modal width={820} title={preview?.mode === 'mock' ? t('模拟接收方可见内容') : t('本人预览共享内容')} open={Boolean(preview)} onCancel={() => setPreview(null)} footer={<Button onClick={() => setPreview(null)}>{t("关闭")}</Button>}><Alert type={preview?.blocked ? 'warning' : 'info'} message={preview?.blocked ? t('Access blocked: {reason}', { reason: preview.message }) : preview?.mode === 'mock' ? t('本地模拟结果，未连接真实接收人。') : t('本人预览，不记为接收方访问。')} />{preview?.excluded_count > 0 && <Paragraph>{preview.excluded_count}{t(" 项资料因私密、归档、删除或更正已不再开放，可重新检查并授权。")}</Paragraph>}<SharedContent data={preview || {}} onFile={viewFile} />{!preview?.blocked && <details className="quiet-details"><summary>{t("测试接收人访问")}</summary><Paragraph type="secondary">{t("以下操作会产生一条模拟接收人的访问记录，方便验证授权规则。")}</Paragraph><Space wrap><Button disabled={disabled} onClick={() => access(true)}>{t("模拟查看并留痕")}</Button><Button disabled={disabled} onClick={() => access(true, 'download')}>{t("模拟导出并留痕")}</Button></Space></details>}</Modal>
    <Modal width={960} title={recordValue(viewer, 'filename')} open={Boolean(viewer)} onCancel={() => { setViewer(null); reload() }} footer={<Button onClick={() => { setViewer(null); reload() }}>{t("关闭")}</Button>} destroyOnHidden>{viewer && <DocumentPreview url={viewer.url} filename={recordValue(viewer, 'filename')} contentType={viewer.content_type} downloadUrl={viewer.download_url} />}</Modal>
  </div>
}
