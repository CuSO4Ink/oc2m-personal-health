import React from 'react'
import { AuditOutlined, CalendarOutlined, CheckCircleOutlined, DownloadOutlined, EyeOutlined, LockOutlined, PlusOutlined, SafetyCertificateOutlined, StopOutlined, TeamOutlined, WarningOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, DatePicker, Descriptions, Empty, Form, Input, List, Modal, Popconfirm, Select, Skeleton, Space, Statistic, Steps, Tabs, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'

const { Title, Paragraph, Text } = Typography

function formatDate(value, withTime = false) {
  return dayjs(value).format(withTime ? 'D MMM YYYY, HH:mm' : 'D MMM YYYY')
}

function statusTag(status) {
  const options = {
    active: ['green', 'Active'],
    scheduled: ['blue', 'Scheduled'],
    expired: ['default', 'Expired'],
    revoked: ['red', 'Revoked'],
  }
  const [color, label] = options[status] || options.expired
  return <Tag color={color}>{label}</Tag>
}

export default function SharingPrivacyPage() {
  const [grants, setGrants] = React.useState([])
  const [recipients, setRecipients] = React.useState([])
  const [records, setRecords] = React.useState([])
  const [events, setEvents] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [shareOpen, setShareOpen] = React.useState(false)
  const [shareStep, setShareStep] = React.useState(0)
  const [draft, setDraft] = React.useState(null)
  const [saving, setSaving] = React.useState(false)
  const [selectedGrant, setSelectedGrant] = React.useState(null)
  const [actionFilter, setActionFilter] = React.useState('all')
  const [resultFilter, setResultFilter] = React.useState('all')
  const [form] = Form.useForm()

  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [grantsResponse, recipientsResponse, recordsResponse, eventsResponse] = await Promise.all([
        api.get('/sharing/grants'), api.get('/sharing/recipients'), api.get('/records'), api.get('/sharing/access-events'),
      ])
      setGrants(grantsResponse.data.grants)
      setRecipients(recipientsResponse.data.recipients)
      setRecords(recordsResponse.data.records)
      setEvents(eventsResponse.data.events)
    } catch (requestError) { setError(apiMessage(requestError)) }
    finally { setLoading(false) }
  }, [])

  React.useEffect(() => {
    let active = true
    Promise.all([api.get('/sharing/grants'), api.get('/sharing/recipients'), api.get('/records'), api.get('/sharing/access-events')])
      .then(([grantsResponse, recipientsResponse, recordsResponse, eventsResponse]) => {
        if (!active) return
        setGrants(grantsResponse.data.grants); setRecipients(recipientsResponse.data.recipients)
        setRecords(recordsResponse.data.records); setEvents(eventsResponse.data.events)
      }).catch((requestError) => { if (active) setError(apiMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  function openShare() {
    setShareStep(0); setDraft(null); form.resetFields()
    form.setFieldsValue({ starts_at: dayjs(), expires_at: dayjs().add(7, 'day'), record_ids: [], allow_download: false })
    setShareOpen(true)
  }

  async function previewShare() {
    try {
      const values = await form.validateFields()
      if (!values.expires_at.isAfter(values.starts_at) || !values.expires_at.isAfter(dayjs())) {
        form.setFields([{ name: 'expires_at', errors: ['Expiry must be after the start time and in the future'] }])
        return
      }
      setDraft(values); setShareStep(1)
    } catch { /* Ant Design displays field errors. */ }
  }

  async function createShare() {
    setSaving(true)
    try {
      await api.post('/sharing/grants', {
        recipient_id: draft.recipient_id,
        record_ids: draft.record_ids,
        starts_at: draft.starts_at.toISOString(),
        expires_at: draft.expires_at.toISOString(),
        allow_download: draft.allow_download,
        purpose: draft.purpose,
      })
      message.success('Sharing permission created.')
      setShareOpen(false); await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function revoke(grantId) {
    try {
      await api.patch(`/sharing/grants/${grantId}/revoke`)
      message.success('Future access has been revoked.')
      setSelectedGrant(null); await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  const activeCount = grants.filter((grant) => grant.status === 'active').length
  const expiringCount = grants.filter((grant) => grant.status === 'active' && dayjs(grant.expires_at).diff(dayjs(), 'day') <= 7).length
  const blockedCount = events.filter((event) => event.result === 'blocked').length
  const filteredEvents = events.filter((event) => (actionFilter === 'all' || event.action === actionFilter) && (resultFilter === 'all' || event.result === resultFilter))
  const draftRecipient = recipients.find((recipient) => recipient.id === draft?.recipient_id)
  const draftRecords = records.filter((record) => draft?.record_ids?.includes(record.id))
  const unusualEvent = events.find((event) => event.unusual)
  const unusualGrant = grants.find((grant) => grant.id === unusualEvent?.grant_id)

  const grantsPanel = loading ? <Card><Skeleton active paragraph={{ rows: 7 }} /></Card> : grants.length === 0 ? <Card><Empty description="No sharing permissions yet"><Button type="primary" onClick={openShare}>Share records</Button></Empty></Card> : <div className="grant-list">{grants.map((grant) => <Card key={grant.id} className="grant-card">
    <div className="grant-main"><div className="recipient-avatar">{grant.recipient.full_name.split(' ').filter((part) => !part.endsWith('.')).map((part) => part[0]).slice(0, 2).join('')}</div><div><Space wrap><Title level={4}>{grant.recipient.full_name}</Title>{statusTag(grant.status)}<Tag icon={<SafetyCertificateOutlined />} color="blue">Verified</Tag></Space><Text>{grant.recipient.role} · {grant.recipient.organisation}</Text><div className="grant-meta"><span><LockOutlined /> {grant.records.length} selected {grant.records.length === 1 ? 'record' : 'records'}</span><span><CalendarOutlined /> Until {formatDate(grant.expires_at, true)}</span><span>{grant.allow_download ? <><DownloadOutlined /> View and download</> : <><EyeOutlined /> View only</>}</span></div></div></div>
    <Space><Button onClick={() => setSelectedGrant(grant)}>View details</Button>{['active', 'scheduled'].includes(grant.status) && <Popconfirm title="Revoke this sharing permission?" description="The recipient will be blocked from future access. Previously downloaded copies cannot be recalled." okText="Revoke access" okButtonProps={{ danger: true }} onConfirm={() => revoke(grant.id)}><Button danger icon={<StopOutlined />}>Revoke</Button></Popconfirm>}</Space>
  </Card>)}</div>

  const activityPanel = <Card className="activity-card"><div className="activity-filters"><div><Title level={3}>Access activity</Title><Paragraph>See who accessed each record, what they did, where the request came from and whether it succeeded.</Paragraph></div><Space wrap><Select value={actionFilter} onChange={setActionFilter} options={[{ value: 'all', label: 'All actions' }, { value: 'view', label: 'Views' }, { value: 'download', label: 'Downloads' }]} /><Select value={resultFilter} onChange={setResultFilter} options={[{ value: 'all', label: 'All results' }, { value: 'allowed', label: 'Allowed' }, { value: 'blocked', label: 'Blocked' }]} /></Space></div>{unusualEvent && <Alert className="activity-alert" type="warning" showIcon message="An access attempt needs your review" description={`${unusualEvent.recipient.full_name} attempted to ${unusualEvent.action} ${unusualEvent.record.title}. The request was ${unusualEvent.result}.`} action={unusualGrant && <Button onClick={() => setSelectedGrant(unusualGrant)}>Review permission</Button>} />}{filteredEvents.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No access activity matches these filters" /> : <List dataSource={filteredEvents} renderItem={(event) => <List.Item><List.Item.Meta avatar={<div className={`event-icon ${event.result}`} >{event.action === 'download' ? <DownloadOutlined /> : <EyeOutlined />}</div>} title={<Space wrap><Text strong>{event.recipient.full_name}</Text><Tag>{event.action === 'download' ? 'Download' : 'View'}</Tag><Tag color={event.result === 'allowed' ? 'green' : 'red'}>{event.result}</Tag>{event.unusual && <Tag color="orange" icon={<WarningOutlined />}>Review activity</Tag>}</Space>} description={<div className="event-details"><span>{event.record.title}</span><span>{formatDate(event.occurred_at, true)}</span><span>{event.location}</span></div>} /></List.Item>} />}</Card>

  return <div className="page-stack sharing-page">
    <div className="page-heading"><div><Title level={1}>Sharing & Privacy</Title><Paragraph>Choose exactly who can access selected health records, for how long, and review every access attempt.</Paragraph></div><Button type="primary" icon={<PlusOutlined />} onClick={openShare}>Share Records</Button></div>
    <Alert type="info" showIcon message="You remain in control" description="Each permission uses a fixed list of records. Records added later are not shared automatically. Revoking access blocks future requests but cannot recall copies that were previously downloaded with your permission." />
    {error && <Alert type="error" showIcon message="Sharing information could not be loaded" description={error} action={<Button onClick={load}>Try again</Button>} />}
    <div className="privacy-stats"><Card><Statistic title="Active permissions" value={activeCount} prefix={<TeamOutlined />} /></Card><Card><Statistic title="Expiring within 7 days" value={expiringCount} prefix={<CalendarOutlined />} /></Card><Card><Statistic title="Blocked access attempts" value={blockedCount} prefix={<AuditOutlined />} /></Card></div>
    <Tabs defaultActiveKey="permissions" items={[{ key: 'permissions', label: `Sharing permissions (${grants.length})`, children: grantsPanel }, { key: 'activity', label: `Access activity (${events.length})`, children: activityPanel }]} />

    <Modal width={780} title="Share health records" open={shareOpen} onCancel={() => setShareOpen(false)} footer={null} destroyOnHidden>
      <Steps size="small" current={shareStep} items={[{ title: 'Set permission' }, { title: 'Review & confirm' }]} />
      {shareStep === 0 ? <Form className="share-form" form={form} layout="vertical">
        <Form.Item label="Verified recipient" name="recipient_id" rules={[{ required: true, message: 'Select a healthcare recipient' }]}><Select placeholder="Select a doctor or health manager" optionRender={(option) => <div><b>{option.data.label}</b><div className="select-detail">{option.data.description}</div></div>} options={recipients.map((recipient) => ({ value: recipient.id, label: recipient.full_name, description: `${recipient.role} · ${recipient.organisation}` }))} /></Form.Item>
        <Form.Item label="Purpose" name="purpose" rules={[{ required: true, message: 'Explain why you are sharing these records' }]}><Input maxLength={200} placeholder="e.g. Follow-up consultation" /></Form.Item>
        <Form.Item label="Records to share" name="record_ids" rules={[{ required: true, type: 'array', min: 1, message: 'Select at least one record' }]}><Checkbox.Group className="record-checkbox-group">{records.map((record) => <Checkbox key={record.id} value={record.id}><span><b>{record.title}</b><small>{record.record_type} · {formatDate(record.record_date)}</small></span></Checkbox>)}</Checkbox.Group></Form.Item>
        <div className="two-field-row"><Form.Item label="Access starts" name="starts_at" rules={[{ required: true }]}><DatePicker showTime className="full-width" /></Form.Item><Form.Item label="Access expires" name="expires_at" rules={[{ required: true }]}><DatePicker showTime className="full-width" /></Form.Item></div>
        <Form.Item name="allow_download" valuePropName="checked"><Checkbox>Allow the recipient to download copies</Checkbox></Form.Item>
        <div className="form-actions"><Button onClick={() => setShareOpen(false)}>Cancel</Button><Button type="primary" onClick={previewShare}>Review permission</Button></div>
      </Form> : <div className="share-preview">
        <Alert type="warning" showIcon message="Confirm what this recipient will be able to access" />
        <Descriptions column={1} bordered size="small" items={[
          { key: 'recipient', label: 'Recipient', children: <span>{draftRecipient.full_name}<br /><Text type="secondary">{draftRecipient.role} · {draftRecipient.organisation}</Text></span> },
          { key: 'purpose', label: 'Purpose', children: draft.purpose },
          { key: 'records', label: 'Fixed record list', children: <List size="small" dataSource={draftRecords} renderItem={(record) => <List.Item>{record.title} <Tag>{record.record_type}</Tag></List.Item>} /> },
          { key: 'actions', label: 'Allowed actions', children: draft.allow_download ? 'View and download' : 'View only' },
          { key: 'period', label: 'Permission period', children: `${formatDate(draft.starts_at, true)} until ${formatDate(draft.expires_at, true)}` },
        ]} />
        <div className="fixed-scope-note"><CheckCircleOutlined /><Text>New records created after confirmation will remain private unless you share them separately.</Text></div>
        <div className="form-actions"><Button onClick={() => setShareStep(0)}>Back</Button><Button type="primary" loading={saving} onClick={createShare}>Confirm Sharing</Button></div>
      </div>}
    </Modal>

    <Modal width={700} title="Sharing permission details" open={Boolean(selectedGrant)} onCancel={() => setSelectedGrant(null)} footer={selectedGrant && ['active', 'scheduled'].includes(selectedGrant.status) ? <Popconfirm title="Revoke this sharing permission?" description="This blocks all future access under this permission." okText="Revoke access" okButtonProps={{ danger: true }} onConfirm={() => revoke(selectedGrant.id)}><Button danger>Revoke access</Button></Popconfirm> : <Button onClick={() => setSelectedGrant(null)}>Close</Button>}>
      {selectedGrant && <div className="grant-detail"><Space>{statusTag(selectedGrant.status)}<Tag icon={<SafetyCertificateOutlined />} color="blue">Verified recipient</Tag></Space><Title level={3}>{selectedGrant.recipient.full_name}</Title><Paragraph>{selectedGrant.recipient.role} · {selectedGrant.recipient.organisation}</Paragraph><Descriptions column={1} bordered size="small" items={[
        { key: 'purpose', label: 'Purpose', children: selectedGrant.purpose },
        { key: 'actions', label: 'Allowed actions', children: selectedGrant.allowed_actions.join(' and ') },
        { key: 'period', label: 'Permission period', children: `${formatDate(selectedGrant.starts_at, true)} until ${formatDate(selectedGrant.expires_at, true)}` },
        { key: 'records', label: 'Shared records', children: <List size="small" dataSource={selectedGrant.records} renderItem={(record) => <List.Item>{record.title} <Tag>{record.record_type}</Tag></List.Item>} /> },
      ]} /></div>}
    </Modal>
  </div>
}
