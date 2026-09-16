import React from 'react'
import { AlertOutlined, CheckCircleOutlined, ClockCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { Alert, Button, Card, DatePicker, Empty, Form, Input, InputNumber, List, Modal, Segmented, Select, Skeleton, Space, Statistic, Table, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api, { apiMessage } from './api'

const { Title, Paragraph, Text } = Typography

const metrics = [
  { key: 'blood_pressure', label: 'Blood Pressure', shortUnit: 'mmHg' },
  { key: 'blood_glucose', label: 'Blood Glucose', shortUnit: 'mmol/L' },
  { key: 'heart_rate', label: 'Heart Rate', shortUnit: 'bpm' },
]

function readingValue(reading) {
  if (!reading) return '—'
  return reading.secondary_value == null ? `${reading.value}` : `${reading.value}/${reading.secondary_value}`
}

function statusTag(status) {
  if (status === 'not_assessed') return <Tag>Context needs interpretation</Tag>
  if (status === 'low') return <Tag color="red">Low reference flag</Tag>
  if (status === 'high') return <Tag color="red">High</Tag>
  if (status === 'watch') return <Tag color="gold">Review</Tag>
  return <Tag color="green">Within configured reference</Tag>
}

function friendlyDate(value, withTime = false) {
  return dayjs(value).format(withTime ? 'D MMM YYYY, HH:mm' : 'D MMM')
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const reading = payload[0].payload
  return <div className="chart-tooltip"><Text strong>{friendlyDate(reading.measured_at, true)}</Text><div>{readingValue(reading)} {reading.unit}</div><Text type="secondary">{reading.source_name}</Text>{reading.context && <Text type="secondary">Context: {reading.context.replace('_', ' ')}</Text>}</div>
}

export default function HealthInsightsPage() {
  const [selectedMetric, setSelectedMetric] = React.useState('blood_pressure')
  const [context, setContext] = React.useState('')
  const [alertStatus, setAlertStatus] = React.useState('pending')
  const [days, setDays] = React.useState(30)
  const [data, setData] = React.useState(null)
  const [alerts, setAlerts] = React.useState([])
  const [error, setError] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [modalOpen, setModalOpen] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [form] = Form.useForm()
  const formMetric = Form.useWatch('metric_type', form)

  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [metricsResponse, alertsResponse] = await Promise.all([
        api.get('/insights/metrics', { params: { metric: selectedMetric, days, context } }),
        api.get('/insights/alerts', { params: { status: alertStatus } }),
      ])
      setData(metricsResponse.data)
      setAlerts(alertsResponse.data.alerts)
    } catch (requestError) {
      setError(apiMessage(requestError))
    } finally { setLoading(false) }
  }, [days, selectedMetric, context, alertStatus])

  React.useEffect(() => {
    let active = true
    Promise.all([
      api.get('/insights/metrics', { params: { metric: selectedMetric, days, context } }),
      api.get('/insights/alerts', { params: { status: alertStatus } }),
    ]).then(([metricsResponse, alertsResponse]) => {
      if (!active) return
      setData(metricsResponse.data)
      setAlerts(alertsResponse.data.alerts)
    }).catch((requestError) => {
      if (active) setError(apiMessage(requestError))
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [days, selectedMetric, context, alertStatus])

  function changeMetric(metric) {
    if (metric === selectedMetric && !context) return
    setLoading(true); setError(''); setSelectedMetric(metric); setContext('')
  }

  function changeDays(value) {
    if (value === days) return
    setLoading(true); setError(''); setDays(value)
  }

  function openAddReading() {
    form.resetFields()
    form.setFieldsValue({ metric_type: selectedMetric, measured_at: dayjs(), source_name: 'Manual entry', context: selectedMetric === 'blood_glucose' ? 'fasting' : selectedMetric === 'heart_rate' ? 'resting' : '' })
    setModalOpen(true)
  }

  async function saveReading(values) {
    setSaving(true)
    try {
      const response = await api.post('/insights/metrics', { ...values, measured_at: values.measured_at.toISOString() })
      if (response.data.alert) message.warning('Reading saved. It also created a health alert for review.')
      else message.success('Health reading saved.')
      setModalOpen(false)
      if (values.metric_type === selectedMetric && !context) await load()
      else if (values.metric_type === selectedMetric) { setLoading(true); setContext('') }
      else changeMetric(values.metric_type)
    } catch (requestError) {
      message.error(apiMessage(requestError))
    } finally { setSaving(false) }
  }

  async function acknowledgeAlert(alertId) {
    try {
      await api.patch(`/insights/alerts/${alertId}/acknowledge`)
      await load()
      message.success('Alert marked as reviewed.')
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  const selected = metrics.find((item) => item.key === selectedMetric)
  const attentionCount = data?.summary.attention_count || 0
  const isBloodPressure = selectedMetric === 'blood_pressure'
  const threshold = selectedMetric === 'blood_pressure' ? 120 : selectedMetric === 'blood_glucose' ? 5.6 : 100
  const contextOptions = selectedMetric === 'blood_glucose' ? [{ value: 'fasting', label: 'Fasting' }, { value: 'after_meal', label: 'After a meal' }, { value: 'random', label: 'Random' }] : [{ value: 'resting', label: 'Resting' }, { value: 'exercise', label: 'Exercise' }, { value: 'unknown', label: 'Unknown context' }]
  const showReference = selectedMetric === 'blood_pressure' || (selectedMetric === 'blood_glucose' && context === 'fasting') || (selectedMetric === 'heart_rate' && context === 'resting')

  return <div className="page-stack insights-page">
    <div className="page-heading">
      <div><Title level={1}>Health Insights</Title><Paragraph>Follow changes in your readings and see the data behind each health notice.</Paragraph></div>
      <Button type="primary" icon={<PlusOutlined />} onClick={openAddReading}>Add Reading</Button>
    </div>

    <Alert type="info" showIcon message="Health information, not a diagnosis" description="Reference thresholds help organise your readings. They do not account for your complete medical history or replace advice from a qualified healthcare professional." />

    <div className="metric-selector" role="tablist">{metrics.map((metric) => <button className={selectedMetric === metric.key ? 'metric-option active' : 'metric-option'} key={metric.key} onClick={() => changeMetric(metric.key)}><span>{metric.label}</span><small>{metric.shortUnit}</small></button>)}</div>

    <div className="insights-toolbar"><div><Text strong>{selected.label} trend</Text><Text type="secondary"> · All times shown in your local timezone</Text></div><Segmented value={days} options={[{ label: '7 days', value: 7 }, { label: '30 days', value: 30 }, { label: '90 days', value: 90 }, { label: '1 year', value: 365 }]} onChange={changeDays} /></div>

    {selectedMetric !== 'blood_pressure' && <Select className="insight-context-filter" value={context} options={[{ value: '', label: 'All measurement contexts' }, ...contextOptions]} onChange={(value) => { setLoading(true); setError(''); setContext(value) }} />}
    {error && <Alert type="error" showIcon message="Health insights could not be loaded" description={error} action={<Button onClick={load}>Try again</Button>} />}
    {loading ? <Card><Skeleton active paragraph={{ rows: 8 }} /></Card> : !error && data && <>
      <div className="insight-stats">
        <Card><Statistic title="Latest reading" value={readingValue(data.latest)} suffix={data.latest?.unit || selected.shortUnit} /><div className="stat-foot">{data.latest ? <Space>{statusTag(data.latest.status)}<Text type="secondary">{friendlyDate(data.latest.measured_at, true)}</Text></Space> : <Text type="secondary">No readings in this period</Text>}</div></Card>
        <Card><Statistic title={`Average ${isBloodPressure ? 'systolic' : ''}`} value={data.summary.average ?? '—'} suffix={selected.shortUnit} /><div className="stat-foot"><Text type="secondary">From {data.summary.count} readings over {data.summary.distinct_days} UTC dates{isBloodPressure ? ` · Diastolic average ${data.summary.secondary_average ?? '—'} mmHg` : ''}</Text></div></Card>
        <Card><Statistic title={isBloodPressure ? 'Systolic range' : 'Range'} value={data.summary.count ? `${data.summary.minimum}–${data.summary.maximum}` : '—'} suffix={selected.shortUnit} /><div className="stat-foot"><Text type="secondary">Selected time period</Text></div></Card>
      </div>

      <Card className="trend-card">
        {data.readings.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No readings in this time range"><Button onClick={openAddReading}>Add your first reading</Button></Empty> : <div className="chart-wrap"><ResponsiveContainer width="100%" height={340}><LineChart data={data.readings} margin={{ top: 18, right: 22, left: 0, bottom: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#edf0f3" /><XAxis dataKey="measured_at" tickFormatter={(value) => friendlyDate(value)} minTickGap={30} /><YAxis domain={['auto', 'auto']} tickFormatter={(value) => selectedMetric === 'blood_glucose' ? Number(value).toFixed(1) : Math.round(value)} unit={` ${selected.shortUnit}`} width={78} /><Tooltip content={<ChartTooltip />} /><Legend />{showReference && <ReferenceLine y={threshold} stroke="#d97706" strokeDasharray="5 5" label={{ value: 'Review threshold', fill: '#a16207', fontSize: 12 }} />}{selectedMetric === 'heart_rate' && context === 'resting' && <ReferenceLine y={60} stroke="#d97706" strokeDasharray="5 5" />}<Line name={isBloodPressure ? 'Systolic' : selected.label} type="monotone" dataKey="value" stroke="#397f78" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />{isBloodPressure && <Line name="Diastolic" type="monotone" dataKey="secondary_value" stroke="#5878a8" strokeWidth={3} dot={{ r: 4 }} />}</LineChart></ResponsiveContainer></div>}
        <div className={`sufficiency ${data.data_sufficiency.status}`}><ClockCircleOutlined /><div><Text strong>{data.data_sufficiency.status === 'sufficient' ? 'Data available for a descriptive summary' : data.data_sufficiency.status === 'stale' ? 'Readings need updating' : 'Limited data'}</Text><Text>{data.data_sufficiency.message}</Text><Text type="secondary">{data.summary.unassessed_count} readings require context-specific interpretation.</Text></div></div>
      </Card>

      <Card title={`How these flags are calculated · Rule ${data.reference.version}`}><Paragraph>{data.reference.text}</Paragraph><Paragraph type="secondary">{data.reference.limitations} Historical alerts retain the rule used when they were created.</Paragraph><Space wrap>{data.reference.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}</a>)}</Space></Card>
      {selectedMetric !== 'blood_pressure' && <Alert type="info" showIcon message="Compare similar measurement contexts" description={`Readings in this view: ${Object.entries(data.summary.context_counts).map(([key, count]) => `${key.replace('_', ' ')}: ${count}`).join(' · ') || 'None'}. Use the context filter before comparing averages. Reference lines are shown only for a selected fasting or resting context.`} />}
      <Card title="Reading history"><Table rowKey="id" scroll={{ x: 850 }} pagination={{ pageSize: 8 }} dataSource={[...data.readings].reverse()} columns={[
        {title: 'Measured at', dataIndex: 'measured_at', render: (value) => friendlyDate(value, true)},
        {title: 'Reading', render: (_, reading) => `${readingValue(reading)} ${reading.unit}`},
        {title: 'Context', dataIndex: 'context', render: (value) => value?.replace('_', ' ') || 'Not recorded'},
        {title: 'Reference flag', dataIndex: 'status', render: statusTag},
        {title: 'Source', dataIndex: 'source_name'}, {title: 'Notes', dataIndex: 'notes', render: (value) => value || '—'},
      ]} /></Card>
      <div className="insight-lower-grid">
        <Card title="Trend summary" className="summary-card">
          {data.data_sufficiency.status !== 'sufficient' ? <Alert type="warning" showIcon message="A summary cannot be generated yet" description={data.data_sufficiency.message} /> : <>
            <div className="summary-row"><CheckCircleOutlined /><div><Text strong>Latest status</Text><Paragraph>{data.latest.status === 'not_assessed' ? 'The latest reading needs context-specific interpretation; no normal-range classification is assigned.' : data.latest.status === 'in_range' ? `The latest ${selected.label.toLowerCase()} reading is within the configured reference threshold.` : `The latest reading is marked for ${data.latest.status === 'high' ? 'attention' : 'review'}.`}</Paragraph></div></div>
            <div className="summary-row"><AlertOutlined /><div><Text strong>Points to review</Text><Paragraph>{attentionCount === 0 ? 'No readings in this period crossed a configured threshold.' : `${attentionCount} ${attentionCount === 1 ? 'reading' : 'readings'} in this period crossed a configured threshold. Hover over a point on the chart to review its time and source.`}</Paragraph></div></div>
            <Text type="secondary">Rule-based summary generated {friendlyDate(data.generated_at, true)} from the selected {days}-day period.</Text>
          </>}
          <div className="planned-analysis"><Tag color="gold">Planned</Tag><Text>Personalised risk reports with clinically approved rules and explainable AI.</Text></div>
        </Card>

        <Card title={`Health alerts (${alerts.length})`} extra={<Select value={alertStatus} options={[{value: 'pending', label: 'To review'}, {value: 'reviewed', label: 'Reviewed'}, {value: 'all', label: 'All alerts'}]} onChange={(value) => {setLoading(true); setError(''); setAlertStatus(value)}} />} className="alerts-card">
          {alerts.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No health alerts in this view" /> : <List pagination={{ pageSize: 5 }} dataSource={alerts} renderItem={(alert) => <List.Item actions={alert.acknowledged_at ? [<Tag key="reviewed" color="green">Reviewed {friendlyDate(alert.acknowledged_at, true)}</Tag>] : [<Button key="review" type="link" onClick={() => acknowledgeAlert(alert.id)}>Mark reviewed</Button>]}><List.Item.Meta avatar={<div className={`alert-icon ${alert.severity}`}><AlertOutlined /></div>} title={alert.title} description={<><Text>{alert.message}</Text><div><Text type="secondary">Original rule {alert.rule_version} · {alert.rule_name}</Text></div><div><Text type="secondary">Reading: {readingValue(alert.measurement)} {alert.measurement.unit} · {friendlyDate(alert.measurement.measured_at, true)}</Text></div></>} /></List.Item>} />}
        </Card>
      </div>
    </>}

    <Modal title="Add health reading" open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={saveReading}>
        <Form.Item label="Health metric" name="metric_type" rules={[{ required: true }]}><Select options={metrics.map(({ key, label }) => ({ value: key, label }))} onChange={(value) => form.setFieldsValue({ value: null, secondary_value: null, context: value === 'blood_glucose' ? 'fasting' : value === 'heart_rate' ? 'resting' : '' })} /></Form.Item>
        {formMetric === 'blood_pressure' ? <div className="two-field-row"><Form.Item label="Systolic" name="value" rules={[{ required: true, message: 'Enter systolic value' }]}><InputNumber min={50} max={260} addonAfter="mmHg" /></Form.Item><Form.Item label="Diastolic" name="secondary_value" rules={[{ required: true, message: 'Enter diastolic value' }]}><InputNumber min={30} max={160} addonAfter="mmHg" /></Form.Item></div> : <Form.Item label="Reading" name="value" rules={[{ required: true, message: 'Enter a reading' }]}><InputNumber className="full-width" min={formMetric === 'heart_rate' ? 25 : 1} max={formMetric === 'heart_rate' ? 240 : 35} step={formMetric === 'blood_glucose' ? 0.1 : 1} addonAfter={formMetric === 'heart_rate' ? 'bpm' : 'mmol/L'} /></Form.Item>}
        {formMetric === 'heart_rate' && <Form.Item label="Measurement context" name="context" rules={[{required: true}]}><Select options={[{value: 'resting', label: 'Resting'}, {value: 'exercise', label: 'During or after exercise'}, {value: 'unknown', label: 'Unknown'}]} /></Form.Item>}
        {formMetric === 'blood_glucose' && <Form.Item label="Measurement context" name="context" rules={[{ required: true }]}><Select options={[{ value: 'fasting', label: 'Fasting' }, { value: 'after_meal', label: 'After a meal' }, { value: 'random', label: 'Random' }]} /></Form.Item>}
        <Form.Item label="Measured at" name="measured_at" rules={[{ required: true }]}><DatePicker showTime className="full-width" disabledDate={(date) => date && date > dayjs().endOf('day')} /></Form.Item>
        <Form.Item label="Source" name="source_name" rules={[{ required: true, message: 'Enter the reading source' }]}><Input placeholder="e.g. Manual entry or home monitor" /></Form.Item>
        <Form.Item label="Notes" name="notes"><Input.TextArea rows={3} maxLength={300} showCount placeholder="Optional context, such as before medication or after exercise" /></Form.Item>
        <div className="form-actions"><Button onClick={() => setModalOpen(false)}>Cancel</Button><Button type="primary" htmlType="submit" loading={saving}>Save Reading</Button></div>
      </Form>
    </Modal>
  </div>
}
