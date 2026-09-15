import React from 'react'
import { BellOutlined, CalendarOutlined, DownOutlined, LoadingOutlined, PlusOutlined } from '@ant-design/icons'
import { Alert, Avatar, Badge, Button, Card, Checkbox, Divider, Dropdown, Form, Input, Layout, Menu, Space, Spin, Tag, Typography } from 'antd'
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import api, { apiMessage } from './api'
import { AuthProvider, useAuth } from './auth'
import { RecordDetailPage, RecordFormPage, RecordHistoryPage, RecordsPage } from './HealthRecords'
import HealthInsightsPage from './HealthInsights'
import SharingPrivacyPage from './SharingPrivacy'
import CareServicesPage from './CareServices'
import CommunityPage from './Community'
import NotificationsPage from './Notifications'

const { Content, Header, Sider } = Layout
const { Title, Text, Paragraph, Link } = Typography

const navItems = [
  { key: '/overview', label: 'Overview' },
  { key: '/records', label: 'Health Records' },
  { key: '/insights', label: 'Health Insights' },
  { key: '/sharing', label: 'Sharing & Privacy' },
  { key: '/services', label: 'Care Services' },
  { key: '/community', label: 'Community' },
]

const plannedPages = {
  '/account': ['Account & Security', 'Manage your profile and sign-in methods.'],
}

function Brand() {
  return <div className="brand"><span className="brand-mark">PH</span><strong>Personal Health</strong></div>
}

function AuthLayout({ children }) {
  return <main className="login-page">
    <section className="login-intro"><div className="intro-content"><Brand /><h1>Your health,<br />in one place.</h1><p>Manage your records, understand your health, and control what you share.</p></div></section>
    <section className="login-form-wrap"><div className="login-form-card">{children}</div></section>
  </main>
}

