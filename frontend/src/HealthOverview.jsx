import React from 'react'
import { CalendarOutlined, HeartOutlined, PlusOutlined, ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Empty, List, Skeleton, Space, Statistic, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import { useAuth } from './auth'

const { Title, Paragraph, Text } = Typography
const time = (value) => dayjs(value).format('D MMM YYYY · HH:mm')

export default function HealthOverviewPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [data, setData] = React.useState(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [refreshing, setRefreshing] = React.useState(false)

  React.useEffect(() => {
    let active = true
    api.get('/overview').then((response) => { if (active) setData(response.data) })
      .catch((requestError) => { if (active) setError(apiMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function refresh() {
    setRefreshing(true); setError('')
    try { setData((await api.get('/overview')).data) }
    catch (requestError) { setError(apiMessage(requestError)) }
    finally { setRefreshing(false) }
  }

  return <div className="page-stack overview-page">
    <div className="page-heading"><div><Title level={1}>Health Overview</Title><Paragraph>Welcome back, {user.full_name.split(' ')[0]}. See what needs attention and prepare for your next step.</Paragraph>{data && <Text type="secondary">Last refreshed {time(data.generated_at)}{error ? ' · Showing previously loaded information' : ''}</Text>}</div><Button icon={<ReloadOutlined />} loading={refreshing} onClick={refresh}>Refresh</Button></div>
    {error && <Alert type="error" showIcon message="Overview could not be refreshed" description={error} action={<Button onClick={refresh}>Try again</Button>} />}
    {loading ? <Card><Skeleton active paragraph={{ rows: 12 }} /></Card> : data && <>
      <div className="overview-actions"><Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/records/new')}>Add Health Record</Button><Button icon={<HeartOutlined />} onClick={() => navigate('/insights')}>Record a Reading</Button><Button icon={<SafetyCertificateOutlined />} onClick={() => navigate('/sharing')}>Share with a Professional</Button><Button icon={<CalendarOutlined />} onClick={() => navigate('/services')}>Find Care</Button></div>
      <div className="overview-stats"><Card><Statistic title="Health alerts to review" value={data.attention.health_alert_count} /><Button type="link" onClick={() => navigate('/insights')}>Review alerts</Button></Card><Card><Statistic title="Health tasks due" value={data.attention.due_task_count} /><Button type="link" onClick={() => navigate('/services')}>Review tasks</Button></Card><Card><Statistic title="Upcoming appointments" value={data.care.appointment_count} /><Button type="link" onClick={() => navigate('/services')}>Manage appointments</Button></Card><Card><Statistic title="Active sharing permissions" value={data.sharing.active_count} /><Button type="link" onClick={() => navigate('/sharing')}>Manage permissions</Button></Card></div>
      <section><div className="section-heading"><div><Title level={3}>Needs your attention</Title><Paragraph>Reading a notification does not complete the underlying health task.</Paragraph></div><Button onClick={() => navigate('/notifications')}>All notifications</Button></div><div className="overview-attention">{data.attention.alerts.map((alert) => <Alert key={`alert-${alert.id}`} type="warning" showIcon message={alert.title} description={<><Paragraph>{alert.message}</Paragraph><Text type="secondary">Reference rule {alert.rule_version} · {time(alert.measurement.measured_at)}</Text></>} action={<Button onClick={() => navigate('/insights')}>Review reading</Button>} />)}{data.attention.due_tasks.map((task) => <Alert key={`task-${task.id}`} type="warning" showIcon message={task.title} description={`Due ${time(task.next_due_at)} · ${task.source_name}`} action={<Button onClick={() => navigate('/services')}>Open task</Button>} />)}{!data.attention.health_alert_count && !data.attention.due_task_count && <Card><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No pending health alerts or overdue tasks" /></Card>}</div></section>
      <section><Title level={3}>Latest readings</Title><div className="reading-grid">{data.readings.map((metric) => <Card key={metric.key} className="reading-card"><Text strong>{metric.label}{metric.reading?.context === 'fasting' ? ' · Fasting' : ''}</Text>{metric.reading ? <><div className="reading-value">{metric.reading.secondary_value == null ? metric.reading.value : `${metric.reading.value}/${metric.reading.secondary_value}`} <small>{metric.reading.unit}</small></div><Space wrap><Tag color={metric.reading.status === 'in_range' ? 'green' : 'gold'}>{metric.reading.status === 'not_assessed' ? 'Context needs interpretation' : metric.reading.status === 'in_range' ? 'Within configured reference' : 'Review reference threshold'}</Tag>{metric.stale && <Tag color="orange">Over 14 days old</Tag>}</Space><Text type="secondary">Measured {time(metric.reading.measured_at)}</Text><Text type="secondary">Source: {metric.reading.source_name}</Text></> : <><Text type="secondary">No reading recorded yet.</Text><Paragraph>Add a reading to begin tracking this metric.</Paragraph></>}<Button type="link" onClick={() => navigate('/insights')}>{metric.reading ? 'View trends →' : 'Add a reading →'}</Button></Card>)}</div></section>
      <div className="overview-lower-grid"><Card title="Your next care steps" extra={<Button type="link" onClick={() => navigate('/services')}>View all</Button>}>{data.care.appointments.length ? <List dataSource={data.care.appointments} renderItem={(appointment) => <List.Item><List.Item.Meta title={<Space wrap><Text strong>{appointment.service.name}</Text><Tag color="green">Confirmed</Tag></Space>} description={`${time(appointment.slot.starts_at)} · ${appointment.service.facility.name}`} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No upcoming appointments"><Button onClick={() => navigate('/services')}>Browse services</Button></Empty>}{data.care.upcoming_tasks.length > 0 && <><Title level={5}>Upcoming health tasks</Title><List size="small" dataSource={data.care.upcoming_tasks} renderItem={(task) => <List.Item><List.Item.Meta title={task.title} description={`${time(task.next_due_at)} · ${task.source_name}`} /></List.Item>} /></>}</Card><Card title="Sharing & access" extra={<Button type="link" onClick={() => navigate('/sharing')}>Review</Button>}>{data.sharing.expiring.length ? data.sharing.expiring.map((grant) => <Alert className="overview-sharing-notice" key={grant.id} type="warning" showIcon message="Permission expires within 7 days" description={`${grant.recipient.full_name} · ${grant.records.length} selected records · ${time(grant.expires_at)}`} />) : <Paragraph>No active permissions expire within seven days.</Paragraph>}<Text strong>{data.sharing.unusual_count} unusual access events in history</Text><Paragraph type="secondary">Historical access activity remains available even after permission revocation.</Paragraph>{data.sharing.recent_unusual.map((event) => <div className="overview-access-event" key={event.id}><Text>{event.recipient.full_name} · {event.action} · {event.result}</Text><Text type="secondary">{time(event.occurred_at)} · {event.location}</Text></div>)}</Card></div>
      <section><div className="section-heading"><Title level={3}>Recently updated records</Title><Button type="link" onClick={() => navigate('/records')}>All {data.records.count} records</Button></div>{data.records.recent.length ? <div className="record-grid">{data.records.recent.map((record) => <Card key={record.id}><Tag>{record.record_type}</Tag><Title level={4}>{record.title}</Title><div className="overview-record-meta"><Text>Record date: {record.record_date}</Text><Text type="secondary">Updated {time(record.updated_at)}</Text><Text type="secondary">Source: {record.source_name}</Text></div><Button type="link" onClick={() => navigate(`/records/${record.id}`)}>Open record →</Button></Card>)}</div> : <Card><Empty description="No health records yet"><Button type="primary" onClick={() => navigate('/records/new')}>Add your first record</Button></Empty></Card>}</section>
      <Alert type="info" showIcon message="Data connection status" description={data.integration.message} />
    </>}
  </div>
}
