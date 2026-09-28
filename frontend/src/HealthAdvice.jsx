import React from 'react'
import { Alert, Button, Card, Checkbox, Empty, List, Skeleton, Space, Tag, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'
import api, { apiMessage } from './api'
import { useLanguage } from './i18n'
import { metricLabels } from './healthLabels'
import './PersonalWorkspace.css'

const { Title, Paragraph, Text } = Typography
function Evidence({ ids, sources, t }) {
  const selected = (ids || []).map(id => sources.find(source => source.id === id)).filter(Boolean)
  return selected.length > 0 && <details className="advice-evidence"><summary>{t('Evidence & source records')}</summary><ul>{selected.map(source => <li key={source.id}><Link to={source.path}>{source.type === 'measurement' ? metricLabels[source.label] || source.label : source.label}{source.page ? ` · ${t('Page')} ${source.page}` : ''}</Link>{source.confirmed === false && <Tag>{t('Report text — verify before relying on it')}</Tag>}</li>)}</ul></details>
}
export default function HealthAdvice() {
  const { language, t } = useLanguage()
  // A language session owns its requests, including an en -> zh -> en round trip.
  return <AdviceContent key={language} language={language} t={t} />
}
function AdviceContent({ language, t }) {
  const [data, setData] = React.useState(null)
  const [loading, setLoading] = React.useState(true)
  const [loadedLanguage, setLoadedLanguage] = React.useState(language)
  const [generating, setGenerating] = React.useState(false)
  const [acknowledged, setAcknowledged] = React.useState(false)
  const [error, setError] = React.useState('')
  const [errorOperation, setErrorOperation] = React.useState('load')
  const attempt = React.useRef('')
  const mounted = React.useRef(true)
  const requestVersion = React.useRef(0)
  const inFlight = React.useRef(false)
  const load = React.useCallback(async () => {
    if (inFlight.current) return
    const version = ++requestVersion.current
    setLoading(true)
    try { const response = await api.get('/advice', { params: { language } }); if (mounted.current && requestVersion.current === version) { setData(response.data); setLoadedLanguage(language); setError('') } }
    catch (failure) { if (mounted.current && requestVersion.current === version) { setError(apiMessage(failure)); setErrorOperation('load') } }
    finally { if (mounted.current && requestVersion.current === version) setLoading(false) }
  }, [language])
  React.useEffect(() => {
    mounted.current = true
    attempt.current = ''
    let active = true
    const version = ++requestVersion.current
    api.get('/advice', {params:{language}}).then(({data: next}) => { if (active && requestVersion.current === version) {setData(next); setLoadedLanguage(language); setError('')} }).catch(failure => { if (active && requestVersion.current === version) {setError(apiMessage(failure));setErrorOperation('load')} }).finally(() => {if(active && requestVersion.current === version) setLoading(false)})
    const visible = () => { if (document.visibilityState === 'visible') load() }
    window.addEventListener('focus', visible)
    return () => { active = false; mounted.current = false; window.removeEventListener('focus', visible) }
  }, [load, language])
  const generate = React.useCallback(async (consent = false) => {
    if (inFlight.current || !data?.configured || !data.input?.has_data || (!data.consent?.granted && !(consent && acknowledged))) return
    const version = ++requestVersion.current
    attempt.current = `${language}:${data.input.fingerprint}`
    inFlight.current = true
    setGenerating(true); setError('')
    try {
      const response = await api.post('/advice/generate', { language, ...(consent ? { acknowledged: true } : {}) }, { timeout: 100000 })
      if (mounted.current && requestVersion.current === version) setData(response.data)
    } catch (failure) {
      if (mounted.current && requestVersion.current === version) {
        if (failure.response?.data?.input) setData(failure.response.data)
        setErrorOperation('generate')
        setError(failure.response?.data?.error === 'generation_in_progress' ? t('An update is already in progress. Please check again shortly.') : apiMessage(failure))
      }
    } finally { if (mounted.current && requestVersion.current === version) {inFlight.current = false;setGenerating(false)} }
  }, [acknowledged, data, language, t])
  React.useEffect(() => {
    const key = `${language}:${data?.input?.fingerprint}`
    if (!loading && loadedLanguage === language && !generating && data?.configured && data?.consent?.granted && data.input?.has_data && (data.stale || !data.latest) && attempt.current !== key) {
      attempt.current = key
      generate()
    }
  }, [data, loading, loadedLanguage, generating, language, generate])
  const result = data?.latest?.language === language ? data.latest : null
  const sources = result?.sources || []
  return <div className="page-stack health-advice">
    <div className="page-heading"><div><Title level={1}>{t('Health advice')}</Title><Paragraph>{t('Review possible concerns and everyday steps, using your latest health information, reports and measurements.')}</Paragraph></div><Button icon={<ReloadOutlined />} loading={generating || loading} onClick={load}>{t('Check for updates')}</Button></div>
    {error && <Alert type="error" showIcon title={t('Advice could not be updated')} description={t(error)} action={<Button disabled={generating} onClick={() => errorOperation === 'generate' ? generate(acknowledged) : load()}>{t('Retry')}</Button>} />}
    {loading || loadedLanguage !== language ? <Card><Skeleton active paragraph={{rows:5}} /></Card> : data && <>
      {!data.configured && <Alert type="warning" showIcon title={t('AI advice is not configured')} description={t('Add the provider key on the server. Your records and measurements remain available.')} />}
      {!data.input?.has_data ? <Card><Empty description={t('Add health information or a report to get started.')}><Space wrap><Link to="/profile"><Button>{t('Basic information & history')}</Button></Link><Link to="/records"><Button type="primary">{t('Reports & documents')}</Button></Link></Space></Empty></Card> : <>
        {!data.consent?.granted && <Card className="advice-consent" title={t('Use your records to prepare advice')}>
          <Paragraph>{t('DeepSeek will receive a limited health summary and extracted report text, including health items marked sensitive. Account contact details and original files are excluded. Free text may still contain personal information; review your records before enabling this.')}</Paragraph>
          <Checkbox checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)}>{t('I agree to send this health information to DeepSeek for advice.')}</Checkbox>
          <div className="form-actions"><Button type="primary" disabled={!acknowledged || !data.configured} loading={generating} onClick={() => generate(true)}>{t('Generate health advice')}</Button></div>
        </Card>}
        {generating && <Alert type="info" showIcon title={t('Preparing advice from your latest information…')} description={t('You can keep using your records. A saved result will appear here when ready.')} />}
        {result && <>
          <div className="advice-meta"><Space wrap><Tag color={data.stale ? 'gold' : 'green'}>{data.stale ? t('Information changed — update needed') : t('Based on current information')}</Tag><Text type="secondary">{t('Generated')} {new Date(result.created_at).toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US')} · {result.model}</Text></Space></div>
          <Card className="advice-summary"><Paragraph>{result.summary}</Paragraph><Text type="secondary">{t('AI-generated information for discussion and daily self-care; not a diagnosis or a medication plan.')}</Text></Card>
          <section><Title level={2}>{t('Concerns to discuss')}</Title>{result.concerns?.length ? <div className="advice-grid">{result.concerns.map((item,index) => <Card key={index} title={item.title}><Paragraph>{item.summary}</Paragraph><Evidence ids={item.evidenceIds} sources={sources} t={t} /></Card>)}</div> : <Paragraph>{t('No specific concern was identified from the available information. This is not an all-clear health assessment.')}</Paragraph>}</section>
          <section><Title level={2}>{t('Everyday steps')}</Title><List className="advice-actions" dataSource={result.daily_actions || []} renderItem={(item,index) => <List.Item><div><Text className="advice-step">{index+1}</Text><Title level={4}>{item.title}</Title><Paragraph>{item.summary}</Paragraph><Evidence ids={item.evidenceIds} sources={sources} t={t} /></div></List.Item>} /></section>
          {result.limitations?.length > 0 && <details className="quiet-details"><summary>{t('Limits of this advice')}</summary><ul>{result.limitations.map((item,index)=><li key={index}>{item}</li>)}</ul></details>}
        </>}
        <details className="quiet-details"><summary>{t('Information used')}</summary><Paragraph>{t('Health history items: {count}',{count:data.input.profile_items ?? 0})} · {t('Measurements: {count}',{count:data.input.measurements ?? 0})} · {t('Reports: {count}',{count:data.input.records ?? 0})}</Paragraph><Paragraph>{t('Advice updates when you open this page after changing your information or on a new day (UTC). The same information reuses its saved result during that day.')}</Paragraph>{data.input.truncated && <Paragraph>{t('Some long or older material was omitted to keep the analysis focused. This is not a complete review of every page.')}</Paragraph>}</details>
      </>}
      <Space wrap><Link to="/profile">{t('Review health information')}</Link><Link to="/records">{t('Review reports')}</Link><Link to="/insights">{t('View measurements')}</Link></Space>
    </>}
  </div>
}