function LoginPage() {
  const navigate = useNavigate()
  const { login, user } = useAuth()
  const [error, setError] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  if (user) return <Navigate to="/overview" replace />

  async function submit(values) {
    setSubmitting(true)
    setError('')
    try {
      await login(values)
      navigate('/overview', { replace: true })
    } catch (requestError) {
      setError(apiMessage(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  return <AuthLayout>
    <Title level={2}>Welcome back</Title><Paragraph>Sign in to access your personal health records.</Paragraph>
    {error && <Alert className="form-alert" type="error" showIcon message={error} />}
    <Form layout="vertical" onFinish={submit} initialValues={{ remember: true }}>
      <Form.Item label="Email address" name="email" rules={[{ required: true, type: 'email', message: 'Enter a valid email address' }]}><Input autoComplete="email" placeholder="Enter your email address" /></Form.Item>
      <Form.Item label="Password" name="password" rules={[{ required: true, message: 'Enter your password' }]}><Input.Password autoComplete="current-password" placeholder="Enter your password" /></Form.Item>
      <div className="login-options"><Form.Item name="remember" valuePropName="checked" noStyle><Checkbox>Keep me signed in</Checkbox></Form.Item><Link onClick={() => navigate('/forgot-password')}>Forgot password?</Link></div>
      <Button type="primary" htmlType="submit" block loading={submitting}>Sign In</Button>
    </Form>
    <div className="alternative-login"><Text type="secondary">Other sign-in methods</Text><Button disabled>SMS Code</Button><Button disabled>Face Verification</Button></div>
    <Divider /><div className="auth-switch"><Text>New to Personal Health?</Text><Button type="link" onClick={() => navigate('/register')}>Create account</Button></div>
  </AuthLayout>
}

function RegisterPage() {
  const navigate = useNavigate()
  const { register, user } = useAuth()
  const [error, setError] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  if (user) return <Navigate to="/overview" replace />

  async function submit(values) {
    setSubmitting(true)
    setError('')
    try {
      await register(values)
      navigate('/overview', { replace: true })
    } catch (requestError) {
      setError(apiMessage(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  return <AuthLayout>
    <Title level={2}>Create your account</Title><Paragraph>Set up a private space for your personal health information.</Paragraph>
    {error && <Alert className="form-alert" type="error" showIcon message={error} />}
    <Form layout="vertical" onFinish={submit}>
      <Form.Item label="Full name" name="full_name" rules={[{ required: true, min: 2, message: 'Enter your full name' }]}><Input autoComplete="name" /></Form.Item>
      <Form.Item label="Email address" name="email" rules={[{ required: true, type: 'email', message: 'Enter a valid email address' }]}><Input autoComplete="email" /></Form.Item>
      <Form.Item label="Password" name="password" extra="Use at least 8 characters with a letter and a number." rules={[{ required: true, min: 8, message: 'Use at least 8 characters' }]}><Input.Password autoComplete="new-password" /></Form.Item>
      <Button type="primary" htmlType="submit" block loading={submitting}>Create Account</Button>
    </Form>
    <div className="auth-switch"><Text>Already have an account?</Text><Button type="link" onClick={() => navigate('/login')}>Sign in</Button></div>
  </AuthLayout>
}

function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [email, setEmail] = React.useState('')
  const [stage, setStage] = React.useState('request')
  const [demoCode, setDemoCode] = React.useState('')
  const [notice, setNotice] = React.useState(null)
  const [submitting, setSubmitting] = React.useState(false)

  async function requestCode(values) {
    setSubmitting(true); setNotice(null)
    try {
      const response = await api.post('/auth/password-reset/request', values)
      setEmail(values.email); setDemoCode(response.data.demo_code || ''); setStage('confirm')
    } catch (requestError) {
      setNotice({ type: 'error', text: apiMessage(requestError) })
    } finally { setSubmitting(false) }
  }

  async function resetPassword(values) {
    setSubmitting(true); setNotice(null)
    try {
      await api.post('/auth/password-reset/confirm', { email, code: values.code, password: values.password })
      setStage('complete')
    } catch (requestError) {
      setNotice({ type: 'error', text: apiMessage(requestError) })
    } finally { setSubmitting(false) }
  }

  return <AuthLayout>
    {stage === 'request' && <><Title level={2}>Reset your password</Title><Paragraph>Enter the email address linked to your account.</Paragraph>{notice && <Alert className="form-alert" type={notice.type} showIcon message={notice.text} />}<Form layout="vertical" onFinish={requestCode}><Form.Item label="Email address" name="email" rules={[{ required: true, type: 'email', message: 'Enter a valid email address' }]}><Input autoComplete="email" /></Form.Item><Button type="primary" htmlType="submit" block loading={submitting}>Send Reset Code</Button></Form></>}
    {stage === 'confirm' && <><Title level={2}>Enter your reset code</Title><Paragraph>We prepared a six-digit code for <b>{email}</b>.</Paragraph>{demoCode && <Alert className="form-alert" type="info" showIcon message={`Development reset code: ${demoCode}`} description="This will be delivered by email or SMS when that service is connected." />}{notice && <Alert className="form-alert" type={notice.type} showIcon message={notice.text} />}<Form layout="vertical" onFinish={resetPassword} initialValues={{ code: demoCode }}><Form.Item label="Reset code" name="code" rules={[{ required: true, len: 6, message: 'Enter the six-digit code' }]}><Input inputMode="numeric" maxLength={6} /></Form.Item><Form.Item label="New password" name="password" extra="Use at least 8 characters with a letter and a number." rules={[{ required: true, min: 8, message: 'Use at least 8 characters' }]}><Input.Password autoComplete="new-password" /></Form.Item><Button type="primary" htmlType="submit" block loading={submitting}>Reset Password</Button></Form></>}
    {stage === 'complete' && <><Alert className="form-alert" type="success" showIcon message="Password reset complete" description="You can now sign in with your new password." /><Button type="primary" block onClick={() => navigate('/login')}>Return to Sign In</Button></>}
    {stage !== 'complete' && <Button className="back-link" type="link" onClick={() => navigate('/login')}>← Back to sign in</Button>}
  </AuthLayout>
}

function ProtectedRoute() {
  const { loading, user } = useAuth()
  if (loading) return <div className="route-loading"><Spin indicator={<LoadingOutlined spin />} size="large" /><Text>Loading your account…</Text></div>
  return user ? <Outlet /> : <Navigate to="/login" replace />
}

function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()
  const [unreadNotifications, setUnreadNotifications] = React.useState(0)
  const pageTitle = location.pathname.startsWith('/records') ? 'Health Records' : navItems.find((item) => item.key === location.pathname)?.label || plannedPages[location.pathname]?.[0] || (location.pathname === '/notifications' ? 'Notifications' : 'Overview')
  async function signOut() { await logout(); navigate('/login', { replace: true }) }
  const accountMenu = { items: [{ key: 'account', label: 'Account & Security', onClick: () => navigate('/account') }, { type: 'divider' }, { key: 'logout', label: 'Sign out', danger: true, onClick: signOut }] }

  React.useEffect(() => {
    let active = true
    const refresh = () => api.get('/notifications/summary').then(({ data }) => { if (active) setUnreadNotifications(data.summary.unread) }).catch(() => {})
    refresh()
    window.addEventListener('notifications:changed', refresh)
    return () => { active = false; window.removeEventListener('notifications:changed', refresh) }
  }, [location.pathname])

  return <Layout className="app-shell"><Sider width={260} theme="light" className="app-sider"><Brand /><Menu mode="inline" selectedKeys={[location.pathname]} items={navItems} onClick={({ key }) => navigate(key)} /></Sider><Layout><Header className="app-header"><Text>{pageTitle}</Text><Space size="large"><Badge count={unreadNotifications} size="small" overflowCount={99}><Button aria-label={`Open notifications, ${unreadNotifications} unread`} type="text" shape="circle" icon={<BellOutlined />} onClick={() => navigate('/notifications')} /></Badge><Dropdown menu={accountMenu} trigger={['click']}><button className="profile-button"><Avatar>{user.initials}</Avatar><span>{user.full_name}</span><DownOutlined /></button></Dropdown></Space></Header><Content className="app-content"><Outlet /></Content></Layout></Layout>
}

function OverviewPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const firstName = user.full_name.split(' ')[0]
  const [recentRecords, setRecentRecords] = React.useState([])
  const [latestReadings, setLatestReadings] = React.useState([])
  const [shareNotice, setShareNotice] = React.useState(null)
  const [careNotice, setCareNotice] = React.useState(null)
  React.useEffect(() => { api.get('/records').then(({ data }) => setRecentRecords(data.records.slice(0, 2))).catch(() => {}) }, [])
  React.useEffect(() => {
    Promise.all(['blood_pressure', 'blood_glucose', 'heart_rate'].map((metric) => api.get('/insights/metrics', { params: { metric, days: 365 } })))
      .then((responses) => setLatestReadings(responses.map(({ data }) => ({ ...data.latest, label: data.metric.label })).filter((item) => item.id)))
      .catch(() => {})
  }, [])
  React.useEffect(() => {
    api.get('/sharing/grants').then(({ data }) => {
      const soon = data.grants.filter((grant) => grant.status === 'active' && new Date(grant.expires_at).getTime() - Date.now() <= 7 * 86400000).sort((a, b) => new Date(a.expires_at) - new Date(b.expires_at))[0]
      setShareNotice(soon || null)
    }).catch(() => {})
  }, [])
  React.useEffect(() => {
    Promise.all([api.get('/services/appointments'), api.get('/services/reminders')]).then(([appointmentResponse, reminderResponse]) => {
      const next = appointmentResponse.data.appointments.find((appointment) => appointment.status === 'confirmed' && new Date(appointment.slot.starts_at) > new Date())
      const due = reminderResponse.data.reminders.filter((reminder) => reminder.status === 'overdue').length
      setCareNotice({ next, due })
    }).catch(() => {})
  }, [])
  return <div className="page-stack"><div className="page-heading"><div><Title level={1}>Health Overview</Title><Paragraph>Welcome back, {firstName}. Review your recent records and manage what you share.</Paragraph></div><Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/records/new')}>Add Record</Button></div>{shareNotice && <div className="warning-banner"><b>A sharing permission expires soon</b><span>{shareNotice.recipient.full_name}’s access to {shareNotice.records.length} selected records expires on {new Date(shareNotice.expires_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}. <Button type="link" onClick={() => navigate('/sharing')}>Review permission</Button></span></div>}{careNotice && (careNotice.next || careNotice.due) && <Card className="overview-care-card"><CalendarOutlined /><div><Text strong>{careNotice.next ? `Next appointment: ${careNotice.next.service.name}` : `${careNotice.due} health ${careNotice.due === 1 ? 'task is' : 'tasks are'} due`}</Text><Text>{careNotice.next ? `${new Date(careNotice.next.slot.starts_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })} · ${careNotice.next.service.facility.name}` : 'Open Care Services to review your reminders.'}</Text></div><Button onClick={() => navigate('/services')}>Open Care Services</Button></Card>}<section><Title level={3}>Latest Readings</Title><div className="reading-grid">{latestReadings.map((reading) => <Card key={reading.metric_type} className="reading-card"><Text strong>{reading.label}{reading.context === 'fasting' ? ' · Fasting' : ''}</Text><div className="reading-value">{reading.secondary_value == null ? reading.value : `${reading.value}/${reading.secondary_value}`} <small>{reading.unit}</small></div><Text type="secondary">Recorded on {new Date(reading.measured_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}</Text><Text type="secondary">Source: {reading.source_name}</Text><Button type="link" onClick={() => navigate('/insights')}>View trends →</Button></Card>)}</div></section><section><div className="section-heading"><Title level={3}>Recent Health Records</Title><Button type="link" onClick={() => navigate('/records')}>View All Records</Button></div><div className="record-grid">{recentRecords.map((record) => <Card key={record.id} hoverable onClick={() => navigate(`/records/${record.id}`)}><Tag>{record.record_type}</Tag><Title level={4}>{record.title}</Title><Text type="secondary">Record date: {new Date(`${record.record_date}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</Text></Card>)}</div></section></div>
}

function PlannedPage() {
  const { pathname } = useLocation()
  const [title, description] = plannedPages[pathname] || ['Page not found', '']
  return <div className="page-stack"><Title level={1}>{title}</Title><Paragraph>{description}</Paragraph><Card className="planned-card"><Tag color="gold">In development</Tag><Title level={3}>This module is being implemented</Title><Paragraph>The route and application structure are ready. Its Figma screen will be implemented with the corresponding API and database functions.</Paragraph></Card></div>
}

export default function App() {
  return <AuthProvider><Routes><Route path="/login" element={<LoginPage />} /><Route path="/register" element={<RegisterPage />} /><Route path="/forgot-password" element={<ForgotPasswordPage />} /><Route element={<ProtectedRoute />}><Route element={<AppShell />}><Route path="/overview" element={<OverviewPage />} /><Route path="/records" element={<RecordsPage />} /><Route path="/records/new" element={<RecordFormPage />} /><Route path="/records/:id" element={<RecordDetailPage />} /><Route path="/records/:id/edit" element={<RecordFormPage editing />} /><Route path="/records/:id/history" element={<RecordHistoryPage />} /><Route path="/insights" element={<HealthInsightsPage />} /><Route path="/sharing" element={<SharingPrivacyPage />} /><Route path="/services" element={<CareServicesPage />} /><Route path="/community" element={<CommunityPage />} /><Route path="/notifications" element={<NotificationsPage />} />{Object.keys(plannedPages).map((path) => <Route key={path} path={path} element={<PlannedPage />} />)}</Route></Route><Route path="/" element={<Navigate to="/overview" replace />} /><Route path="*" element={<Navigate to="/overview" replace />} /></Routes></AuthProvider>
}
