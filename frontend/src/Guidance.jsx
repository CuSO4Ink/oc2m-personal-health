import { t, useLanguage } from './i18n'
import React from 'react'
import { Button } from 'antd'
import { CloseOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { useAuth } from './auth'

export default function Guidance({ id, title = t('使用说明'), children, defaultExpanded = false }) {
  useLanguage()
  const { user } = useAuth() || {}
  const storageKey = `health-help:${user?.id || 'guest'}:${id}`
  return <GuidanceContent key={storageKey} storageKey={storageKey} title={title} defaultExpanded={defaultExpanded}>{children}</GuidanceContent>
}

function GuidanceContent({ storageKey, title, children, defaultExpanded }) {
  useLanguage()
  const [dismissed, setDismissed] = React.useState(() => {
    try { return localStorage.getItem(storageKey) === 'dismissed' } catch { return false }
  })
  const [expanded, setExpanded] = React.useState(defaultExpanded)
  React.useEffect(() => {
    const reset = () => { setDismissed(false); setExpanded(false) }
    window.addEventListener('health-help:reset', reset)
    return () => window.removeEventListener('health-help:reset', reset)
  }, [])
  function dismiss() {
    setDismissed(true); setExpanded(false)
    try { localStorage.setItem(storageKey, 'dismissed') } catch { /* Help remains usable without browser storage. */ }
  }
  function reopen() {
    setDismissed(false); setExpanded(true)
    try { localStorage.removeItem(storageKey) } catch { /* No persistence is required. */ }
  }
  if (dismissed) return <div className="guidance-reopen"><Button type="text" size="small" aria-label={title} icon={<QuestionCircleOutlined aria-hidden="true" />} onClick={reopen}>{title}</Button></div>
  return <aside className={`guidance ${expanded ? 'expanded' : ''}`} aria-label={title}>
    <div className="guidance-heading"><Button type="text" icon={<QuestionCircleOutlined />} aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{title}<span className="guidance-toggle">{expanded ? t('收起说明') : t('了解更多')}</span></Button><Button type="text" size="small" icon={<CloseOutlined />} aria-label={t('Dismiss hint: {title}', { title })} onClick={dismiss} /></div>
    {expanded && <div className="guidance-body">{children}</div>}
  </aside>
}
