import { t, useLanguage } from './i18n'
import React from 'react'
import { Alert, Button, Card, List, Select, Space, Tag, Typography, message } from 'antd'
import { CloseOutlined, SyncOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'
import api, { apiMessage } from './api'
import { recordValue } from './recordDisplay'
import { recordLabels } from './healthLabels'
import './documents.css'

const { Paragraph, Text } = Typography
const statusLabels = { get ready() { return t("待同步") }, get imported() { return t("已同步") }, get duplicate() { return t("已存在") }, get failed() { return t("同步失败") } }
const indexLabels = { get complete() { return t("全文可搜索") }, get partial() { return t("部分页面可搜索") }, get failed() { return t("等待重新识别") } }

export default function HospitalSync({ onImported, onClose }) {
  useLanguage()
  const [jobs, setJobs] = React.useState([])
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState('')
  React.useEffect(() => { let active = true; api.get('/records/imports').then(({ data }) => { if (active) setJobs(data.jobs) }).catch((e) => { if (active) setError(apiMessage(e)) }); return () => { active = false } }, [])
  async function preview() {
    setBusy(true); setError('')
    try { const { data } = await api.post('/records/imports'); setJobs((current) => [data.job, ...current]) }
    catch (e) { setError(apiMessage(e)) }
    finally { setBusy(false) }
  }
  async function sync(job, retry = false) {
    setBusy(true); setError('')
    try {
      const { data } = await api.post(`/records/imports/${job.id}/${retry ? 'retry' : 'confirm'}`, { revision: job.revision, selections: Object.fromEntries(job.items.map((item) => [item.external_id, item.selected_type])) })
      setJobs((current) => current.map((item) => item.id === job.id ? data.job : item))
      onImported(); message.success(t('资料已整理。请按需核对读数和健康信息。'))
    } catch (e) { setError(apiMessage(e)) }
    finally { setBusy(false) }
  }
  function classify(jobId, externalId, value) {
    setJobs((current) => current.map((job) => job.id === jobId ? { ...job, items: job.items.map((item) => item.external_id === externalId ? { ...item, selected_type: value } : item) } : job))
  }
  return <Card className="hospital-sync" title={t("从医院同步资料")} extra={<Button type="text" aria-label={t("关闭医院同步")} icon={<CloseOutlined />} onClick={onClose} />}>
    <Space wrap><Tag color="blue">{t("模拟医院")}</Tag><Text>{t("8 份合成 PDF，覆盖 6 种类型和 3 次检查日期。")}</Text></Space>
    <Paragraph type="secondary">{t("原文件保存在你的档案中。系统自动分类、整理全文和识别候选；读数与健康信息经你确认后才正式加入。这里不会连接真实医院。")}</Paragraph>
    {error && <Alert type="error" showIcon title={t(error)} />}
    <Button aria-label={t("查看可同步的资料")} icon={<SyncOutlined />} onClick={preview} loading={busy}>{t("查看可同步的资料")}</Button>
    {busy && <Paragraph className="sync-progress" role="status">{t("正在处理文件和扫描页面，请稍候。原件保存后，识别状态会逐项显示。")}</Paragraph>}
    {jobs.slice(0, 4).map((job, position) => <details className="sync-batch" key={job.id} open={position === 0 && (job.counts.ready > 0 || job.counts.failed > 0)}>
      <summary>{position === 0 ? t('最近一次同步') : t('历史同步')} · {job.counts.imported}{t(" 份已同步")}{job.counts.duplicate ? t(` · ${job.counts.duplicate} 份已存在`) : ''}{job.counts.failed ? t(` · ${job.counts.failed} 份失败`) : ''}{t(" · 展开查看")}</summary>
      <List dataSource={job.items} renderItem={(item) => <List.Item className="sync-document" actions={item.record_id ? [<Link key="record" to={`/records/${item.record_id}`}>{t("查看资料")}</Link>] : [<a key="preview" href={`/api/records/imports/samples/${item.external_id}`} target="_blank" rel="noreferrer">{t("预览 PDF")}</a>]}>
        <List.Item.Meta title={<Space wrap><span>{recordValue(item, 'title')}</span><Tag>{statusLabels[item.status]}</Tag></Space>} description={<><Text type="secondary">{recordValue(item, 'filename')} · {item.record_date}</Text><div>{item.status === 'ready' ? <Select aria-label={t('Classify {title}', { title: recordValue(item, 'title') })} value={item.selected_type} disabled={busy} onChange={(value) => classify(job.id, item.external_id, value)} options={Object.entries(recordLabels).map(([value, label]) => ({ value, label }))} /> : <Tag>{recordLabels[item.selected_type]}</Tag>}{item.index_status && <Tag color={item.index_status === 'complete' ? 'green' : 'orange'}>{indexLabels[item.index_status]}</Tag>}</div>{item.error && <Paragraph type="secondary">{item.status === 'duplicate' ? t('已保留之前同步的原件，不会重复添加。') : t(item.error)}</Paragraph>}</>} />
      </List.Item>} />
      <Space wrap>{job.counts.ready > 0 && <Button type="primary" loading={busy} onClick={() => sync(job)}>{t("同步这 ")}{job.counts.ready}{t(" 份资料")}</Button>}{job.counts.failed > 0 && <Button loading={busy} onClick={() => sync(job, true)}>{t("重试失败项")}</Button>}</Space>
    </details>)}
    {jobs[0]?.counts.imported > 0 && <Paragraph className="sync-summary">{t("同步完成。发现的候选汇总在下方“待核对信息”，可以逐份查看，也可以稍后处理。没有指标的文件同样可以全文搜索。")}</Paragraph>}
  </Card>
}
