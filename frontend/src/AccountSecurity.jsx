import React from 'react'
import { CheckCircleOutlined, ClockCircleOutlined, DesktopOutlined, EditOutlined, ExclamationCircleOutlined, KeyOutlined, LockOutlined, LogoutOutlined, MailOutlined, MobileOutlined, SafetyCertificateOutlined, ScanOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Avatar, Button, Card, DatePicker, Descriptions, Empty, Form, Input, List, Modal, Popconfirm, Progress, Select, Skeleton, Space, Statistic, Tabs, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import { useAuth } from './auth'

const { Title, Paragraph, Text } = Typography

function formatDate(value) {
  return value ? dayjs(value).format('D MMM YYYY · HH:mm') : 'Not available'
}

function eventLabel(type) {
  return type.split('_').map((part) => part[0].toUpperCase() + part.slice(1)).join(' ')
}

export default function AccountSecurityPage() {
  const { refresh } = useAuth()
  const [account, setAccount] = React.useState(null)
  const [sessions, setSessions] = React.useState([])
  const [events, setEvents] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
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
      preferred_language: data.profile.preferred_language,
    })
  }, [profileForm])

  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [accountResponse, sessionsResponse, eventsResponse] = await Promise.all([
        api.get('/account'), api.get('/account/sessions'), api.get('/account/security-events'),
      ])
      applyAccount(accountResponse.data); setSessions(sessionsResponse.data.sessions); setEvents(eventsResponse.data.events)
    } catch (requestError) { setError(apiMessage(requestError)) }
    finally { setLoading(false) }
  }, [applyAccount])

  React.useEffect(() => {
    let active = true
    Promise.all([api.get('/account'), api.get('/account/sessions'), api.get('/account/security-events')]).then(([accountResponse, sessionsResponse, eventsResponse]) => {
      if (!active) return
      applyAccount(accountResponse.data); setSessions(sessionsResponse.data.sessions); setEvents(eventsResponse.data.events)
    }).catch((requestError) => { if (active) setError(apiMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [applyAccount])

  async function saveProfile(values) {
    setSaving(true)
    try {
      const response = await api.patch('/account/profile', { ...values, date_of_birth: values.date_of_birth?.format('YYYY-MM-DD') || null })
      applyAccount(response.data); await refresh(); message.success('Profile updated.')
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  function openEmailChange() {
    setEmailCode(null); emailForm.resetFields(); emailForm.setFieldsValue({ email: account.user.email }); setEmailOpen(true)
  }

  async function requestEmailCode() {
    try {const values = await emailForm.validateFields(['email', 'current_password']); const response = await api.post('/account/email-change/request', values); setEmailCode(response.data.demo_code); message.info(response.data.message)}
    catch(error) {if(error.response) message.error(apiMessage(error))}
  }

  async function changeEmail(values) {
    setSaving(true)
    try {
      const response = await api.post('/account/change-email', values)
      applyAccount(response.data); await refresh(); setEmailOpen(false); message.success('Sign-in email changed.')
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  function openPasswordChange() { passwordForm.resetFields(); setPasswordOpen(true) }

  async function changePassword(values) {
    setSaving(true)
    try {
      await api.post('/account/change-password', { current_password: values.current_password, new_password: values.new_password })
      setPasswordOpen(false); message.success('Password changed. Other sessions were signed out.'); await load()
      window.dispatchEvent(new Event('notifications:changed'))
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSaving(false) }
  }

  async function revokeSession(sessionId) {
    try { await api.delete(`/account/sessions/${sessionId}`); message.success('Session signed out.'); await load() }
    catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function revokeOthers() {
    try {
      const response = await api.post('/account/sessions/revoke-others')
      message.success(response.data.message); await load(); window.dispatchEvent(new Event('notifications:changed'))
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  if (loading) return <div className="page-stack account-page"><Card><Skeleton active paragraph={{ rows: 12 }} /></Card></div>
  if (!account) return <div className="page-stack account-page"><div className="page-heading"><div><Title level={1}>Account & Security</Title><Paragraph>Manage your identity, sign-in protection and active sessions.</Paragraph></div></div><Alert type="error" showIcon message="Account information could not be loaded" description={error || 'Please try again.'} action={<Button onClick={load}>Try again</Button>} /></div>

  const profilePanel = <div className="account-panel"><Card title="Personal details" extra={<Text type="secondary">Profile completion: {account.profile_completeness}%</Text>}><Progress percent={account.profile_completeness} showInfo={false} strokeColor="#397f78" /><Form className="account-form" form={profileForm} layout="vertical" onFinish={saveProfile}><div className="form-grid"><Form.Item label="Full name" name="full_name" rules={[{ required: true, min: 2, max: 100, message: 'Enter your full name' }]}><Input prefix={<UserOutlined />} /></Form.Item><Form.Item label="Sign-in email"><Input prefix={<MailOutlined />} value={account.user.email} disabled /></Form.Item><Form.Item label="Phone number" name="phone" extra="Stored contact only; phone ownership is not verified."><Input prefix={<MobileOutlined />} placeholder="Add a phone number" maxLength={40} /></Form.Item><Form.Item label="Date of birth" name="date_of_birth"><DatePicker className="full-width" disabledDate={(date) => date && date >= dayjs().startOf('day')} /></Form.Item><Form.Item label="Preferred language" name="preferred_language"><Select options={[{ value: 'English', label: 'English' }, { value: '简体中文', label: '简体中文' }, { value: '繁體中文', label: '繁體中文' }]} /></Form.Item></div><div className="form-actions"><Button icon={<EditOutlined />} onClick={openEmailChange}>Change sign-in email</Button><Button type="primary" htmlType="submit" loading={saving}>Save Profile</Button></div></Form></Card><Alert type="info" showIcon message="Health details belong in Health Records" description="This page stores account contact and display information. Medical history, allergies and medicines remain in the protected Health Records module." /></div>

  const securityPanel = <div className="account-panel"><div className="security-method-grid">{account.sign_in_methods.map((method) => <Card key={method.key} className="security-method-card"><div className={`method-icon ${method.status}`}>{method.key === 'password' ? <KeyOutlined /> : method.key === 'sms' ? <MobileOutlined /> : <ScanOutlined />}</div><Space><Title level={4}>{method.name}</Title><Tag color={method.status === 'active' ? 'green' : 'gold'}>{method.status === 'active' ? 'Active' : 'Planned'}</Tag></Space><Paragraph>{method.description}</Paragraph>{method.key === 'password' ? <Button type="primary" onClick={openPasswordChange}>Change Password</Button> : <Button disabled>Set up later</Button>}</Card>)}</div><Card title="Active sessions" extra={<Popconfirm title="Sign out all other sessions?" description="The current browser will stay signed in." onConfirm={revokeOthers}><Button icon={<LogoutOutlined />} disabled={sessions.length <= 1}>Sign out other sessions</Button></Popconfirm>}>{sessions.length === 0 ? <Empty description="No active sessions" /> : <List dataSource={sessions} renderItem={(item) => <List.Item actions={item.current ? [] : [<Popconfirm key="revoke" title="Sign out this session?" onConfirm={() => revokeSession(item.id)}><Button danger>Sign out</Button></Popconfirm>]}><List.Item.Meta avatar={<Avatar icon={<DesktopOutlined />} />} title={<Space><Text strong>{item.device_name}</Text>{item.current && <Tag color="green">This device</Tag>}</Space>} description={<div className="session-detail"><span>IP address: {item.ip_address}</span><span>Last active: {formatDate(item.last_seen_at)}</span><span>Expires: {formatDate(item.expires_at)}</span></div>} /></List.Item>} />}</Card><Alert type="warning" showIcon message="Recovery uses development code preview" description={account.protection.recovery_mode} /></div>

  const activityPanel = <div className="account-panel"><div className="section-heading"><div><Title level={3}>Account security activity</Title><Paragraph>Review sign-ins, password changes and session actions for this account.</Paragraph></div></div>{events.length === 0 ? <Card><Empty description="No security activity recorded yet" /></Card> : <List className="security-event-list" dataSource={events} renderItem={(event) => <List.Item><List.Item.Meta avatar={<div className={`security-event-icon ${event.result}`}>{event.result === 'success' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}</div>} title={<Space wrap><Text strong>{eventLabel(event.event_type)}</Text><Tag color={event.result === 'success' ? 'green' : 'red'}>{event.result}</Tag>{event.important && <Tag color="orange">Security relevant</Tag>}</Space>} description={<div className="event-description"><Text>{event.description}</Text><span><ClockCircleOutlined /> {formatDate(event.created_at)} · {event.device_name} · IP {event.ip_address}</span></div>} /></List.Item>} />}</div>

  return <div className="page-stack account-page"><div className="page-heading"><div><Title level={1}>Account & Security</Title><Paragraph>Manage your identity, sign-in protection and active sessions.</Paragraph></div></div>{error && <Alert type="error" showIcon message="Account information could not be loaded" description={error} action={<Button onClick={load}>Try again</Button>} />}{account && <><div className="account-summary"><Card className="identity-card"><Avatar size={64}>{account.user.initials}</Avatar><div><Title level={3}>{account.user.full_name}</Title><Text>{account.user.email}</Text><Text type="secondary">Personal health account</Text></div></Card><Card><Statistic title="Active sessions" value={sessions.length} prefix={<DesktopOutlined />} /></Card><Card><Statistic title="Security events" value={events.length} prefix={<SafetyCertificateOutlined />} /></Card></div><Tabs defaultActiveKey="profile" items={[{ key: 'profile', label: 'Profile', children: profilePanel }, { key: 'security', label: 'Sign-in & Sessions', children: securityPanel }, { key: 'activity', label: 'Security Activity', children: activityPanel }]} /></>}

    <Alert type="info" showIcon message="Login protection" description={`${account.protection.login_limit}. Remembered logins are tied to revocable server sessions.`} />
    <Modal title="Change sign-in email" open={emailOpen} onCancel={() => setEmailOpen(false)} footer={null} destroyOnHidden><Alert type="warning" showIcon message="Your email is used to sign in and recover your account" /><Form className="account-modal-form" form={emailForm} layout="vertical" onFinish={changeEmail}><Form.Item label="New email address" name="email" rules={[{ required: true, type: 'email', message: 'Enter a valid email address' }]}><Input autoComplete="email" /></Form.Item><Form.Item label="Current password" name="current_password" rules={[{ required: true, message: 'Enter your current password' }]}><Input.Password autoComplete="current-password" /></Form.Item><Form.Item label="Verification code" name="code" rules={[{required: true, message: 'Request and enter the verification code'}]}><Input maxLength={6} /></Form.Item>{emailCode && <Alert type="warning" message={`Development code: ${emailCode}`} description="No email was sent. This tests the workflow and does not prove mailbox ownership." />}<div className="form-actions"><Button onClick={() => setEmailOpen(false)}>Cancel</Button><Button onClick={requestEmailCode}>Request code</Button><Button type="primary" htmlType="submit" loading={saving}>Confirm Email Change</Button></div></Form></Modal>

    <Modal title="Change password" open={passwordOpen} onCancel={() => setPasswordOpen(false)} footer={null} destroyOnHidden><Alert type="info" showIcon icon={<LockOutlined />} message="Other active sessions will be signed out" /><Form className="account-modal-form" form={passwordForm} layout="vertical" onFinish={changePassword}><Form.Item label="Current password" name="current_password" rules={[{ required: true, message: 'Enter your current password' }]}><Input.Password autoComplete="current-password" /></Form.Item><Form.Item label="New password" name="new_password" extra="Use at least 8 characters with a letter and a number." rules={[{ required: true, min: 8, message: 'Use at least 8 characters' }]}><Input.Password autoComplete="new-password" /></Form.Item><Form.Item label="Confirm new password" name="confirm_password" dependencies={['new_password']} rules={[{ required: true, message: 'Confirm your new password' }, ({ getFieldValue }) => ({ validator: (_, value) => !value || getFieldValue('new_password') === value ? Promise.resolve() : Promise.reject(new Error('Passwords do not match')) })]}><Input.Password autoComplete="new-password" /></Form.Item><div className="form-actions"><Button onClick={() => setPasswordOpen(false)}>Cancel</Button><Button type="primary" htmlType="submit" loading={saving}>Change Password</Button></div></Form></Modal>
  </div>
}
