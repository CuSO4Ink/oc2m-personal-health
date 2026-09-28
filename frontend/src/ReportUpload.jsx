import { t, useLanguage } from './i18n'
import React from 'react'
import { Alert, Button, Card, DatePicker, Form, Input, Select, Space, Typography, Upload, message } from 'antd'
import { ArrowLeftOutlined, InboxOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import Guidance from './Guidance'
import { recordLabels } from './healthLabels'

const { Title, Paragraph, Text } = Typography

export default function ReportUpload() {
  useLanguage()
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [file, setFile] = React.useState(null)
  const [saving, setSaving] = React.useState(false)
  const [savedRecord, setSavedRecord] = React.useState(null)
  const [error, setError] = React.useState('')
  function chooseFile(next) {
    if (!/\.(pdf|png|jpe?g)$/i.test(next.name) || next.size > 10 * 1024 * 1024) {
      message.error(t('请选择不超过 10 MB 的 PDF、PNG 或 JPEG 文件。')); return Upload.LIST_IGNORE
    }
    setFile(next); setError('')
    if (!form.getFieldValue('title')) form.setFieldValue('title', next.name.replace(/\.[^.]+$/, '').slice(0, 160))
    return false
  }
  async function submit(values) {
    if (!file) { setError(t('请选择要保存的报告。')); return }
    setSaving(true); setError('')
    try {
      let record = savedRecord
      if (!record) {
        const response = await api.post('/records', { title: values.title, record_date: values.record_date.format('YYYY-MM-DD'), record_type: values.record_type, source_name: values.source_name || t('个人上传'), content: values.content?.trim() || t('个人上传的报告，原始内容请查看附件。') })
        record = response.data.record; setSavedRecord(record)
      }
      const payload = new FormData()
      payload.append('file', file); payload.append('version', record.version)
      await api.post(`/records/${record.id}/attachments`, payload, { headers: { 'Content-Type': 'multipart/form-data' } })
      message.success(t('原件已保存，自动整理结果可在详情中查看。'))
      navigate(`/records/${record.id}`)
    } catch (failure) { setError(apiMessage(failure)) }
    finally { setSaving(false) }
  }
  return <div className="page-stack upload-report-page">
    <Button className="inline-back" type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/records')}>{t("返回健康资料")}</Button>
    <div className="page-heading"><div><Text className="eyebrow">{t("报告与病历")}</Text><Title level={1}>{t("上传报告")}</Title><Paragraph>{t("保存原始文件后，系统自动整理全文并查找指标和健康信息。核对确认后才加入正式档案。")}</Paragraph></div></div>
    <div className="workflow-steps" aria-label={t("报告整理流程")}><span className="current">{t("1 · 保存原件")}</span><span>{t("2 · 核对识别信息")}</span><span>{t("3 · 查看健康解读")}</span></div>
    <Card>
      {error && <Alert type="error" showIcon title={t("未能完成保存")} description={error} style={{marginBottom: 20}} />}
      {savedRecord && <Alert type="info" showIcon title={t("记录已保存")} description={t("附件尚未上传完成。可在下方重试，或打开已保存的记录稍后继续。")} action={<Button onClick={() => navigate(`/records/${savedRecord.id}`)}>{t("打开记录")}</Button>} style={{marginBottom: 20}} />}
      <Form form={form} layout="vertical" initialValues={{record_date: dayjs(), record_type: 'Lab Report'}} onFinish={submit} disabled={saving}>
        <Upload.Dragger accept=".pdf,.png,.jpg,.jpeg" maxCount={1} beforeUpload={chooseFile} fileList={file ? [file] : []} onRemove={() => {setFile(null); return true}} disabled={saving}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p><p className="ant-upload-text">{t("拖入报告，或点击选择文件")}</p><p className="ant-upload-hint">{t("PDF、PNG 或 JPEG · 最多 10 MB")}</p>
        </Upload.Dragger>
        <div className="form-grid" style={{marginTop: 24}}><Form.Item name="title" label={t("报告名称")} rules={[{required: true, min: 2, max: 160}]}><Input placeholder={t("例如：九月体检报告")} disabled={Boolean(savedRecord)} /></Form.Item><Form.Item name="record_date" label={t("报告日期")} rules={[{required: true}]} extra={t("请核对原报告上的日期。")}><DatePicker className="full-width" disabled={Boolean(savedRecord)} /></Form.Item></div>
        <details className="quiet-details"><summary>{t("补充信息（可选）")}</summary><div className="form-grid"><Form.Item name="record_type" label={t("资料类型")}><Select disabled={Boolean(savedRecord)} options={['Lab Report','Visit Summary','Medication','Allergy','Imaging','Other'].map(value => ({value,label:recordLabels[value]}))} /></Form.Item><Form.Item name="source_name" label={t("医院或来源")}><Input maxLength={160} disabled={Boolean(savedRecord)} /></Form.Item></div><Form.Item name="content" label={t("个人备注")}><Input.TextArea rows={3} maxLength={30000} disabled={Boolean(savedRecord)} /></Form.Item></details>
        <div className="form-actions"><Button onClick={() => navigate('/records')}>{t("取消")}</Button><Button type="primary" htmlType="submit" loading={saving}>{savedRecord ? t('重试上传附件') : t('保存并自动整理')}</Button></div>
      </Form>
    </Card>
    <Guidance id="report-upload" title={t("系统会整理哪些信息？")}>{t("系统会建立可搜索的逐页文本，并识别支持的血压、血糖、心率及明确标注的健康信息。识别在本地运行，复杂表格、错字或未识别页可能需要人工核对；确认前不会写入正式健康档案。")}</Guidance>
    <Space wrap><Text type="secondary">{t("暂时没有报告？")}</Text><Button type="link" onClick={() => navigate('/records/new')}>{t("写健康记录")}</Button></Space>
  </div>
}
