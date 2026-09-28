import { t, useLanguage } from './i18n'
import React from 'react'
import { BellOutlined, CalendarOutlined, CheckOutlined, ClearOutlined, CommentOutlined, ExclamationCircleOutlined, EyeOutlined, HeartOutlined, LockOutlined, SafetyCertificateOutlined, SearchOutlined, ShareAltOutlined } from '@ant-design/icons'
import { Alert, Badge, Button, Card, Checkbox, Empty, Input, List, Popconfirm, Select, Skeleton, Space, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import api, { apiMessage } from './api'
import Guidance from './Guidance'

const { Title, Paragraph, Text } = Typography

const categoryConfig = {
  health: { get label() { return t("健康") }, color: 'red', icon: <HeartOutlined /> },
  care: { get label() { return t("服务") }, color: 'blue', icon: <CalendarOutlined /> },
  sharing: { get label() { return t("共享") }, color: 'purple', icon: <ShareAltOutlined /> },
  security: { get label() { return t("安全") }, color: 'orange', icon: <SafetyCertificateOutlined /> },
  community: { get label() { return t("社区") }, color: 'cyan', icon: <CommentOutlined /> },
  system: { get label() { return t("系统") }, color: 'default', icon: <BellOutlined /> },
}

function notifyHeaderChanged() {
  window.dispatchEvent(new Event('notifications:changed'))
}

export default function NotificationsPage() {
  useLanguage()
  const navigate = useNavigate()
  const [notifications, setNotifications] = React.useState([])
  const [summary, setSummary] = React.useState({ unread: 0, total: 0, unread_by_category: {} })
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [status, setStatus] = React.useState('all')
  const [category, setCategory] = React.useState('all')
  const [search, setSearch] = React.useState('')
  const [pagination, setPagination] = React.useState({ current: 1, pageSize: 20, total: 0 })
  const appliedFilters = React.useRef({status: 'all', category: 'all', q: '', page: 1, page_size: 20})
  const requestVersion = React.useRef(0)
  const foregroundLoading = React.useRef(false)

  const load = React.useCallback(async (filters = {}) => {
    const version = ++requestVersion.current
    foregroundLoading.current = true
    setLoading(true); setError('')
    try {
      appliedFilters.current = { ...appliedFilters.current, status, category, q: search, ...filters }
      const response = await api.get('/notifications', { params: appliedFilters.current })
      if (version !== requestVersion.current) return
      setNotifications(response.data.notifications); setSummary(response.data.summary)
      setPagination({current: response.data.page, pageSize: response.data.page_size, total: response.data.total})
      appliedFilters.current.page = response.data.page
    } catch (requestError) { if (version === requestVersion.current) setError(apiMessage(requestError)) }
    finally { if (version === requestVersion.current) { setLoading(false); foregroundLoading.current = false } }
  }, [category, search, status])

  React.useEffect(() => {
    let active = true
    const version = ++requestVersion.current
    foregroundLoading.current = true
    api.get('/notifications').then((response) => {
      if (!active || version !== requestVersion.current) return
      setNotifications(response.data.notifications); setSummary(response.data.summary)
      setPagination({current: response.data.page, pageSize: response.data.page_size, total: response.data.total})
    }).catch((requestError) => { if (active && version === requestVersion.current) setError(apiMessage(requestError)) })
      .finally(() => { if (active && version === requestVersion.current) { setLoading(false); foregroundLoading.current = false } })
    return () => { active = false }
  }, [])

  React.useEffect(() => {
    let active = true
    let pending = false
    const refresh = async () => {
      if (pending || foregroundLoading.current || document.visibilityState === 'hidden') return
      pending = true
      const version = ++requestVersion.current
      try {
        const { data } = await api.get('/notifications', { params: appliedFilters.current })
        if (active && version === requestVersion.current) { setNotifications(data.notifications); setSummary(data.summary); setPagination({current: data.page, pageSize: data.page_size, total: data.total}); appliedFilters.current.page = data.page; setError('') }
      } catch (requestError) { if (active && version === requestVersion.current) setError(apiMessage(requestError)) }
      finally { pending = false }
    }
    const timer = window.setInterval(refresh, 30000)
    window.addEventListener('notifications:changed', refresh)
    window.addEventListener('community:changed', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('notifications:changed', refresh); window.removeEventListener('community:changed', refresh); document.removeEventListener('visibilitychange', refresh) }
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
      message.success(t(category === 'all' ? 'All notifications marked as read.' : 'Visible category marked as read.'))
      await load(); notifyHeaderChanged()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function clearNotification(notificationId) {
    try {
      await api.delete(`/notifications/${notificationId}`)
      message.success(t('Notification cleared.')); await load(); notifyHeaderChanged()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function savePreferences(values) {
    try {const response = await api.put('/notifications/preferences', {muted_categories: values}); setSummary(response.data.summary); notifyHeaderChanged(); message.success(t('Badge preferences saved.'))}
    catch(error) {message.error(apiMessage(error))}
  }

  function resetFilters() {
    setStatus('all'); setCategory('all'); setSearch(''); load({ status: 'all', category: 'all', q: '', page: 1 })
  }

  return <div className="page-stack notifications-page">
    <div className="page-heading"><div><Title level={1}>{t("消息通知")}</Title><Paragraph>{t("查看提醒与动态，点击消息回到对应功能继续处理。")}</Paragraph></div><Button icon={<CheckOutlined />} disabled={!summary.total} onClick={markAllRead}>{t("全部标为已读")}</Button></div>
    {error && <Alert type="error" showIcon message={t("通知加载失败")} description={t(error)} action={<Button onClick={() => load()}>{t("重试")}</Button>} />}
    <div className="notification-counts"><Tag color="green">{summary.unread}{t(" 条待关注")}</Tag><Text type="secondary">{(summary.unread_by_category?.health || 0) + (summary.unread_by_category?.care || 0)}{t(" 健康与服务 · ")}{(summary.unread_by_category?.security || 0) + (summary.unread_by_category?.sharing || 0)}{t(" 安全与共享")}</Text></div>
    <Card className="notification-filter-card"><div className="notification-filters"><Input allowClear prefix={<SearchOutlined />} placeholder={t("搜索通知内容或来源")} value={search} onChange={(event) => setSearch(event.target.value)} onPressEnter={() => load({page: 1})} /><Select value={status} onChange={setStatus} options={[{ value: 'all', label: t('所有状态') }, { value: 'unread', label: t('未读') }, { value: 'read', label: t('已读') }, {value: 'resolved', label: t('已处理事件')}]} /><Select value={category} onChange={setCategory} options={[{ value: 'all', label: t('所有类别') }, ...Object.entries(categoryConfig).map(([value, config]) => ({ value, label: config.label }))]} /><Button type="primary" onClick={() => load({page: 1})}>{t("筛选")}</Button><Button onClick={resetFilters}>{t("重置")}</Button></div></Card>
    {loading ? <Card><Skeleton active paragraph={{ rows: 9 }} /></Card> : notifications.length === 0 ? <Card><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("暂无符合条件的通知")} /></Card> : <List pagination={{...pagination, responsive: true, showLessItems: true, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], showTotal: (total) => t('{count} notifications', { count: total }), onChange: (page, pageSize) => load({page: pageSize === pagination.pageSize ? page : 1, page_size: pageSize})}} className="notification-list" dataSource={notifications} renderItem={(notification) => {
      const config = categoryConfig[notification.category] || categoryConfig.system
      return <List.Item style={{flexWrap: 'wrap', gap: 12}} styles={{actions: {display: 'flex', flexWrap: 'wrap', gap: 4, marginInlineStart: 0, maxWidth: '100%'}}} className={notification.unread ? 'unread' : ''} actions={[<Button key="read" type="text" icon={notification.unread ? <CheckOutlined /> : <EyeOutlined />} onClick={() => setRead(notification, notification.unread)}>{notification.unread ? t('标为已读') : t('标为未读')}</Button>, notification.action_path && <Button key="open" type="link" onClick={() => openNotification(notification)}>{t("查看详情")}</Button>, <Popconfirm key="clear" title={t("清除此通知？")} description={t("这条通知将从列表移除，不会删除相关健康资料。")} onConfirm={() => clearNotification(notification.id)}><Button type="text" danger icon={<ClearOutlined />}>{t("清除")}</Button></Popconfirm>].filter(Boolean)}><List.Item.Meta avatar={<Badge dot={notification.unread}><div className={`notification-icon ${notification.severity}`}>{config.icon}</div></Badge>} title={<Space wrap><Text strong>{t(notification.title)}</Text><Tag color={config.color}>{config.label}</Tag>{notification.resolved && <Tag color="green">{t("事件已处理")}</Tag>}{notification.severity === 'urgent' && !notification.resolved && <Tag color="red" icon={<ExclamationCircleOutlined />}>{t("待关注")}</Tag>}</Space>} description={<div className="notification-detail"><Text>{t(notification.message)}</Text><span>{dayjs(notification.created_at).format('D MMM YYYY · HH:mm')}{t(" · Source: ")}{t(notification.source_name)}</span></div>} /></List.Item>
    }} />}
    <Card title={t("未读提醒偏好")}><Paragraph type="secondary">{t("选择不计入顶部未读数字的类别，消息仍保留在这里。健康、安全和系统消息始终计入；已处理事件不再计数。")}</Paragraph><Checkbox.Group value={summary.muted_categories || []} options={[{value: 'care', label: t('免打扰：服务')}, {value: 'sharing', label: t('免打扰：共享')}, {value: 'community', label: t('免打扰：社区')}]} onChange={savePreferences} /></Card>
    <Guidance id="notifications-delivery" title={t("通知送达方式")}>{t("目前使用站内通知，邮件、短信和设备推送尚未连接。")}</Guidance>
  </div>
}
