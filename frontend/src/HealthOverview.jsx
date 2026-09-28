import React from 'react'
import { ArrowRightOutlined, FolderOpenOutlined, LineChartOutlined, BulbOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Collapse, List, Skeleton, Space, Tag, Typography } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import { useAuth } from './auth'
import { useLanguage } from './i18n'
import { metricLabels } from './healthLabels'
import './PersonalWorkspace.css'

const { Title, Paragraph, Text } = Typography
export default function HealthOverviewPage() {
  const { user } = useAuth()
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [data, setData] = React.useState(null)
  const [error, setError] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try { setData((await api.get('/overview')).data) }
    catch (failure) { setError(apiMessage(failure)) }
    finally { setLoading(false) }
  }, [])
  React.useEffect(() => {
    let active = true
    api.get('/overview').then(({data: next}) => { if (active) setData(next) }).catch(failure => { if (active) setError(apiMessage(failure)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  const review = data?.records.pending_reviews?.[0]
  const firstAlert = data?.attention.alerts[0]
  const next = review ? { title:t('Your reports are ready to review'), detail:t('Reports with information awaiting your confirmation: {count}',{count:data.records.pending_review_count}), label:t('Review extracted information'), path:`/records/${review.record_id}?extraction=${review.id}` }
    : firstAlert ? {title:t('A measurement needs a closer look'),detail:t('Check the value, measurement context and original source before drawing conclusions.'),label:t('Review measurement'),path:`/insights?metric=${firstAlert.measurement.metric_type}&alert=${firstAlert.id}`}
    : data?.records.count ? {title:t('Your records are together. See what they tell you.'),detail:t('Explore your measurements or prepare advice using your latest information.'),label:t('View health advice'),path:'/advice'}
    : {title:t('Start with what you already know'),detail:t('Add your basic health information, then bring in a report. You can fill in the rest later.'),label:t('Add basic health information'),path:'/profile'}
  return <div className="page-stack personal-home">
    <div className="page-heading"><div><Text className="home-eyebrow">{t('YOUR PERSONAL HEALTH SPACE')}</Text><Title level={1}>{t('Hello, {name}',{name:user.full_name})}</Title><Paragraph>{t('Keep your information together, follow changes, and decide what to do next.')}</Paragraph></div><Button icon={<ReloadOutlined />} aria-label={t('Refresh home')} loading={loading} onClick={load}>{t('Refresh')}</Button></div>
    {error && <Alert type="error" title={t('Home could not be updated')} description={error} action={<Button onClick={load}>{t('Retry')}</Button>} />}
    {loading && !data ? <Skeleton active paragraph={{rows:5}} /> : data && <>
      <Card className="home-next-card"><Text className="home-eyebrow">{t('YOUR NEXT STEP')}</Text><Title level={2}>{next.title}</Title><Paragraph>{next.detail}</Paragraph><Button type="primary" icon={<ArrowRightOutlined />} onClick={()=>navigate(next.path)}>{next.label}</Button></Card>
      <section className="home-journey" aria-label={t('How your health information connects')}>
        <article className="journey-records"><div className="journey-title"><span>01</span><FolderOpenOutlined /><Title level={3}>{t('Keep your records')}</Title></div><Paragraph>{t('Two parts of one health folder: information about you, and documents from your care.')}</Paragraph><div className="journey-record-links"><Link to="/profile"><strong>{t('Basic information & history')}</strong><span>{t('Personal details, illnesses, family history, medicines and allergies')}</span><ArrowRightOutlined /></Link><Link to="/records"><strong>{t('Reports & documents')}</strong><span>{t('Sync, upload, search and review your original documents')}</span><ArrowRightOutlined /></Link></div></article>
        <article><div className="journey-title"><span>02</span><LineChartOutlined /><Title level={3}>{t('Track measurements')}</Title></div><Paragraph>{t('See blood pressure, glucose and heart rate over time. Each reading keeps its source.')}</Paragraph><Link to="/insights">{t('View trends & readings')} <ArrowRightOutlined /></Link></article>
        <article><div className="journey-title"><span>03</span><BulbOutlined /><Title level={3}>{t('Understand next steps')}</Title></div><Paragraph>{t('Bring your information together for possible concerns and practical everyday suggestions.')}</Paragraph><Link to="/advice">{t('View health advice')} <ArrowRightOutlined /></Link></article>
      </section>
      {data.readings.some(item=>item.reading) && <Card className="home-reading-summary" title={t('Latest measurements')} extra={<Link to="/insights">{t('All measurements')}</Link>}><div className="home-reading-grid">{data.readings.filter(item=>item.reading).map(item=><div key={item.key}><Text strong>{t(metricLabels[item.key] || item.label)}</Text><div className="home-reading-value">{item.reading.value}{item.reading.secondary_value != null ? `/${item.reading.secondary_value}` : ''} <small>{item.reading.unit}</small></div><Text type="secondary">{dayjs(item.reading.measured_at).format('YYYY-MM-DD HH:mm')}</Text><Tag color={['not_assessed','in_range'].includes(item.reading.status)?'default':'gold'}>{item.reading.status==='in_range'?t('Within reference range'):item.reading.status==='not_assessed'?t('Context needed'):t('Review this reading')}</Tag><Link to={`/insights?metric=${item.key}&reading=${item.reading.id}`}>{t('View reading & source')}</Link></div>)}</div></Card>}
      <Collapse className="home-more" items={[{key:'details',label:t('Reminders, appointments & sharing'),children:<div className="page-stack"><List dataSource={data.attention.due_tasks} locale={{emptyText:t('No reminders due.')}} renderItem={item=><List.Item actions={[<Link key="open" to={`/services?tab=reminders&reminder=${item.id}`}>{t('View')}</Link>]}><List.Item.Meta title={item.title} description={dayjs(item.next_due_at).format('YYYY-MM-DD HH:mm')} /></List.Item>} /><Space wrap><Link to="/services">{t('Reminders & appointments')}</Link><Link to="/sharing">{t('Manage sharing ({count})',{count:data.sharing.active_count})}</Link><Link to="/notifications">{t('All notifications')}</Link></Space></div>}]} />
    </>}
  </div>
}
