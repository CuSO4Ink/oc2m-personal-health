import React from 'react'
import { BellOutlined, DownOutlined, LoadingOutlined, MenuOutlined, HomeOutlined, FolderOpenOutlined, LineChartOutlined, CalendarOutlined, TeamOutlined, SafetyCertificateOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { Alert, Avatar, Badge, Button, Card, Checkbox, Divider, Drawer, Dropdown, Form, Input, Layout, Menu, Modal, Space, Spin, Tag, Typography } from 'antd'
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import LanguageSwitch from './LanguageSwitch'
import { useLanguage, t } from './i18n'
import api, { apiMessage } from './api'
import { AuthProvider, useAuth } from './auth'
const ReportUploadPage = React.lazy(() => import('./ReportUpload'))
const RecordsPage = React.lazy(() => import('./HealthRecords').then((module) => ({ default: module.RecordsPage })))
const RecordDetailPage = React.lazy(() => import('./HealthRecords').then((module) => ({ default: module.RecordDetailPage })))
const RecordFormPage = React.lazy(() => import('./HealthRecords').then((module) => ({ default: module.RecordFormPage })))
const RecordHistoryPage = React.lazy(() => import('./HealthRecords').then((module) => ({ default: module.RecordHistoryPage })))
const HealthProfilePage = React.lazy(() => import('./HealthProfile'))
const HealthInsightsPage = React.lazy(() => import('./HealthInsights'))
const SharingPrivacyPage = React.lazy(() => import('./SharingPrivacy'))
const CareServicesPage = React.lazy(() => import('./CareServices'))
const CommunityPage = React.lazy(() => import('./Community'))
const NotificationsPage = React.lazy(() => import('./Notifications'))
const AccountSecurityPage = React.lazy(() => import('./AccountSecurity'))
const HealthAdvicePage = React.lazy(() => import('./HealthAdvice'))
const HealthOverviewPage = React.lazy(() => import('./HealthOverview'))

const { Content, Header, Sider } = Layout
const { Title, Text, Paragraph, Link } = Typography

const navItems = [
  { key: '/overview', get label() { return t("首页") }, icon: <HomeOutlined /> },
  { key: '/records', get label() { return t("健康资料") }, icon: <FolderOpenOutlined /> },
  { key: '/insights', get label() { return t("Measurements") }, icon: <LineChartOutlined /> },
  { key: '/advice', get label() { return t("Health advice") }, icon: <SafetyCertificateOutlined /> },
  { key: '/services', get label() { return t("Reminders & appointments") }, icon: <CalendarOutlined /> },
  { key: '/sharing', get label() { return t("共享与访问") }, icon: <SafetyCertificateOutlined /> },
  { key: '/community', get label() { return t("病友交流") }, icon: <TeamOutlined /> },
]

const plannedPages = {
}

function Brand() {
  useLanguage()
  return <div className="brand"><span className="brand-mark">{t("PH")}</span><strong>{t("Personal Health")}</strong></div>
}

function AuthLayout({ children }) {
  useLanguage()
  return <main className="login-page"><div className="auth-language"><LanguageSwitch /></div>
    <section className="login-intro"><div className="intro-content"><Brand /><h1>{t('Keep your health records together.')}</h1><p>{t("整理病历与报告，查看身体指标变化，按需分享给关心你健康的人。")}</p></div></section>
    <section className="login-form-wrap"><div className="login-form-card">{children}</div></section>
  </main>
}

function LoginPage() {
  useLanguage()
  const navigate = useNavigate()
  const { login, user } = useAuth()
  const [error, setError] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [loginForm] = Form.useForm()
  const [demo, setDemo] = React.useState(null)
  React.useEffect(() => {
    let active = true
    api.get('/demo/context').then(({data}) => {
      if (!active) return
      // A fresh demo should also start its optional onboarding from the beginning.
      if (data.prepared && data.dataset_id) {
        try {
          if (localStorage.getItem('health-demo-dataset') !== data.dataset_id) {
            Object.keys(localStorage).filter((key) => key.startsWith('health-help:') || key.startsWith('personal-health:setup:')).forEach((key) => localStorage.removeItem(key))
            localStorage.setItem('health-demo-dataset', data.dataset_id)
          }
        } catch { /* Storage is optional for the demo. */ }
      }
      setDemo(data)
    }).catch(() => {})
    return () => {active = false}
  }, [])
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
    <Title level={2}>{t("欢迎回来")}</Title><Paragraph>{t("登录，继续管理你的健康资料。")}</Paragraph>
    {error && <Alert className="form-alert" type="error" showIcon message={error} />}
    <Form form={loginForm} layout="vertical" onFinish={submit} initialValues={{ remember: true }}>
      <Form.Item label={t("电子邮箱")} name="email" rules={[{ required: true, type: 'email', message: t('请输入有效的邮箱地址') }]}><Input autoComplete="email" placeholder={t("请输入邮箱地址")} /></Form.Item>
      <Form.Item label={t("密码")} name="password" rules={[{ required: true, message: t('请输入密码') }]}><Input.Password autoComplete="current-password" placeholder={t("请输入密码")} /></Form.Item>
      <div className="login-options"><Form.Item name="remember" valuePropName="checked" noStyle><Checkbox>{t("保持登录")}</Checkbox></Form.Item><Link onClick={() => navigate('/forgot-password')}>{t("忘记密码？")}</Link></div>
      <Button type="primary" htmlType="submit" block loading={submitting}>{t("登录")}</Button>
    </Form>
    <Paragraph className="signin-note" type="secondary">{t("健康资料由你管理，共享范围由你决定。")}</Paragraph>
    {demo?.prepared && <div className="demo-login"><Text strong>{t("选择一个演示账户")}</Text><div className="demo-account-options">{demo.accounts.slice(0, 1).map((account) => <button type="button" key={account.email} onClick={() => {loginForm.setFieldsValue({email: account.email, password: demo.password}); setError('')}}><b>{t(account.title)}</b><span>{t(account.description)}</span></button>)}</div>{demo.accounts.length > 1 && <details className="demo-other-accounts"><summary>{t('Other demo accounts ({count})', {count: demo.accounts.length - 1})}</summary><div className="demo-account-options">{demo.accounts.slice(1).map((account) => <button type="button" key={account.email} onClick={() => {loginForm.setFieldsValue({email: account.email, password: demo.password}); setError('')}}><b>{t(account.title)}</b><span>{t(account.description)}</span></button>)}</div></details>}<Text type="secondary">{t("选择后点击登录。演示账户内均为虚构资料。")}</Text></div>}
    <Divider /><div className="auth-switch"><Text>{t("还没有账户？")}</Text><Button type="link" onClick={() => navigate('/register')}>{t("注册账户")}</Button></div>
  </AuthLayout>
}

function RegisterPage() {
  useLanguage()
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
    <Title level={2}>{t("创建账户")}</Title><Paragraph>{t("开始建立自己的健康资料。")}</Paragraph>
    {error && <Alert className="form-alert" type="error" showIcon message={error} />}
    <Form layout="vertical" onFinish={submit}>
      <Form.Item label={t("姓名")} name="full_name" rules={[{ required: true, min: 2, message: t('请输入姓名') }]}><Input autoComplete="name" /></Form.Item>
      <Form.Item label={t("电子邮箱")} name="email" rules={[{ required: true, type: 'email', message: t('请输入有效的邮箱地址') }]}><Input autoComplete="email" /></Form.Item>
      <Form.Item label={t("密码")} name="password" extra={t("至少 8 位，包含字母和数字。")} rules={[{ required: true, min: 8, message: t('请至少输入 8 位字符') }]}><Input.Password autoComplete="new-password" /></Form.Item>
      <Button type="primary" htmlType="submit" block loading={submitting}>{t("注册")}</Button>
    </Form>
    <div className="auth-switch"><Text>{t("已有账户？")}</Text><Button type="link" onClick={() => navigate('/login')}>{t("登录")}</Button></div>
  </AuthLayout>
}

function ForgotPasswordPage() {
  useLanguage()
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
    {stage === 'request' && <><Title level={2}>{t("重置密码")}</Title><Paragraph>{t("填写账户使用的邮箱。")}</Paragraph>{notice && <Alert className="form-alert" type={notice.type} showIcon message={notice.text} />}<Form layout="vertical" onFinish={requestCode}><Form.Item label={t("电子邮箱")} name="email" rules={[{ required: true, type: 'email', message: t('请输入有效的邮箱地址') }]}><Input autoComplete="email" /></Form.Item><Button type="primary" htmlType="submit" block loading={submitting}>{t("获取重置验证码")}</Button></Form></>}
    {stage === 'confirm' && <><Title level={2}>{t("输入重置验证码")}</Title><Paragraph>{t("已为此账户准备六位验证码： ")}<b>{email}</b>.</Paragraph>{demoCode && <Alert className="form-alert" type="info" showIcon message={t(`演示验证码： ${demoCode}`)} description={t("目前仅在本页显示演示验证码，尚未发送邮件或短信。")} />}{notice && <Alert className="form-alert" type={notice.type} showIcon message={notice.text} />}<Form layout="vertical" onFinish={resetPassword} initialValues={{ code: demoCode }}><Form.Item label={t("重置验证码")} name="code" rules={[{ required: true, len: 6, message: t('请输入六位验证码') }]}><Input inputMode="numeric" maxLength={6} /></Form.Item><Form.Item label={t("新密码")} name="password" extra={t("至少 8 位，包含字母和数字。")} rules={[{ required: true, min: 8, message: t('请至少输入 8 位字符') }]}><Input.Password autoComplete="new-password" /></Form.Item><Button type="primary" htmlType="submit" block loading={submitting}>{t("重置密码")}</Button></Form></>}
    {stage === 'complete' && <><Alert className="form-alert" type="success" showIcon message={t("密码已重置")} description={t("现在可以用新密码登录。")} /><Button type="primary" block onClick={() => navigate('/login')}>{t("返回登录")}</Button></>}
    {stage !== 'complete' && <Button className="back-link" type="link" onClick={() => navigate('/login')}>{t("← 返回登录")}</Button>}
  </AuthLayout>
}

function ProtectedRoute() {
  useLanguage()
  const { loading, user } = useAuth()
  if (loading) return <div className="route-loading"><Spin indicator={<LoadingOutlined spin />} size="large" /><Text>{t("正在加载账户…")}</Text></div>
  return user ? <Outlet /> : <Navigate to="/login" replace />
}

export function AppShell() {
  useLanguage()
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()
  const [unreadNotifications, setUnreadNotifications] = React.useState(0)
  const [communityEnabled, setCommunityEnabled] = React.useState(false)
  const [menuOpen, setMenuOpen] = React.useState(false)
  const [helpOpen, setHelpOpen] = React.useState(false)
  const visibleItems = [{ type: 'group', label: t('我的健康'), children: navItems.slice(0, 5).map(item => ({...item,label:t(item.label)})) }, { type: 'group', label: t('分享与交流'), children: navItems.slice(5).map(item => ({...item,label:t(item.label)})).filter((item) => item.key !== '/community' || communityEnabled) }]
  const selectedKey = (location.pathname.startsWith('/records') || location.pathname === '/profile') ? '/records' : location.pathname
  const utilityTitle = { '/notifications': t('消息通知'), '/account': t('账户与安全') }[location.pathname]
  const pageTitle = (location.pathname.startsWith('/records') || location.pathname === '/profile') ? t('健康资料') : navItems.find((item) => item.key === location.pathname)?.label || plannedPages[location.pathname]?.[0] || utilityTitle || t('首页')
  async function signOut() { await logout(); navigate('/login', { replace: true }) }
  const accountMenu = { items: [{ key: 'account', label: t('账户与安全'), onClick: () => navigate('/account') }, { type: 'divider' }, { key: 'logout', label: t('退出登录'), danger: true, onClick: signOut }] }

  React.useEffect(() => {
    let active = true
    const refresh = () => api.get('/notifications/summary').then(({ data }) => { if (active) setUnreadNotifications(data.summary.unread) }).catch(() => {})
    refresh()
    window.addEventListener('notifications:changed', refresh)
    const interval = window.setInterval(() => { if (document.visibilityState === 'visible') refresh() }, 30000)
    const onFocus = () => refresh()
    window.addEventListener('focus', onFocus)
    return () => { active = false; window.clearInterval(interval); window.removeEventListener('focus', onFocus); window.removeEventListener('notifications:changed', refresh) }
  }, [location.pathname])

  React.useEffect(() => {
    let active = true
    const refresh = () => api.get('/community').then(({ data }) => { if (active) setCommunityEnabled(Boolean(data.profile.enabled)) }).catch(() => {})
    refresh()
    window.addEventListener('community:changed', refresh)
    return () => { active = false; window.removeEventListener('community:changed', refresh) }
  }, [])

  function openPage({ key }) { setMenuOpen(false); navigate(key) }

  return <Layout className="app-shell"><a className="skip-link" href="#main-content">{t("跳到主要内容")}</a><Sider width={260} theme="light" className="app-sider"><Brand /><Menu aria-label={t("主导航")} mode="inline" selectedKeys={[selectedKey]} items={visibleItems} onClick={openPage} /></Sider><Drawer className="app-mobile-navigation" title={t("Personal Health")} placement="left" open={menuOpen} onClose={() => setMenuOpen(false)} size={280}><Menu aria-label={t("移动端导航")} mode="inline" selectedKeys={[selectedKey]} items={visibleItems} onClick={openPage} /><Button block onClick={() => openPage({ key: '/account' })}>{t("账户与安全")}</Button></Drawer><Layout><Header className="app-header"><Space><Button className="mobile-menu-button" aria-label={t("打开导航")} aria-expanded={menuOpen} icon={<MenuOutlined />} onClick={() => setMenuOpen(true)} /><Text>{t(pageTitle)}</Text></Space><Space size="middle"><LanguageSwitch /><Button className="header-help" aria-label={t("使用帮助")} type="text" shape="circle" icon={<QuestionCircleOutlined />} onClick={() => setHelpOpen(true)} /><Badge count={unreadNotifications} size="small" overflowCount={99}><Button aria-label={t(`打开通知，${unreadNotifications} 条未读`)} type="text" shape="circle" icon={<BellOutlined />} onClick={() => navigate('/notifications')} /></Badge><Dropdown menu={accountMenu} trigger={['click']}><button className="profile-button" aria-label={t("账户菜单")}><Avatar>{user.initials}</Avatar><span>{user.full_name}</span><DownOutlined /></button></Dropdown></Space></Header><Content id="main-content" tabIndex={-1} className="app-content"><React.Suspense fallback={<div className="route-loading"><Spin /><Text>{t("正在加载页面…")}</Text></div>}><Outlet /></React.Suspense></Content></Layout><Modal title={t("从一份资料开始")} open={helpOpen} onCancel={() => setHelpOpen(false)} footer={<Button onClick={() => setHelpOpen(false)}>{t("知道了")}</Button>}><div className="workflow-help"><p><b>{t("1. 在健康资料收好报告。")}</b>{t(" 模拟医院同步或上传自己的文件，系统分类整理并建立文字索引。")}</p><p><b>{t("2. 核对识别结果。")}</b>{t(" 对照原报告，确认要加入的指标和健康信息；不确定的内容可以暂时保留。")}</p><p><b>{t("3. Follow measurements and prepare health advice.")}</b>{t("Measurements shows trends and sources. Health advice uses your basic information, health history, reports and measurements to suggest topics to discuss and everyday steps.")}</p><p>{t("需要时再设置提醒、授权共享或加入病友交流。")}</p><Button onClick={() => { setHelpOpen(false); navigate('/records?sync=1') }}>{t("体验医院同步")}</Button><Button type="text" onClick={() => { try { Object.keys(localStorage).filter((key) => key.startsWith(`health-help:${user.id}:`)).forEach((key) => localStorage.removeItem(key)) } catch { /* Storage is optional. */ } window.dispatchEvent(new Event('health-help:reset')) }}>{t("重新显示页面提示")}</Button></div></Modal></Layout>
}

function PlannedPage() {
  useLanguage()
  const { pathname } = useLocation()
  const [title, description] = plannedPages[pathname] || ['Page not found', '']
  return <div className="page-stack"><Title level={1}>{title}</Title><Paragraph>{description}</Paragraph><Card className="planned-card"><Tag color="gold">{t("In development")}</Tag><Title level={3}>{t("This module is being implemented")}</Title><Paragraph>{t("The route and application structure are ready. Its Figma screen will be implemented with the corresponding API and database functions.")}</Paragraph></Card></div>
}

export default function App() {
  useLanguage()
  return <AuthProvider><Routes><Route path="/login" element={<LoginPage />} /><Route path="/register" element={<RegisterPage />} /><Route path="/forgot-password" element={<ForgotPasswordPage />} /><Route element={<ProtectedRoute />}><Route element={<AppShell />}><Route path="/overview" element={<HealthOverviewPage />} /><Route path="/profile" element={<HealthProfilePage />} /><Route path="/records" element={<RecordsPage />} /><Route path="/records/upload" element={<ReportUploadPage />} /><Route path="/records/new" element={<RecordFormPage />} /><Route path="/records/:id" element={<RecordDetailPage />} /><Route path="/records/:id/edit" element={<RecordFormPage editing />} /><Route path="/records/:id/history" element={<RecordHistoryPage />} /><Route path="/insights" element={<HealthInsightsPage />} /><Route path="/advice" element={<HealthAdvicePage />} /><Route path="/sharing" element={<SharingPrivacyPage />} /><Route path="/services" element={<CareServicesPage />} /><Route path="/community" element={<CommunityPage />} /><Route path="/notifications" element={<NotificationsPage />} /><Route path="/account" element={<AccountSecurityPage />} />{Object.keys(plannedPages).map((path) => <Route key={path} path={path} element={<PlannedPage />} />)}</Route></Route><Route path="/" element={<Navigate to="/overview" replace />} /><Route path="*" element={<Navigate to="/overview" replace />} /></Routes></AuthProvider>
}
