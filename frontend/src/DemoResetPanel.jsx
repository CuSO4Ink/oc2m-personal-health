import React from 'react'
import { Alert, Button, Card, Modal, Typography, message } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import api, { apiMessage } from './api'
import { useLanguage } from './i18n'

const { Paragraph, Text } = Typography

export default function DemoResetPanel({ accountEmail, onReset }) {
  const { t } = useLanguage()
  const [available, setAvailable] = React.useState(false)
  const [open, setOpen] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState('')
  React.useEffect(() => {
    let active = true
    api.get('/demo/reset-account').then(({ data }) => { if (active) setAvailable(data.available === true) }).catch(() => { /* Only the dedicated demo offers this action. */ })
    return () => { active = false }
  }, [])

  async function reset() {
    if (busy) return
    setBusy(true); setError('')
    try {
      await api.post('/demo/reset-account', { confirmed: true })
      setOpen(false)
      window.dispatchEvent(new Event('notifications:changed'))
      window.dispatchEvent(new Event('community:changed'))
      message.success(t('Your demo data has been reset. You can sync the eight hospital reports again.'))
      await onReset?.()
    } catch (failure) { setError(apiMessage(failure)) }
    finally { setBusy(false) }
  }

  if (!available) return null
  return <Card title={t('Start a new demonstration')}>
    <Paragraph>{t('Clear your practice data and repeat the hospital sync, report review, measurements and sharing workflow.')}</Paragraph>
    <Paragraph type="secondary">{t('Your sign-in account, preferences and the original community examples are kept. The eight hospital sample PDFs stay available for everyone.')}</Paragraph>
    <Button danger icon={<DeleteOutlined aria-hidden="true" />} onClick={() => { setError(''); setOpen(true) }}>{t('Reset my demo data')}</Button>
    <Modal title={t('Reset this account’s demo data?')} open={open} onCancel={() => !busy && setOpen(false)} onOk={reset}
      okText={t('Reset my demo data')} cancelText={t('Cancel')} okButtonProps={{ danger: true }} confirmLoading={busy}
      cancelButtonProps={{ disabled: busy }} closable={!busy} mask={{ closable: !busy }} keyboard={!busy}>
      <Paragraph><Text strong>{accountEmail}</Text></Paragraph>
      <Paragraph>{t('This clears your health information, imported and uploaded reports, measurements, AI advice, grants, appointments, reminders, activity history and notifications.')}</Paragraph>
      <Paragraph>{t('Practice posts, comments and friend requests are removed. Friendships and their entire chats are cleared for both participants; original community examples remain.')}</Paragraph>
      <Paragraph>{t('Other accounts’ health records are not affected. Your name, sign-in details and preferences are kept; your phone number and date of birth are cleared.')}</Paragraph>
      <Alert type="warning" showIcon title={t('This cannot be undone from the website.')} />
      {error && <Alert type="error" showIcon title={t(error)} />}
    </Modal>
  </Card>
}
