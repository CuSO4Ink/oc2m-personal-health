import { t, useLanguage } from './i18n'
import React from 'react'
import { AlertOutlined, CheckCircleOutlined, ClockCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { Alert, Button, Card, DatePicker, Empty, Form, Input, InputNumber, List, Modal, Segmented, Select, Skeleton, Space, Statistic, Table, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { Link, useSearchParams } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api, { apiMessage } from './api'
import Guidance from './Guidance'
import { metricLabels, contextLabels } from './healthLabels'

const { Title, Paragraph, Text } = Typography

const metrics = [
  { key: 'blood_pressure', get label() { return t("血压") }, shortUnit: 'mmHg' },
  { key: 'blood_glucose', get label() { return t("血糖") }, shortUnit: 'mmol/L' },
  { key: 'heart_rate', get label() { return t("心率") }, shortUnit: 'bpm' },
]

function readingValue(reading) {
  if (!reading) return '—'
  return reading.secondary_value == null ? `${reading.value}` : `${reading.value}/${reading.secondary_value}`
}

function statusTag(status) {
  if (status === 'not_assessed') return <Tag>{t("需结合情境解释")}</Tag>
  if (status === 'low') return <Tag color="red">{t("偏低参考标记")}</Tag>
  if (status === 'high') return <Tag color="red">{t("偏高")}</Tag>
  if (status === 'watch') return <Tag color="gold">{t("待核对")}</Tag>
  return <Tag color="green">{t("在配置参考范围内")}</Tag>
}

function friendlyDate(value, withTime = false) {
  return dayjs(value).format(withTime ? 'D MMM YYYY, HH:mm' : 'D MMM')
}

function ChartTooltip({ active, payload }) {
  useLanguage()
  if (!active || !payload?.length) return null
  const reading = payload[0].payload
  return <div className="chart-tooltip"><Text strong>{friendlyDate(reading.measured_at, true)}</Text><div>{readingValue(reading)} {reading.unit}</div><Text type="secondary">{t(reading.source_name)}</Text>{reading.context && <Text type="secondary">{t("Context: ")}{contextLabels[reading.context] || t(reading.context.replace('_', ' '))}</Text>}</div>
}

export default function HealthInsightsPage() {
  useLanguage()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedMetric = metrics.some((item) => item.key === searchParams.get('metric')) ? searchParams.get('metric') : 'blood_pressure'
  const focusedAlert = searchParams.get('alert')
  const focusedReading = searchParams.get('reading')
  const selectedView = 'trend'
  const [context, setContext] = React.useState('')
  const [alertStatus, setAlertStatus] = React.useState('pending')
  const [days, setDays] = React.useState(30)
  const [data, setData] = React.useState(null)
  const [alerts, setAlerts] = React.useState([])
  const [error, setError] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [modalOpen, setModalOpen] = React.useState(() => searchParams.get('add') === '1')
  const [saving, setSaving] = React.useState(false)
  const [editing, setEditing] = React.useState(null)
  const [voidReading, setVoidReading] = React.useState(null)
  const [voidReason, setVoidReason] = React.useState('')
  const [form] = Form.useForm()
  const formMetric = Form.useWatch('metric_type', form)
  React.useEffect(() => {
    if (searchParams.get('add') !== '1') return
    form.setFieldsValue({ metric_type: selectedMetric, measured_at: dayjs(), source_name: t('手工录入'), special_context: 'general', context: selectedMetric === 'blood_glucose' ? 'fasting' : selectedMetric === 'heart_rate' ? 'resting' : '' })
    const next = new URLSearchParams(searchParams); next.delete('add'); setSearchParams(next, {replace: true})
  }, [form, searchParams, selectedMetric, setSearchParams])


  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [metricsResponse, alertsResponse] = await Promise.all([
        api.get('/insights/metrics', { params: { metric: selectedMetric, days, context, reading_id: focusedReading || undefined, timezone_offset_minutes: new Date().getTimezoneOffset() } }),
        api.get('/insights/alerts', { params: { status: focusedAlert ? 'all' : alertStatus } }),
      ])
      setData(metricsResponse.data)
      setAlerts(alertsResponse.data.alerts)
    } catch (requestError) {
      setError(apiMessage(requestError))
    } finally { setLoading(false) }
  }, [days, selectedMetric, context, alertStatus, focusedAlert, focusedReading])

  React.useEffect(() => {
    let active = true
    Promise.all([
      api.get('/insights/metrics', { params: { metric: selectedMetric, days, context, reading_id: focusedReading || undefined, timezone_offset_minutes: new Date().getTimezoneOffset() } }),
      api.get('/insights/alerts', { params: { status: focusedAlert ? 'all' : alertStatus } }),
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
  }, [days, selectedMetric, context, alertStatus, focusedAlert, focusedReading])

  React.useEffect(() => {
    if (!loading && focusedAlert) document.getElementById(`health-alert-${focusedAlert}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [loading, focusedAlert, alerts])

  function changeMetric(metric) {
    if (metric === selectedMetric && !context) return
    setLoading(true); setError(''); setSearchParams({ metric, view: selectedView }); setContext('')
  }

  function changeDays(value) {
    if (value === days) return
    setLoading(true); setError(''); setDays(value)
  }

  function openAddReading() {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ metric_type: selectedMetric, measured_at: dayjs(), source_name: t('手工录入'), special_context: 'general', context: selectedMetric === 'blood_glucose' ? 'fasting' : selectedMetric === 'heart_rate' ? 'resting' : '' })
    setModalOpen(true)
  }

  async function saveReading(values) {
    setSaving(true)
    try {
      const payload = { ...values, measured_at: values.measured_at.toISOString() }
      const response = editing ? await api.patch(`/insights/metrics/${editing.id}`, payload) : await api.post('/insights/metrics', payload)
      if (response.data.alert) message.warning(t('指标已保存，并生成了一条待核对的健康提醒。'))
      else message.success(t('健康指标已保存。'))
      setModalOpen(false)
      window.dispatchEvent(new Event('notifications:changed'))
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
      window.dispatchEvent(new Event('notifications:changed'))
      await load()
      message.success(t('提醒已标记为已核对。'))
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  function editReading(reading) {
    setEditing(reading); form.resetFields(); form.setFieldsValue({ ...reading, measured_at: dayjs(reading.measured_at) }); setModalOpen(true)
  }

  async function confirmVoid() {
    setSaving(true)
    try {
      await api.post(`/insights/metrics/${voidReading.id}/void`, { reason: voidReason })
      setVoidReading(null); setVoidReason(''); await load(); window.dispatchEvent(new Event('notifications:changed'))
      message.success(t('指标已作废，原始值和相关提醒仍保留在历史中。'))
    } catch (failure) { message.error(apiMessage(failure)) }
    finally { setSaving(false) }
  }

  React.useEffect(() => { if (!loading && focusedReading) document.getElementById('measurement-history')?.scrollIntoView({behavior:'smooth',block:'start'}) }, [loading, focusedReading])

  const selected = metrics.find((item) => item.key === selectedMetric)
  const attentionCount = data?.summary.attention_count || 0
  const isBloodPressure = selectedMetric === 'blood_pressure'
  const threshold = selectedMetric === 'blood_pressure' ? 120 : selectedMetric === 'blood_glucose' ? 5.6 : 100
  const contextOptions = selectedMetric === 'blood_glucose' ? [{ value: 'fasting', label: t('空腹') }, { value: 'after_meal', label: t('餐后') }, { value: 'random', label: t('随机') }] : [{ value: 'resting', label: t('静息') }, { value: 'exercise', label: t('运动后') }, { value: 'unknown', label: t('未确认场景') }]
  const showReference = data?.latest?.assessment?.reason === 'adult_reference' && (selectedMetric === 'blood_pressure' || (selectedMetric === 'blood_glucose' && context === 'fasting') || (selectedMetric === 'heart_rate' && context === 'resting'))
  const historyReadings = data ? [...new Map([...data.readings, ...(data.superseded_readings || []), ...(data.focused_reading ? [data.focused_reading] : [])].map((reading) => [reading.id, reading])).values()].sort((a, b) => Number(String(b.id) === focusedReading) - Number(String(a.id) === focusedReading) || b.measured_at.localeCompare(a.measured_at)) : []

  return <div className="page-stack insights-page">
    <div className="page-heading">
      <div><Title level={1}>{t("身体指标")}</Title><Paragraph>{t("查看变化图表，在下方核对每次测量与报告来源。")}</Paragraph></div>
      <Space wrap><Link to="/records/upload"><Button>{t("上传报告")}</Button></Link><Button type="primary" icon={<PlusOutlined />} onClick={openAddReading}>{t("手工记录指标")}</Button></Space>
    </div>

    <div className="measurement-advice-link"><Link to="/advice">{t("查看健康建议与日常关注")}</Link></div>

    {selectedView !== 'review' && <><div className="metric-selector" role="tablist">{metrics.map((metric) => <button className={selectedMetric === metric.key ? 'metric-option active' : 'metric-option'} key={metric.key} onClick={() => changeMetric(metric.key)}><span>{metric.label}</span><small>{metric.shortUnit}</small></button>)}</div>

    <div className="insights-toolbar"><div><Text strong>{t('{metric} trend',{metric:selected.label})}</Text><Text type="secondary">{t(" · 按本机时区显示")}</Text></div><Segmented value={days} options={[{ label: t('7 天'), value: 7 }, { label: t('30 天'), value: 30 }, { label: t('90 天'), value: 90 }, { label: t('1 年'), value: 365 }]} onChange={changeDays} /></div>

    {selectedMetric !== 'blood_pressure' && <Select className="insight-context-filter" value={context} options={[{ value: '', label: t('全部测量场景') }, ...contextOptions]} onChange={(value) => { setLoading(true); setError(''); setContext(value) }} />}
    </>}
    {error && <Alert type="error" showIcon message={t("健康状况暂时无法加载")} description={error} action={<Button onClick={load}>{t("重试")}</Button>} />}
    {loading ? <Card><Skeleton active paragraph={{ rows: 8 }} /></Card> : !error && data && <>
<div className="page-stack">      <div className="insight-stats">
        <Card><Statistic title={t("最近读数")} value={readingValue(data.latest)} suffix={data.latest?.unit || selected.shortUnit} /><div className="stat-foot">{data.latest ? <Space>{statusTag(data.latest.status)}<Text type="secondary">{friendlyDate(data.latest.measured_at, true)}</Text></Space> : <Text type="secondary">{t("此时间范围内没有记录")}</Text>}</div></Card>
        <Card><Statistic title={isBloodPressure ? t('收缩压均值') : t('均值')} value={data.summary.average ?? '—'} suffix={selected.shortUnit} /><div className="stat-foot"><Text type="secondary">{t('{count} readings across {days} dates',{count:data.summary.count,days:data.summary.distinct_days})}{isBloodPressure ? t(' · Average diastolic: {value} mmHg',{value:data.summary.secondary_average ?? '—'}) : ''}</Text></div></Card>
        <Card><Statistic title={isBloodPressure ? t('收缩压范围') : t('数值范围')} value={data.summary.count ? `${data.summary.minimum}–${data.summary.maximum}` : '—'} suffix={selected.shortUnit} /><div className="stat-foot"><Text type="secondary">{t("所选时间范围")}</Text></div></Card>
      </div>

      <Card className="trend-card">
        {data.readings.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("此时间范围内没有记录")}><Button onClick={openAddReading}>{t("记录第一个指标")}</Button></Empty> : <div className="chart-wrap"><ResponsiveContainer width="100%" height={340}><LineChart data={data.readings} margin={{ top: 18, right: 22, left: 0, bottom: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#edf0f3" /><XAxis dataKey="measured_at" tickFormatter={(value) => friendlyDate(value)} minTickGap={30} /><YAxis domain={['auto', 'auto']} tickFormatter={(value) => selectedMetric === 'blood_glucose' ? Number(value).toFixed(1) : Math.round(value)} unit={` ${selected.shortUnit}`} width={78} /><Tooltip content={<ChartTooltip />} /><Legend />{showReference && <ReferenceLine y={threshold} stroke="#d97706" strokeDasharray="5 5" label={{ value: t('Review threshold'), fill: '#a16207', fontSize: 12 }} />}{showReference && selectedMetric === 'heart_rate' && context === 'resting' && <ReferenceLine y={60} stroke="#d97706" strokeDasharray="5 5" />}<Line name={isBloodPressure ? t('收缩压') : selected.label} type="monotone" dataKey="value" stroke="#397f78" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />{isBloodPressure && <Line name={t("舒张压")} type="monotone" dataKey="secondary_value" stroke="#5878a8" strokeWidth={3} dot={{ r: 4 }} />}</LineChart></ResponsiveContainer></div>}
        <div className={`sufficiency ${data.data_sufficiency.status}`}><ClockCircleOutlined /><div><Text strong>{data.data_sufficiency.status === 'sufficient' ? t('已有足够记录描述变化') : data.data_sufficiency.status === 'stale' ? t('近期记录需要补充') : data.data_sufficiency.status === 'mixed_context' ? t('请按同类测量场景比较') : t('记录仍较少')}</Text><Text>{data.data_sufficiency.status === 'mixed_context' ? t('空腹、餐后或运动等不同情境不直接合并比较。') : t('至少三个不同本地日期的三条记录，且最近一次在14天以内，才提供描述性变化说明。')}</Text><Text type="secondary">{data.summary.unassessed_count}{t(" 条记录需要按个人情境解释。")}</Text></div></div>
      </Card>

<div><Link to={`/services?tab=reminders&new=${selectedMetric}`}><Button>{t("设置测量提醒")}</Button></Link></div><details className="quiet-details"><summary>{t("查看趋势说明")}</summary>        <Card title={t("趋势说明")} className="summary-card">
          {data.data_sufficiency.status !== 'sufficient' ? <Alert type="warning" showIcon message={t("记录暂不足以生成趋势说明")} description={t(data.data_sufficiency.message)} /> : <>
            <div className="summary-row"><CheckCircleOutlined /><div><Text strong>{t("Latest status")}</Text><Paragraph>{data.latest.status === 'not_assessed' ? t('The latest reading needs context-specific interpretation; no normal-range classification is assigned.') : data.latest.status === 'in_range' ? t('The latest {metric} reading is within the configured reference threshold.', {metric: selected.label.toLowerCase()}) : t('The latest reading is marked for review.')}</Paragraph></div></div>
            <div className="summary-row"><AlertOutlined /><div><Text strong>{t("Points to review")}</Text><Paragraph>{attentionCount === 0 ? t('No reading in this period crossed a configured threshold.') : t('Readings crossing a configured threshold: {count}. Select a chart point to review its time and source.', {count: attentionCount})}</Paragraph></div></div>
            <Text type="secondary">{t("Rule-based summary generated ")}{friendlyDate(data.generated_at, true)}{t(" from the selected ")}{days}{t("-day period.")}</Text>
          </>}
          <Paragraph>{data.trend && <>{t("First-to-last reading ")}{t(data.trend.direction)}: {data.trend.change} {selected.shortUnit}{data.trend.secondary_change != null && t(' · Diastolic change: {value} mmHg', {value: data.trend.secondary_change})}. {t(data.trend.message)}</>}</Paragraph><Text type="secondary">{t("No disease probability, diagnosis or medication plan is generated.")}</Text>
        </Card>

</details>      <Guidance id="reference-rule" title={t('How reference flags work · {version}', {version: data.reference.version})}><Paragraph>{t(data.reference.text)}</Paragraph><Paragraph type="secondary">{t(data.reference.limitations)}{t(" Historical alerts retain the rule used when they were created.")}</Paragraph><Space wrap>{data.reference.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{t(source.title)}</a>)}</Space></Guidance>
      {selectedMetric !== 'blood_pressure' && <Guidance id="measurement-contexts" title={t("Compare similar measurement contexts")}>{t('Readings in this view: {contexts}. Use the context filter before comparing averages. Reference lines are shown only for a selected fasting or resting context.', {contexts: Object.entries(data.summary.context_counts).map(([key, count]) => `${contextLabels[key] || t(key.replace('_', ' '))}: ${count}`).join(' · ') || t('None')})}</Guidance>}
<Card id="measurement-history" title={t("测量记录与来源")}><Paragraph type="secondary">{t("在这里核对、更正或作废记录；报告导入的指标可回到原文。")}</Paragraph>{data.focused_reading_outside_period && <Alert type="info" showIcon title={t("这条来源记录不在所选趋势时间范围内。")} description={t("为方便核对，已将其放在明细首行。图表、均值与趋势仍只使用所选时间范围。")} style={{ marginBottom: 16 }} />}<Table key={focusedReading || 'history'} rowKey="id" rowClassName={(reading) => String(reading.id) === focusedReading ? 'linked-item' : ''} scroll={{ x: 850 }} pagination={{ pageSize: 8 }} dataSource={historyReadings} columns={[
        {title: t('测量时间'), dataIndex: 'measured_at', render: (value) => friendlyDate(value, true)},
        {title: t('读数'), render: (_, reading) => `${readingValue(reading)} ${reading.unit}`},
        {title: t('测量场景'), dataIndex: 'context', render: (value) => contextLabels[value] || t('未记录')},
        {title: t('参考标记'), render: (_, reading) => <>{(reading.flags?.length ? reading.flags : [reading.status]).map((flag) => <React.Fragment key={flag}>{statusTag(flag)}</React.Fragment>)}{reading.assessment?.reason !== 'adult_reference' && <div><Text type="secondary">{t(reading.assessment?.reason.replaceAll('_', ' '))}</Text></div>}{reading.disposition && <div><Tag>{t(reading.disposition.status)}</Tag>{reading.disposition.reason}</div>}</>},
        {title: t('来源'), render: (_, reading) => <Space direction="vertical" size={0}><Tag>{reading.report_source ? t('报告导入') : t('手工录入')}</Tag><span>{reading.report_source?.filename || t(reading.source_name)}</span>{reading.report_source && <><Link to={reading.report_source.review_path}>{t("查看核对记录")}</Link>{reading.report_source.attachment_id && <Link to={`/records/${reading.report_source.record_id}?document=${reading.report_source.attachment_id}`}>{t("打开 PDF 原件")}</Link>}</>}</Space>}, {title: t('备注'), dataIndex: 'notes', render: (value) => value || '—'},
        {title: t('操作'), render: (_, reading) => reading.is_editable ? <Space><Button onClick={() => editReading(reading)}>{t("更正")}</Button><Button danger onClick={() => { setVoidReading(reading); setVoidReason('') }}>{t("作废")}</Button></Space> : <Text type="secondary">{t("保留历史 / 只读")}</Text>},
      ]} /></Card>
          <details className="quiet-details" open={Boolean(focusedAlert)}><summary>{t("逐条指标提醒 · ")}{alerts.filter(item=>!item.acknowledged_at&&!item.disposition).length}{t(" 项待核对")}</summary><Card title={t("指标提醒历史")} extra={<Select value={focusedAlert?'all':alertStatus} options={[{value:'pending',label:t('待核对')},{value:'reviewed',label:t('已核对')},{value:'all',label:t('全部')}]} onChange={(value)=>{setLoading(true);setError('');setAlertStatus(value);setSearchParams({metric:selectedMetric,view:'review'})}}/>}>
            {alerts.length===0?<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("暂无此类提醒")}/>:<List pagination={{pageSize:5}} dataSource={focusedAlert?[...alerts].sort((a,b)=>Number(b.id===Number(focusedAlert))-Number(a.id===Number(focusedAlert))):alerts} renderItem={(alert)=><List.Item id={`health-alert-${alert.id}`} actions={alert.disposition?[<Tag key="history">{t("已更正 / 作废的历史提醒")}</Tag>]:alert.acknowledged_at?[<Tag key="reviewed">{t("已核对")}</Tag>]:[<Button key="review" type="link" onClick={()=>acknowledgeAlert(alert.id)}>{t("标记已核对")}</Button>]}><List.Item.Meta title={t(`${metricLabels[alert.measurement.metric_type]}记录需要核对`)} description={<><Paragraph>{readingValue(alert.measurement)} {alert.measurement.unit} · {friendlyDate(alert.measurement.measured_at,true)}</Paragraph><Paragraph type="secondary">{t("记录触发了当时的参考规则，请结合原始数值及测量场景核对。标记已核对不会改变健康数据。")}</Paragraph><Link to={`/insights?metric=${alert.measurement.metric_type}&reading=${alert.measurement.id}`}>{t("查看对应记录")}</Link><div><Text type="secondary">{t("参考版本 ")}{alert.rule_version}</Text></div></>}/></List.Item>}/>}
          </Card></details>
</div>
    </>}

    <Modal title={editing ? t("更正健康指标") : t("手工记录指标")} open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={saveReading} initialValues={{metric_type: selectedMetric, measured_at: dayjs(), source_name: t('手工录入'), special_context: 'general', context: selectedMetric === 'blood_glucose' ? 'fasting' : selectedMetric === 'heart_rate' ? 'resting' : ''}} >
        <Form.Item label={t("指标类型")} name="metric_type" rules={[{ required: true }]}><Select disabled={Boolean(editing)} options={metrics.map(({ key, label }) => ({ value: key, label }))} onChange={(value) => form.setFieldsValue({ value: null, secondary_value: null, context: value === 'blood_glucose' ? 'fasting' : value === 'heart_rate' ? 'resting' : '' })} /></Form.Item>
        {formMetric === 'blood_pressure' ? <div className="two-field-row"><Form.Item label={t("收缩压")} name="value" rules={[{ required: true, message: t('请输入收缩压') }]}><InputNumber min={50} max={260} addonAfter="mmHg" /></Form.Item><Form.Item label={t("舒张压")} name="secondary_value" rules={[{ required: true, message: t('请输入舒张压') }]}><InputNumber min={30} max={160} addonAfter="mmHg" /></Form.Item></div> : <Form.Item label={t("读数")} name="value" rules={[{ required: true, message: t('请输入读数') }]}><InputNumber className="full-width" min={formMetric === 'heart_rate' ? 25 : 1} max={formMetric === 'heart_rate' ? 240 : 35} step={formMetric === 'blood_glucose' ? 0.1 : 1} addonAfter={formMetric === 'heart_rate' ? 'bpm' : 'mmol/L'} /></Form.Item>}
        {formMetric === 'heart_rate' && <Form.Item label={t("测量场景")} name="context" rules={[{required: true}]}><Select options={[{value: 'resting', label: t('静息')}, {value: 'exercise', label: t('运动期间 / 运动后')}, {value: 'unknown', label: t('不确定')}]} /></Form.Item>}
        {formMetric === 'blood_glucose' && <Form.Item label={t("测量场景")} name="context" rules={[{ required: true }]}><Select options={[{ value: 'fasting', label: t('空腹') }, { value: 'after_meal', label: t('餐后') }, { value: 'random', label: t('随机') }]} /></Form.Item>}
        <Form.Item label={t("适用情况")} name="special_context" rules={[{ required: true }]}><Select options={[{value: 'general', label: t('一般成人参考')}, {value: 'pregnancy', label: t('孕期：请由专业人员解释')}, {value: 'individual_target', label: t('个人医疗目标：请由专业人员解释')}, {value: 'unknown', label: t('不确定：不套用成人参考')}]} /></Form.Item>
        <Form.Item label={t("测量时间")} name="measured_at" rules={[{ required: true }]}><DatePicker showTime className="full-width" disabledDate={(date) => date && date > dayjs().endOf('day')} /></Form.Item>
        <Form.Item label={t("来源")} name="source_name" rules={[{ required: true, message: t('请输入来源') }]}><Input placeholder={t("例如：手工填写或家用设备")} /></Form.Item>
        <Form.Item label={t("备注")} name="notes"><Input.TextArea rows={3} maxLength={300} showCount placeholder={t("可补充测量前后的情境")} /></Form.Item>
        {editing && <Form.Item label={t("更正原因")} name="reason" rules={[{required: true, whitespace: true}]}><Input.TextArea maxLength={300} /></Form.Item>}
        <div className="form-actions"><Button onClick={() => setModalOpen(false)}>{t("取消")}</Button><Button type="primary" htmlType="submit" loading={saving}>{t("保存指标")}</Button></div>
      </Form>
    </Modal>
    <Modal title={t("作废这条指标？")} open={Boolean(voidReading)} onCancel={() => setVoidReading(null)} onOk={confirmVoid} confirmLoading={saving} okText={t("确认作废")} okButtonProps={{danger: true, disabled: !voidReason.trim()}}><Paragraph>{t("作废后不再计入当前图表和统计，原始值与相关提醒保留在历史中。")}</Paragraph><Input.TextArea aria-label={t("作废原因")} value={voidReason} onChange={(event) => setVoidReason(event.target.value)} maxLength={300} placeholder={t("为什么要作废这条记录？")} /></Modal>
  </div>
}
