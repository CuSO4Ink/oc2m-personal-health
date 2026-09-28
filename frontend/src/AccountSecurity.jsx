import { t, useLanguage } from './i18n'
import React from 'react'
import { CheckCircleOutlined, ClockCircleOutlined, DesktopOutlined, EditOutlined, ExclamationCircleOutlined, KeyOutlined, LockOutlined, LogoutOutlined, MailOutlined, MobileOutlined, SafetyCertificateOutlined, ScanOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Avatar, Button, Card, DatePicker, Descriptions, Empty, Form, Input, List, Modal, Popconfirm, Progress, Skeleton, Space, Statistic, Switch, Tabs, Tag, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import Guidance from './Guidance'
import DemoResetPanel from './DemoResetPanel'
import { useAuth } from './auth'

const { Title, Paragraph, Text } = Typography

function formatDate(value) {
  return value ? dayjs(value).format('D MMM YYYY · HH:mm') : t('Not available')
}

function eventLabel(type) {
  return type.split('_').map((part) => part[0].toUpperCase() + part.slice(1)).join(' ')
}

export default function AccountSecurityPage() {
  const { language } = useLanguage()
  const navigate = useNavigate()
  const { refresh } = useAuth()
  const [account, setAccount] = React.useState(null)
  const [sessions, setSessions] = React.useState([])
  const [events, setEvents] = React.useState([])
  const [eventPage, setEventPage] = React.useState(1)
  const [eventTotal, setEventTotal] = React.useState(0)
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [communitySaving, setCommunitySaving] = React.useState(false)
  const [error, setError] = React.useState('')
  const [emailCode, setEmailCode] = React.useState(null)
  const [emailOpen, setEmailOpen] = React.useState(false)
  const [passwordOpen, setPasswordOpen] = React.useState(false)
  const [profileForm] = Form.useForm()
  const [emailForm] = Form.useForm()
  const [passwordForm] = Form.useForm()

  const applyAccount = React.useCallback((data) => {
    setAccount(data)
    profileForm.setFieldsValue({
      full_name: data.user.full_name,
      phone: data.profile.phone,
      date_of_birth: data.profile.date_of_birth ? dayjs(data.profile.date_of_birth) : null,
    })
  }, [profileForm])

  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [accountResponse, sessionsResponse, eventsResponse] = await Promise.all([
        api.get('/account'), api.get('/account/sessions'), api.get('/account/security-events', { params: { page: eventPage, page_size: 20 } }),
      ])
      applyAccount(accountResponse.data); setSessions(sessionsResponse.data.sessions); setEvents(eventsResponse.data.events); setEventTotal(eventsResponse.data.total)
    } catch (requestError) { setError(apiMessage(requestError)) }
    finally { setLoading(false) }
  }, [applyAccount, eventPage])

  React.useEffect(() => {
    let active = true
    Promise.all([api.get('/account'), api.get('/account/sessions'), api.get('/account/security-events', { params: { page: eventPage, page_size: 20 } })]).then(([accountResponse, sessionsResponse, eventsResponse]) => {
      if (!active) return
      applyAccount(accountResponse.data); setSessions(sessionsResponse.data.sessions); setEvents(eventsResponse.data.events); setEventTotal(eventsResponse.data.total)
    }).catch((requestError) => { if (active) setError(apiMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [applyAccount, eventPage])

  async function saveProfile(values) {
    setSaving(true)
    try {
      const response = await api.patch('/account/profile', { ...values, date_of_birth: values.date_of_birth?.format('YYYY-MM-DD') || null })
      applyAccount(response.data); await refresh(); message.success(t('Profile updated.'))
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function changeCommunity(enabled) {
    setCommunitySaving(true)
    try {
      await api.patch('/community/profile', { enabled })
      setAccount((current) => ({ ...current, community_enabled: enabled }))
      window.dispatchEvent(new Event('community:changed'))
      message.success(t(enabled ? 'Community enabled. Choose a nickname before making friends.' : 'Community is off. Community notifications are silenced.'))
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setCommunitySaving(false) }
  }

  function openEmailChange() {
    setEmailCode(null); emailForm.resetFields(); emailForm.setFieldsValue({ email: account.user.email }); setEmailOpen(true)
  }

  async function requestEmailCode() {
    try {const values = await emailForm.validateFields(['email', 'current_password']); const response = await api.post('/account/email-change/request', values); setEmailCode(response.data.demo_code); message.info(t(response.data.message))}
    catch(error) {if(error.response) message.error(apiMessage(error))}
  }

  async function changeEmail(values) {
    setSaving(true)
    try {
      const response = await api.post('/account/change-email', values)
      applyAccount(response.data); await refresh(); setEmailOpen(false); message.success(t('Sign-in email changed.'))
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  function openPasswordChange() { passwordForm.resetFields(); setPasswordOpen(true) }

  async function changePassword(values) {
    setSaving(true)
    try {
      await api.post('/account/change-password', { current_password: values.current_password, new_password: values.new_password })
      setPasswordOpen(false); message.success(t('Password changed. Other sessions were signed out.')); await load()
      window.dispatchEvent(new Event('notifications:changed'))
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function revokeSession(sessionId) {
    try { await api.delete(`/account/sessions/${sessionId}`); message.success(t('Session signed out.')); await load() }
    catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function revokeOthers() {
    try {
      const response = await api.post('/account/sessions/revoke-others')
      message.success(t(response.data.message)); await load(); window.dispatchEvent(new Event('notifications:changed'))
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function finishDemoReset() {
    try {
      Object.keys(localStorage).filter(key => key.startsWith(`health-help:${account.user.id}:`) || key.startsWith(`personal-health:setup:${account.user.id}:`)).forEach(key => localStorage.removeItem(key))
    } catch { /* Reset does not depend on optional browser storage. */ }
    window.dispatchEvent(new Event('health-help:reset'))
    await refresh()
    navigate('/overview', { replace: true })
  }

  if (loading) return <div className="page-stack account-page"><Card><Skeleton active paragraph={{ rows: 12 }} /></Card></div>
  if (!account) return <div className="page-stack account-page"><div className="page-heading"><div><Title level={1}>{t("账户与安全")}</Title><Paragraph>{t("管理登录方式、安全记录和登录设备。基础健康信息也可以在健康资料中编辑。")}</Paragraph></div></div><Alert type="error" showIcon message={t("Account information could not be loaded")} description={t(error || 'Please try again.')} action={<Button onClick={load}>{t("重试")}</Button>} /></div>

  const profilePanel = <div className="account-panel"><Card title={t("基础资料")} extra={<Text type="secondary">{t("资料完整度： ")}{account.profile_completeness}%</Text>}><Progress percent={account.profile_completeness} showInfo={false} strokeColor="#397f78" /><Form className="account-form" form={profileForm} layout="vertical" onFinish={saveProfile}><div className="form-grid"><Form.Item label={t("姓名")} name="full_name" rules={[{ required: true, min: 2, max: 100, message: t('Enter your full name') }]}><Input prefix={<UserOutlined />} /></Form.Item><Form.Item label={t("登录邮箱")}><Input prefix={<MailOutlined />} value={account.user.email} disabled /></Form.Item><Form.Item label={t("联系电话")} name="phone" extra={t("仅作为联系信息保存，尚未验证号码归属。")}><Input prefix={<MobileOutlined />} placeholder={t("填写联系电话")} maxLength={40} /></Form.Item><Form.Item label={t("出生日期")} name="date_of_birth"><DatePicker className="full-width" disabledDate={(date) => date && date >= dayjs().startOf('day')} /></Form.Item><Form.Item label={t("界面语言")}><Text>{language === 'zh' ? '简体中文' : 'English'}</Text></Form.Item></div><div className="form-actions"><Button icon={<EditOutlined />} onClick={openEmailChange}>{t("修改登录邮箱")}</Button><Button type="primary" htmlType="submit" loading={saving}>{t("保存基础资料")}</Button></div></Form></Card><Card title={t("病友交流设置")}><Space wrap><Switch aria-label={t("Enable community")} checked={account.community_enabled} loading={communitySaving} onChange={changeCommunity} /><Text>{t("社区、好友与私聊")}</Text>{account.community_enabled && <Button onClick={() => navigate('/community')}>{t("进入病友交流")}</Button>}</Space><Paragraph type="secondary">{t("可按需开启。关闭后隐藏社区入口并停止社交通知；健康资料不会自动分享给好友。")}</Paragraph></Card><Card size="small"><Space wrap><Text>{t("要查看病史、用药或过敏情况？")}</Text><Button onClick={() => navigate('/profile')}>{t("前往个人健康信息")}</Button></Space></Card></div>

  const securityPanel = <div className="account-panel"><div className="security-method-grid">{account.sign_in_methods.filter((method) => method.status === 'active').map((method) => <Card key={method.key} className="security-method-card"><div className={`method-icon ${method.status}`}>{method.key === 'password' ? <KeyOutlined /> : method.key === 'sms' ? <MobileOutlined /> : <ScanOutlined />}</div><Space><Title level={4}>{t(method.name)}</Title><Tag color={method.status === 'active' ? 'green' : 'gold'}>{method.status === 'active' ? t('Active') : t('Planned')}</Tag></Space><Paragraph>{t(method.description)}</Paragraph>{method.key === 'password' ? <Button type="primary" onClick={openPasswordChange}>{t("修改密码")}</Button> : <Button disabled>{t("Set up later")}</Button>}</Card>)}</div><Card title={t("登录设备")} extra={<Popconfirm title={t("Sign out all other sessions?")} description={t("The current browser will stay signed in.")} onConfirm={revokeOthers}><Button icon={<LogoutOutlined />} disabled={sessions.length <= 1}>{t("退出其他设备")}</Button></Popconfirm>}>{sessions.length === 0 ? <Empty description={t("No active sessions")} /> : <List dataSource={sessions} renderItem={(item) => <List.Item actions={item.current ? [] : [<Popconfirm key="revoke" title={t("Sign out this session?")} onConfirm={() => revokeSession(item.id)}><Button danger>{t("Sign out")}</Button></Popconfirm>]}><List.Item.Meta avatar={<Avatar icon={<DesktopOutlined />} />} title={<Space><Text strong>{item.device_name}</Text>{item.current && <Tag color="green">{t("当前设备")}</Tag>}</Space>} description={<div className="session-detail"><span>{t("IP address: ")}{item.ip_address}</span><span>{t("Last active: ")}{formatDate(item.last_seen_at)}</span><span>{t("Expires: ")}{formatDate(item.expires_at)}</span></div>} /></List.Item>} />}</Card><Guidance id="account-recovery" title={t("Account recovery options")}>{t(account.protection.recovery_mode)}</Guidance></div>

  const activityPanel = <div className="account-panel"><div className="section-heading"><div><Title level={3}>{t("账户安全记录")}</Title><Paragraph>{t("Review sign-ins, password changes and session actions for this account.")}</Paragraph></div></div>{events.length === 0 ? <Card><Empty description={t("No security activity recorded yet")} /></Card> : <List pagination={{ current: eventPage, total: eventTotal, pageSize: 20, showSizeChanger: false, onChange: setEventPage }} className="security-event-list" dataSource={events} renderItem={(event) => <List.Item><List.Item.Meta avatar={<div className={`security-event-icon ${event.result}`}>{event.result === 'success' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}</div>} title={<Space wrap><Text strong>{t(eventLabel(event.event_type))}</Text><Tag color={event.result === 'success' ? 'green' : 'red'}>{t(event.result)}</Tag>{event.important && <Tag color="orange">{t("Security relevant")}</Tag>}</Space>} description={<div className="event-description"><Text>{t(event.description)}</Text><span><ClockCircleOutlined /> {formatDate(event.created_at)} · {event.device_name}{t(" · IP ")}{event.ip_address}</span></div>} /></List.Item>} />}</div>

  return <div className="page-stack account-page"><div className="page-heading"><div><Title level={1}>{t("账户与安全")}</Title><Paragraph>{t("管理登录方式、安全记录和登录设备。基础健康信息也可以在健康资料中编辑。")}</Paragraph></div></div>{error && <Alert type="error" showIcon message={t("Account information could not be loaded")} description={t(error)} action={<Button onClick={load}>{t("重试")}</Button>} />}{account && <><div className="account-summary"><Card className="identity-card"><Avatar size={64}>{account.user.initials}</Avatar><div><Title level={3}>{account.user.full_name}</Title><Text>{account.user.email}</Text><Text type="secondary">{t("个人健康账户")}</Text></div></Card><Card><Statistic title={t("登录设备")} value={sessions.length} prefix={<DesktopOutlined />} /></Card><Card><Statistic title={t("安全事件")} value={eventTotal} prefix={<SafetyCertificateOutlined />} /></Card></div><Tabs defaultActiveKey="profile" items={[{ key: 'profile', label: t('资料与偏好'), children: profilePanel }, { key: 'security', label: t('登录与设备'), children: securityPanel }, { key: 'activity', label: t('安全记录'), children: activityPanel }]} /></>}

    <DemoResetPanel accountEmail={account.user.email} onReset={finishDemoReset} />
    <Guidance id="login-protection" title={t("How your sign-in is protected")}>{t(account.protection.login_limit)}{t(". Remembered logins are tied to revocable server sessions.")}</Guidance>
    <Modal title={t("修改登录邮箱")} open={emailOpen} onCancel={() => setEmailOpen(false)} footer={null} destroyOnHidden><Alert type="warning" showIcon message={t("Your email is used to sign in and recover your account")} /><Form className="account-modal-form" form={emailForm} layout="vertical" onFinish={changeEmail}><Form.Item label={t("New email address")} name="email" rules={[{ required: true, type: 'email', message: t('Enter a valid email address') }]}><Input autoComplete="email" /></Form.Item><Form.Item label={t("当前密码")} name="current_password" rules={[{ required: true, message: t('Enter your current password') }]}><Input.Password autoComplete="current-password" /></Form.Item><Form.Item label={t("Verification code")} name="code" rules={[{required: true, message: t('Request and enter the verification code')}]}><Input maxLength={6} /></Form.Item>{emailCode && <Alert type="warning" message={t('Demo verification code: {code}', { code: emailCode })} description={t("No email was sent. This tests the workflow and does not prove mailbox ownership.")} />}<div className="form-actions"><Button onClick={() => setEmailOpen(false)}>{t("取消")}</Button><Button onClick={requestEmailCode}>{t("Request code")}</Button><Button type="primary" htmlType="submit" loading={saving}>{t("Confirm Email Change")}</Button></div></Form></Modal>

    <Modal title={t("修改密码")} open={passwordOpen} onCancel={() => setPasswordOpen(false)} footer={null} destroyOnHidden><Alert type="info" showIcon icon={<LockOutlined />} message={t("Other active sessions will be signed out")} /><Form className="account-modal-form" form={passwordForm} layout="vertical" onFinish={changePassword}><Form.Item label={t("当前密码")} name="current_password" rules={[{ required: true, message: t('Enter your current password') }]}><Input.Password autoComplete="current-password" /></Form.Item><Form.Item label={t("新密码")} name="new_password" extra={t("至少 8 位，包含字母和数字。")} rules={[{ required: true, min: 8, message: t('Use at least 8 characters') }]}><Input.Password autoComplete="new-password" /></Form.Item><Form.Item label={t("再次输入新密码")} name="confirm_password" dependencies={['new_password']} rules={[{ required: true, message: t('Confirm your new password') }, ({ getFieldValue }) => ({ validator: (_, value) => !value || getFieldValue('new_password') === value ? Promise.resolve() : Promise.reject(new Error(t('Passwords do not match'))) })]}><Input.Password autoComplete="new-password" /></Form.Item><div className="form-actions"><Button onClick={() => setPasswordOpen(false)}>{t("取消")}</Button><Button type="primary" htmlType="submit" loading={saving}>{t("修改密码")}</Button></div></Form></Modal>
  </div>
}
