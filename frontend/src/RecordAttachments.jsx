import { t, useLanguage } from './i18n'
import React from 'react'
import { Alert, Button, Card, Empty, List, Modal, Popconfirm, Space, Tag, Typography, Upload, message } from 'antd'
import { DeleteOutlined, DownloadOutlined, EyeOutlined, ScanOutlined, SyncOutlined, UploadOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import { recordValue } from './recordDisplay'
import ReportExtraction from './ReportExtraction'
import DocumentPreview from './DocumentPreview'
import './documents.css'

const { Paragraph, Text } = Typography
const sizeLabel = (size) => size < 1024 * 1024 ? `${Math.ceil(size / 1024)} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`
const indexLabels = { get pending() { return t("尚未整理全文") }, get complete() { return t("全文可搜索") }, get partial() { return t("部分页面可搜索") }, get failed() { return t("全文识别失败") } }

export default function RecordAttachments({ record, onChange }) {
  useLanguage()
  const [uploading, setUploading] = React.useState(false)
  const [busyId, setBusyId] = React.useState(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const queryKey = ['extract', 'extraction', 'document', 'page', 'review'].map((key) => searchParams.get(key) || '').join(':')
  function targetFromQuery() {
    const draftId = searchParams.get('extraction')
    if (draftId && /^\d+$/.test(draftId)) return { extractionId: Number(draftId) }
    if (searchParams.get('review') === '1' && record.pending_extractions?.length) return { extractionId: record.pending_extractions[0].id }
    const attachment = record.attachments.find((item) => item.id === Number(searchParams.get('extract')))
    if (attachment && !record.archived) {
      const pending = record.pending_extractions?.find((item) => item.attachment_id === attachment.id)
      return pending ? { extractionId: pending.id } : attachment.latest_extraction_id ? { extractionId: attachment.latest_extraction_id } : { attachment }
    }
    return null
  }
  function previewFromQuery() {
    const attachment = record.attachments.find((item) => item.id === Number(searchParams.get('document')))
    return attachment ? { ...attachment, page: Math.max(1, Number(searchParams.get('page')) || 1) } : null
  }
  const [lastQueryKey, setLastQueryKey] = React.useState(queryKey)
  const [extraction, setExtraction] = React.useState(targetFromQuery)
  const [preview, setPreview] = React.useState(previewFromQuery)
  if (queryKey !== lastQueryKey) {
    setLastQueryKey(queryKey)
    if (queryKey !== '::::') {
      const nextExtraction = targetFromQuery(), nextPreview = previewFromQuery()
      if (nextExtraction) setExtraction(nextExtraction)
      if (nextPreview) setPreview(nextPreview)
    }
  }
  React.useEffect(() => {
    if (queryKey === '::::') return
    const next = new URLSearchParams(searchParams)
    for (const key of ['extract', 'extraction', 'document', 'page', 'review']) next.delete(key)
    setSearchParams(next, { replace: true })
  }, [queryKey, searchParams, setSearchParams])
  const url = (attachment) => `/api/records/${record.id}/attachments/${attachment.id}`
  async function refresh() { try { const { data } = await api.get(`/records/${record.id}`); onChange(data.record) } catch (error) { message.error(apiMessage(error)) } }
  async function upload({ file, onSuccess, onError }) {
    setUploading(true)
    const payload = new FormData(); payload.append('file', file); payload.append('version', record.version)
    try {
      const { data } = await api.post(`/records/${record.id}/attachments`, payload, { headers: { 'Content-Type': 'multipart/form-data' } })
      onChange(data.record); onSuccess(data); message.success(t('原件已保存，并完成自动整理。'))
    } catch (error) { message.error(apiMessage(error)); onError(error) }
    finally { setUploading(false) }
  }
  async function retry(attachment) {
    setBusyId(attachment.id)
    try { const { data } = await api.post(`${url(attachment).replace('/api', '')}/index`); onChange(data.record); message.success(t('整理状态已更新。')) }
    catch (error) { message.error(apiMessage(error)) }
    finally { setBusyId(null) }
  }
  async function remove(attachment) {
    setBusyId(attachment.id)
    try { const { data } = await api.delete(`/records/${record.id}/attachments/${attachment.id}`, { data: { version: record.version } }); onChange(data.record); message.success(t('附件已删除。')) }
    catch (error) { message.error(apiMessage(error)) }
    finally { setBusyId(null) }
  }
  function validate(file) {
    if (file.size > 10 * 1024 * 1024) { message.error(t('每份文件不能超过 10 MB。')); return Upload.LIST_IGNORE }
    if (!/\.(pdf|png|jpe?g)$/i.test(file.name)) { message.error(t('请选择 PDF、PNG 或 JPEG 文件。')); return Upload.LIST_IGNORE }
    return true
  }
  function reviewAttachment(attachment) {
    const pending = record.pending_extractions?.find((item) => item.attachment_id === attachment.id)
    setExtraction(pending ? { extractionId: pending.id } : attachment.latest_extraction_id ? { extractionId: attachment.latest_extraction_id } : { attachment })
  }
  return <Card title={t(`原始文件（${record.attachments.length}/10）`)} extra={record.is_editable && <Upload accept=".pdf,.png,.jpg,.jpeg" showUploadList={false} beforeUpload={validate} customRequest={upload} disabled={uploading || record.attachments.length >= 10}><Button icon={<UploadOutlined />} loading={uploading}>{t("上传文件")}</Button></Upload>}>
    <Paragraph type="secondary">{t("PDF、PNG 或 JPEG，每份最多 10 MB。搜索索引只供本人查找；共享原文件需要单独勾选，隐藏文字字段不会对原文件打码。")}</Paragraph>
    {record.pending_extractions?.length > 0 && <Alert type="info" showIcon title={t("发现待核对信息")} description={<Space direction="vertical">{record.pending_extractions.map((draft) => <Space wrap key={draft.id}><Text>{draft.filename} · {draft.candidate_count}{t(" 条读数 · ")}{draft.fact_count}{t(" 条健康信息")}</Text><Button size="small" onClick={() => setExtraction({ extractionId: draft.id })}>{t("核对后加入")}</Button></Space>)}</Space>} style={{ marginBottom: 16 }} />}
    {record.attachments.length ? <List dataSource={record.attachments} renderItem={(attachment) => <List.Item className="attachment-item" actions={[
      <Button key="preview" icon={<EyeOutlined />} onClick={() => setPreview({ ...attachment, page: 1 })}>{t("查看原件")}</Button>,
      <Button key="download" icon={<DownloadOutlined />} href={`${url(attachment)}?download=1`}>{t("下载")}</Button>,
      ...(!record.archived ? [<Button key="extract" icon={<ScanOutlined />} onClick={() => reviewAttachment(attachment)}>{record.pending_extractions?.some((draft) => draft.attachment_id === attachment.id) ? t('核对识别信息') : t('查看识别结果')}</Button>] : []),
      ...(record.is_editable ? [<Popconfirm key="delete" title={t("删除这份附件？")} description={t("原始文件及搜索索引将删除。已确认读数及来源留痕会保留。")} onConfirm={() => remove(attachment)} okText={t("删除")} okButtonProps={{ danger: true }}><Button danger icon={<DeleteOutlined />} loading={busyId === attachment.id} disabled={uploading}>{t("删除")}</Button></Popconfirm>] : []),
    ]}><List.Item.Meta title={recordValue(attachment, 'filename')} description={<><Text type="secondary">{sizeLabel(attachment.size)}{t(" · 保存于 ")}{dayjs(attachment.created_at).format('YYYY-MM-DD HH:mm')}</Text><div className="document-index-state"><Tag color={attachment.index?.status === 'complete' ? 'green' : 'orange'}>{indexLabels[attachment.index?.status || 'pending']}</Tag>{attachment.index?.total_pages != null && <Text>{attachment.index.processed_pages?.length || 0}/{attachment.index.total_pages}{t(" 页")}</Text>}{attachment.index?.status !== 'complete' && !record.archived && <Button aria-label={t("重新整理")} size="small" icon={<SyncOutlined />} loading={busyId === attachment.id} onClick={() => retry(attachment)}>{t("重新整理")}</Button>}</div>{attachment.index?.warnings?.length > 0 && <details><summary>{t("识别说明")}</summary>{attachment.index.warnings.map((warning, index) => <Paragraph key={index}>{t(warning)}</Paragraph>)}</details>}</>} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("尚无附件")} />}
    {!record.is_editable && <Text type="secondary">{t("模拟医院原件只读，个人分类可以在下方调整。")}</Text>}
    {!record.archived && <details className="quiet-details"><summary>{t("从文字记录中提取")}</summary><Button icon={<ScanOutlined />} onClick={() => setExtraction({})}>{t("识别记录说明中的信息")}</Button></details>}
    <Modal title={recordValue(preview, 'filename')} open={Boolean(preview)} onCancel={() => setPreview(null)} footer={<Space><Button aria-label={t("关闭预览")} onClick={() => setPreview(null)}>{t("关闭")}</Button>{preview && <Button icon={<DownloadOutlined />} href={`${url(preview)}?download=1`}>{t("下载原件")}</Button>}</Space>} width={960} destroyOnHidden>
      {preview && <DocumentPreview url={url(preview)} filename={recordValue(preview, 'filename')} contentType={preview.content_type} initialPage={preview.page} downloadUrl={`${url(preview)}?download=1`} />}
    </Modal>
    <ReportExtraction record={record} attachment={extraction?.attachment} extractionId={extraction?.extractionId} open={Boolean(extraction)} onClose={() => setExtraction(null)} onImported={refresh} />
  </Card>
}
