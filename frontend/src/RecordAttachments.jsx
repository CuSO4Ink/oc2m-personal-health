import React from 'react'
import { Button, Card, Empty, List, Modal, Popconfirm, Space, Typography, Upload, message } from 'antd'
import { DeleteOutlined, DownloadOutlined, EyeOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'

const { Paragraph, Text } = Typography
const sizeLabel = (size) => size < 1024 * 1024 ? `${Math.ceil(size / 1024)} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`

export default function RecordAttachments({ record, onChange }) {
  const [uploading, setUploading] = React.useState(false)
  const [deleting, setDeleting] = React.useState(null)
  const [preview, setPreview] = React.useState(null)
  const url = (attachment) => `/api/records/${record.id}/attachments/${attachment.id}`

  async function upload({ file, onSuccess, onError }) {
    setUploading(true)
    const payload = new FormData()
    payload.append('file', file)
    try {
      const { data } = await api.post(`/records/${record.id}/attachments`, payload, { headers: { 'Content-Type': 'multipart/form-data' } })
      onChange(data.record); onSuccess(data)
      message.success('Attachment saved.')
    } catch (error) { message.error(apiMessage(error)); onError(error) }
    finally { setUploading(false) }
  }

  async function remove(attachment) {
    setDeleting(attachment.id)
    try {
      const { data } = await api.delete(`/records/${record.id}/attachments/${attachment.id}`)
      onChange(data.record); message.success('Attachment deleted.')
    } catch (error) { message.error(apiMessage(error)) }
    finally { setDeleting(null) }
  }

  function validate(file) {
    if (file.size > 10 * 1024 * 1024) { message.error('Each attachment must be 10 MB or smaller.'); return Upload.LIST_IGNORE }
    if (!/\.(pdf|png|jpe?g)$/i.test(file.name)) { message.error('Choose a PDF, PNG or JPEG file.'); return Upload.LIST_IGNORE }
    return true
  }

  return <Card title={`Attachments (${record.attachments.length}/10)`} extra={record.is_editable && <Upload accept=".pdf,.png,.jpg,.jpeg" showUploadList={false} beforeUpload={validate} customRequest={upload} disabled={uploading || record.attachments.length >= 10}><Button icon={<UploadOutlined />} loading={uploading} disabled={record.attachments.length >= 10}>Upload document</Button></Upload>}>
    <Paragraph type="secondary">PDF, PNG or JPEG · Up to 10 MB each. Save reports, prescriptions or images alongside this record. Attachments are managed separately from text version history and are not included in the current sharing permissions.</Paragraph>
    {record.attachments.length ? <List dataSource={record.attachments} renderItem={(attachment) => <List.Item className="attachment-item" actions={[
      <Button key="preview" icon={<EyeOutlined />} onClick={() => setPreview(attachment)}>Preview</Button>,
      <Button key="download" icon={<DownloadOutlined />} href={`${url(attachment)}?download=1`}>Download</Button>,
      ...(record.is_editable ? [<Popconfirm key="delete" title="Delete this attachment?" description="The uploaded file will be permanently removed." onConfirm={() => remove(attachment)} okText="Delete" okButtonProps={{ danger: true }}><Button danger icon={<DeleteOutlined />} loading={deleting === attachment.id} disabled={uploading || deleting !== null}>Delete</Button></Popconfirm>] : []),
    ]}><List.Item.Meta title={attachment.filename} description={`${sizeLabel(attachment.size)} · Uploaded ${dayjs(attachment.created_at).format('D MMM YYYY, HH:mm')}`} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No attachments yet" />}
    {!record.is_editable && <Text type="secondary">Original provider attachments cannot be changed.</Text>}
    <Modal title={preview?.filename} open={Boolean(preview)} onCancel={() => setPreview(null)} footer={<Space><Button onClick={() => setPreview(null)}>Close</Button>{preview && <Button icon={<DownloadOutlined />} href={`${url(preview)}?download=1`}>Download</Button>}</Space>} width={960} destroyOnHidden>
      {preview && <><Paragraph type="secondary">If your browser cannot display this file, download it to view locally.</Paragraph>{preview.content_type === 'application/pdf' ? <iframe className="attachment-pdf" title={preview.filename} src={url(preview)} /> : <img className="attachment-image" alt={preview.filename} src={url(preview)} />}</>}
    </Modal>
  </Card>
}
