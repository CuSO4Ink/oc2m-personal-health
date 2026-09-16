import React from 'react'
import {
  ArrowLeftOutlined,
  EditOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { Alert, Button, Card, DatePicker, Descriptions, Empty, Form, Input, List, Select, Skeleton, Space, Tag, Timeline, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { useNavigate, useParams } from 'react-router-dom'
import api, { apiMessage } from './api'
import RecordAttachments from './RecordAttachments'

const { Title, Paragraph, Text } = Typography
const { RangePicker } = DatePicker
const recordTypes = ['Lab Report', 'Visit Summary', 'Medication', 'Allergy', 'Imaging', 'Other']

function displayDate(value, withTime = false) {
  if (!value) return 'Not available'
  return dayjs(value).format(withTime ? 'D MMM YYYY, HH:mm' : 'D MMM YYYY')
}

function SourceTag({ record }) {
  return record.source_type === 'hospital'
    ? <Tag color="blue" icon={<SafetyCertificateOutlined />}>Provider synced</Tag>
    : <Tag color="green">Self-reported</Tag>
}

function RecordTypeTag({ type }) {
  const colors = { 'Lab Report': 'cyan', 'Visit Summary': 'geekblue', Medication: 'purple', Allergy: 'volcano', Imaging: 'gold' }
  return <Tag color={colors[type]}>{type}</Tag>
}

export function RecordsPage() {
  const navigate = useNavigate()
  const [records, setRecords] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [filters, setFilters] = React.useState({ q: '', type: undefined, source: undefined, dates: null })

  async function loadRecords(nextFilters = filters) {
    setLoading(true); setError('')
    try {
      const params = {
        q: nextFilters.q || undefined,
        type: nextFilters.type,
        source: nextFilters.source,
        from: nextFilters.dates?.[0]?.format('YYYY-MM-DD'),
        to: nextFilters.dates?.[1]?.format('YYYY-MM-DD'),
      }
      const response = await api.get('/records', { params })
      setRecords(response.data.records)
    } catch (requestError) {
      setError(apiMessage(requestError))
    } finally { setLoading(false) }
  }

  React.useEffect(() => {
    let active = true
    api.get('/records').then((response) => {
      if (active) setRecords(response.data.records)
    }).catch((requestError) => {
      if (active) setError(apiMessage(requestError))
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [])

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function resetFilters() {
    const empty = { q: '', type: undefined, source: undefined, dates: null }
    setFilters(empty); loadRecords(empty)
  }

  return <div className="page-stack records-page">
    <div className="page-heading">
      <div><Title level={1}>Health Records</Title><Paragraph>Keep provider records and your own health notes in one searchable timeline.</Paragraph></div>
      <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/records/new')}>Add Record</Button>
    </div>

    <Card className="filter-card">
      <div className="filter-grid">
        <Input allowClear value={filters.q} prefix={<SearchOutlined />} placeholder="Search title, condition, source or details" onChange={(event) => updateFilter('q', event.target.value)} onPressEnter={() => loadRecords()} />
        <Select allowClear value={filters.type} placeholder="All record types" options={recordTypes.map((value) => ({ value }))} onChange={(value) => updateFilter('type', value)} />
        <Select allowClear value={filters.source} placeholder="All sources" options={[{ value: 'hospital', label: 'Provider synced' }, { value: 'self', label: 'Self-reported' }]} onChange={(value) => updateFilter('source', value)} />
        <RangePicker value={filters.dates} onChange={(value) => updateFilter('dates', value)} />
        <Space><Button type="primary" onClick={() => loadRecords()}>Apply filters</Button><Button onClick={resetFilters}>Reset</Button></Space>
      </div>
    </Card>

    {error && <Alert type="error" showIcon message="Records could not be loaded" description={error} action={<Button onClick={() => loadRecords()}>Try again</Button>} />}
    {loading ? <Card><Skeleton active paragraph={{ rows: 6 }} /></Card> : !error && <>
      <div className="results-heading"><Text strong>{records.length} {records.length === 1 ? 'record' : 'records'}</Text><Text type="secondary">Newest record date first</Text></div>
      {records.length === 0 ? <Card><Empty description={<><b>No matching records</b><br /><Text type="secondary">Change your filters or add a self-reported record.</Text></>}><Button type="primary" onClick={() => navigate('/records/new')}>Add Record</Button></Empty></Card> :
        <List className="records-list" dataSource={records} renderItem={(record) => <List.Item onClick={() => navigate(`/records/${record.id}`)} actions={[<Button key="view" type="link" onClick={(event) => { event.stopPropagation(); navigate(`/records/${record.id}`) }}>View details</Button>]}>
          <List.Item.Meta
            avatar={<div className="record-icon"><FileTextOutlined /></div>}
            title={<Space wrap><span>{record.title}</span><RecordTypeTag type={record.record_type} /><SourceTag record={record} /></Space>}
            description={<div className="record-list-details"><span>{record.condition || 'No condition specified'}</span><span>Record date: {displayDate(record.record_date)}</span><span>Source: {record.source_name}</span><span>Version {record.version} · Updated {displayDate(record.updated_at, true)}</span><span>{record.attachments.length} attachments</span></div>}
          />
        </List.Item>}/>
      }
    </>}
  </div>
}

export function RecordFormPage({ editing = false }) {
  const navigate = useNavigate()
  const { id } = useParams()
  const [form] = Form.useForm()
  const [record, setRecord] = React.useState(null)
  const [loading, setLoading] = React.useState(editing)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState('')

  React.useEffect(() => {
    if (!editing) return
    api.get(`/records/${id}`).then(({ data }) => {
      setRecord(data.record)
      form.setFieldsValue({ ...data.record, record_date: dayjs(data.record.record_date) })
    }).catch((requestError) => setError(apiMessage(requestError))).finally(() => setLoading(false))
  }, [editing, form, id])

  async function submit(values) {
    setSaving(true); setError('')
    const payload = { ...values, record_date: values.record_date.format('YYYY-MM-DD') }
    try {
      const response = editing
        ? await api.patch(`/records/${id}`, { ...payload, version: record.version })
        : await api.post('/records', payload)
      message.success(editing ? 'Record updated and a new version was saved.' : 'Health record added.')
      navigate(`/records/${response.data.record.id}`)
    } catch (requestError) {
      setError(apiMessage(requestError))
      if (requestError.response?.status === 409) setRecord(requestError.response.data.record)
    } finally { setSaving(false) }
  }

  if (loading) return <div className="page-stack"><Card><Skeleton active /></Card></div>
  if (editing && !record) return <NavigateBack title="Record unavailable" description={error} onBack={() => navigate('/records')} />
  if (editing && record && !record.is_editable) return <NavigateBack title="This provider record is read-only" description="Provider-synced content is preserved exactly as received. A correction-request workflow will be added with hospital integration." onBack={() => navigate(`/records/${id}`)} />

  return <div className="page-stack form-page">
    <Button className="inline-back" type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate(editing ? `/records/${id}` : '/records')}>Back to {editing ? 'record' : 'health records'}</Button>
    <div><Title level={1}>{editing ? 'Edit Health Record' : 'Add Health Record'}</Title><Paragraph>{editing ? 'Saving creates a new version so earlier information remains traceable.' : 'Add information you manage yourself. Provider imports will appear separately when connected.'}</Paragraph></div>
    {error && <Alert type="error" showIcon message={error} />}
    <Card>
      <Paragraph type="secondary">After saving this record, you can upload supporting PDF reports or images on its detail page.</Paragraph>
      <Form form={form} layout="vertical" onFinish={submit} initialValues={{ record_type: 'Other', record_date: dayjs(), source_name: 'Self-reported' }}>
        <div className="form-grid">
          <Form.Item label="Record title" name="title" rules={[{ required: true, min: 2, message: 'Enter a record title' }]}><Input placeholder="e.g. Physiotherapy follow-up" /></Form.Item>
          <Form.Item label="Record type" name="record_type" rules={[{ required: true }]}><Select options={recordTypes.map((value) => ({ value }))} /></Form.Item>
          <Form.Item label="Record date" name="record_date" rules={[{ required: true, message: 'Select the record date' }]}><DatePicker className="full-width" /></Form.Item>
          <Form.Item label="Condition or health topic" name="condition"><Input placeholder="Optional, e.g. lower back pain" /></Form.Item>
          <Form.Item className="span-two" label="Source or recorder" name="source_name" extra="For self-entered records, note who supplied the information."><Input /></Form.Item>
          <Form.Item className="span-two" label="Record details" name="content" rules={[{ required: true, message: 'Enter the record details' }]}><Input.TextArea rows={7} placeholder="Include the finding, advice, dosage, reaction or other useful context." /></Form.Item>
          {editing && <Form.Item className="span-two" label="Reason for this update" name="change_note" rules={[{ required: true, message: 'Briefly explain what changed' }]}><Input placeholder="e.g. Updated dosage after consultation" maxLength={240} showCount /></Form.Item>}
        </div>
        <div className="form-actions"><Button onClick={() => navigate(editing ? `/records/${id}` : '/records')}>Cancel</Button><Button type="primary" htmlType="submit" loading={saving}>{editing ? 'Save New Version' : 'Add Record'}</Button></div>
      </Form>
    </Card>
  </div>
}

function NavigateBack({ title, description, onBack }) {
  return <div className="page-stack"><Alert type="info" showIcon message={title} description={description} action={<Button onClick={onBack}>Back to record</Button>} /></div>
}

export function RecordDetailPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const [record, setRecord] = React.useState(null)
  const [error, setError] = React.useState('')

  React.useEffect(() => { api.get(`/records/${id}`).then(({ data }) => setRecord(data.record)).catch((requestError) => setError(apiMessage(requestError))) }, [id])
  if (error) return <NavigateBack title="Record unavailable" description={error} onBack={() => navigate('/records')} />
  if (!record) return <div className="page-stack"><Card><Skeleton active /></Card></div>

  return <div className="page-stack record-detail-page">
    <Button className="inline-back" type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/records')}>Back to health records</Button>
    <div className="page-heading">
      <div><Space wrap><RecordTypeTag type={record.record_type} /><SourceTag record={record} /></Space><Title level={1}>{record.title}</Title><Paragraph>{record.condition || 'No condition specified'}</Paragraph></div>
      <Space wrap>{record.is_editable && <Button icon={<EditOutlined />} onClick={() => navigate(`/records/${id}/edit`)}>Edit Record</Button>}<Button icon={<HistoryOutlined />} onClick={() => navigate(`/records/${id}/history`)}>Version History</Button></Space>
    </div>
    {!record.is_editable && <Alert type="info" showIcon message="Original provider record preserved" description="This record is read-only because it was synced from a healthcare provider. Requesting a correction will be available after provider integration." action={<Button disabled>Request correction</Button>} />}
    <Card title="Record details"><Paragraph className="record-content">{record.content}</Paragraph></Card>
    <Card title="Record provenance">
      <Descriptions column={{ xs: 1, sm: 2 }} items={[
        { key: 'date', label: 'Record date', children: displayDate(record.record_date) },
        { key: 'type', label: 'Record type', children: record.record_type },
        { key: 'source', label: 'Source / recorder', children: record.source_name },
        { key: 'sync', label: 'Synced at', children: record.synced_at ? displayDate(record.synced_at, true) : 'Not provider synced' },
        { key: 'updated', label: 'Last updated', children: displayDate(record.updated_at, true) },
        { key: 'version', label: 'Current version', children: `Version ${record.version}` },
      ]} />
    </Card>
    <RecordAttachments record={record} onChange={setRecord} />
    <Card className="future-card"><div><Text strong>OCR and visit folders</Text><Paragraph>Automatic text extraction and grouping related records into one visit will be added in the next phase.</Paragraph></div><Tag color="gold">Planned</Tag></Card>
  </div>
}

export function RecordHistoryPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const [versions, setVersions] = React.useState(null)
  const [error, setError] = React.useState('')

  React.useEffect(() => { api.get(`/records/${id}/history`).then(({ data }) => setVersions(data.versions)).catch((requestError) => setError(apiMessage(requestError))) }, [id])
  return <div className="page-stack history-page">
    <Button className="inline-back" type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate(`/records/${id}`)}>Back to record</Button>
    <div><Title level={1}>Version History</Title><Paragraph>Review when this record changed, who changed it, and the information saved in each version.</Paragraph></div>
    {error && <Alert type="error" showIcon message={error} />}
    {!versions ? <Card><Skeleton active /></Card> : <Card><Timeline items={versions.map((item, index) => ({
      color: index === 0 ? 'green' : 'gray',
      children: <div className="version-item"><Space><Text strong>Version {item.version}</Text>{index === 0 && <Tag color="green">Current</Tag>}</Space><Text>{item.change_note}</Text><Text type="secondary">{item.changed_by} · {displayDate(item.created_at, true)}</Text><details><summary>View saved information</summary><Descriptions size="small" column={1} items={[
        { key: 'title', label: 'Title', children: item.snapshot.title },
        { key: 'date', label: 'Record date', children: displayDate(item.snapshot.record_date) },
        { key: 'source', label: 'Source', children: item.snapshot.source_name },
        { key: 'content', label: 'Details', children: item.snapshot.content },
      ]} /></details></div>,
    }))} /></Card>}
  </div>
}
