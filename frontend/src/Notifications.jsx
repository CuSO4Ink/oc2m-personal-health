import React from 'react'
import { BellOutlined, CalendarOutlined, CheckOutlined, ClearOutlined, CommentOutlined, ExclamationCircleOutlined, EyeOutlined, HeartOutlined, LockOutlined, SafetyCertificateOutlined, SearchOutlined, ShareAltOutlined } from '@ant-design/icons'
import { Alert, Badge, Button, Card, Checkbox, Empty, Input, List, Popconfirm, Select, Skeleton, Space, Statistic, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import api, { apiMessage } from './api'

const { Title, Paragraph, Text } = Typography

const categoryConfig = {
  health: { label: 'Health', color: 'red', icon: <HeartOutlined /> },
  care: { label: 'Care', color: 'blue', icon: <CalendarOutlined /> },
  sharing: { label: 'Sharing', color: 'purple', icon: <ShareAltOutlined /> },
  security: { label: 'Security', color: 'orange', icon: <SafetyCertificateOutlined /> },
  community: { label: 'Community', color: 'cyan', icon: <CommentOutlined /> },
  system: { label: 'System', color: 'default', icon: <BellOutlined /> },
}

function notifyHeaderChanged() {
  window.dispatchEvent(new Event('notifications:changed'))
}

export default function NotificationsPage() {
  const navigate = useNavigate()
  const [notifications, setNotifications] = React.useState([])
  const [summary, setSummary] = React.useState({ unread: 0, total: 0, unread_by_category: {} })
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [status, setStatus] = React.useState('all')
  const [category, setCategory] = React.useState('all')
  const [search, setSearch] = React.useState('')

  const load = React.useCallback(async (filters = {}) => {
    setLoading(true); setError('')
    try {
      const response = await api.get('/notifications', { params: { status, category, q: search, ...filters } })
      setNotifications(response.data.notifications); setSummary(response.data.summary); notifyHeaderChanged()
    } catch (requestError) { setError(apiMessage(requestError)) }
    finally { setLoading(false) }
  }, [category, search, status])

  React.useEffect(() => {
    let active = true
    api.get('/notifications').then((response) => {
      if (!active) return
      setNotifications(response.data.notifications); setSummary(response.data.summary); notifyHeaderChanged()
    }).catch((requestError) => { if (active) setError(apiMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function setRead(notification, read) {
    try {
      await api.patch(`/notifications/${notification.id}/read`, { read })
      await load(); notifyHeaderChanged()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function openNotification(notification) {
    if (notification.unread) await setRead(notification, true)
    if (notification.action_path) navigate(notification.action_path)
  }

  async function markAllRead() {
    try {
      await api.post('/notifications/read-all', { category })
      message.success(category === 'all' ? 'All notifications marked as read.' : 'Visible category marked as read.')
      await load(); notifyHeaderChanged()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function clearNotification(notificationId) {
    try {
      await api.delete(`/notifications/${notificationId}`)
      message.success('Notification cleared.'); await load(); notifyHeaderChanged()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function savePreferences(values) {
    try {const response = await api.put('/notifications/preferences', {muted_categories: values}); setSummary(response.data.summary); notifyHeaderChanged(); message.success('Badge preferences saved.')}
    catch(error) {message.error(apiMessage(error))}
  }

  function resetFilters() {
    setStatus('all'); setCategory('all'); setSearch(''); load({ status: 'all', category: 'all', q: '' })
  }

  return <div className="page-stack notifications-page">
    <div className="page-heading"><div><Title level={1}>Notifications</Title><Paragraph>Review health, care, sharing, security and community updates in one place. Event message times use UTC; list timestamps use your local timezone.</Paragraph></div><Button icon={<CheckOutlined />} disabled={!notifications.some((item) => item.unread)} onClick={markAllRead}>Mark all as read</Button></div>
    {error && <Alert type="error" showIcon message="Notifications could not be loaded" description={error} action={<Button onClick={() => load()}>Try again</Button>} />}
    <div className="notification-summary"><Card><Statistic title="Unread requiring attention" value={summary.unread} prefix={<BellOutlined />} /></Card><Card><Statistic title="Health & care" value={(summary.unread_by_category?.health || 0) + (summary.unread_by_category?.care || 0)} prefix={<HeartOutlined />} /></Card><Card><Statistic title="Security & sharing" value={(summary.unread_by_category?.security || 0) + (summary.unread_by_category?.sharing || 0)} prefix={<LockOutlined />} /></Card></div>
    <Card className="notification-filter-card"><div className="notification-filters"><Input allowClear prefix={<SearchOutlined />} placeholder="Search notification or source" value={search} onChange={(event) => setSearch(event.target.value)} onPressEnter={() => load()} /><Select value={status} onChange={setStatus} options={[{ value: 'all', label: 'All states' }, { value: 'unread', label: 'Unread' }, { value: 'read', label: 'Read' }, {value: 'resolved', label: 'Resolved events'}]} /><Select value={category} onChange={setCategory} options={[{ value: 'all', label: 'All categories' }, ...Object.entries(categoryConfig).map(([value, config]) => ({ value, label: config.label }))]} /><Button type="primary" onClick={() => load()}>Apply filters</Button><Button onClick={resetFilters}>Reset</Button></div></Card>
    {loading ? <Card><Skeleton active paragraph={{ rows: 9 }} /></Card> : notifications.length === 0 ? <Card><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No notifications match these filters" /></Card> : <List pagination={{pageSize: 10}} className="notification-list" dataSource={notifications} renderItem={(notification) => {
      const config = categoryConfig[notification.category] || categoryConfig.system
      return <List.Item className={notification.unread ? 'unread' : ''} actions={[<Button key="read" type="text" icon={notification.unread ? <CheckOutlined /> : <EyeOutlined />} onClick={() => setRead(notification, notification.unread)}>{notification.unread ? 'Mark read' : 'Mark unread'}</Button>, notification.action_path && <Button key="open" type="link" onClick={() => openNotification(notification)}>Open details</Button>, <Popconfirm key="clear" title="Clear this notification?" description="It will be removed from this list." onConfirm={() => clearNotification(notification.id)}><Button type="text" danger icon={<ClearOutlined />}>Clear</Button></Popconfirm>].filter(Boolean)}><List.Item.Meta avatar={<Badge dot={notification.unread}><div className={`notification-icon ${notification.severity}`}>{config.icon}</div></Badge>} title={<Space wrap><Text strong>{notification.title}</Text><Tag color={config.color}>{config.label}</Tag>{notification.resolved && <Tag color="green">Event resolved</Tag>}{notification.severity === 'urgent' && !notification.resolved && <Tag color="red" icon={<ExclamationCircleOutlined />}>Needs attention</Tag>}</Space>} description={<div className="notification-detail"><Text>{notification.message}</Text><span>{dayjs(notification.created_at).format('D MMM YYYY · HH:mm')} · Source: {notification.source_name}</span></div>} /></List.Item>
    }} />}
    <Card title="Unread badge preferences"><Paragraph type="secondary">Mute these categories in the header badge. Notices remain saved and visible in this inbox. Health, security and system notices always count; resolved events no longer count.</Paragraph><Checkbox.Group value={summary.muted_categories || []} options={[{value: 'care', label: 'Mute care'}, {value: 'sharing', label: 'Mute sharing'}, {value: 'community', label: 'Mute community'}]} onChange={savePreferences} /></Card>
    <Alert type="info" showIcon message="In-app notifications are active" description="Email, SMS and device push delivery will be connected after the customer confirms channels, consent and urgency rules." />
  </div>
}
