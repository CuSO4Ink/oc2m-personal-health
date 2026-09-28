import { t, useLanguage } from './i18n'
import React from 'react'
import {
  ArrowLeftOutlined,
  EditOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, DatePicker, Descriptions, Empty, Form, Input, List, Modal, Pagination, Popconfirm, Select, Skeleton, Space, Tag, Timeline, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { apiMessage } from './api'
import { recordValue } from './recordDisplay'
import RecordAttachments from './RecordAttachments'
import HealthWorkspaceNav from './HealthWorkspaceNav'
import Guidance from './Guidance'
import HospitalSync from './HospitalSync'
import { recordLabels } from './healthLabels'

const { Title, Paragraph, Text } = Typography
const { RangePicker } = DatePicker
const fieldLabels = {get title() { return t("标题") },get record_type() { return t("资料类型") },get record_date() { return t("资料日期") },get source_name() { return t("来源") },get condition() { return t("疾病或主题") },get content() { return t("记录说明") }}
const actionLabels = {get record_created() { return t("新增资料") },get view() { return t("查看资料") },get edit() { return t("编辑资料") },get attachment_added() { return t("上传原件") },get attachment_view() { return t("预览原件") },get download() { return t("下载原件") },get attachment_deleted() { return t("删除附件") },get document_indexed() { return t("整理全文") },get record_classified() { return t("调整分类") },get record_imported() { return t("同步医院资料") },get report_extraction_prepared() { return t("识别候选信息") },get extraction_text_reviewed() { return t("校对识别文字") },get report_reading_confirmed() { return t("确认指标") },get health_fact_confirmed() { return t("确认健康信息") },get privacy_updated() { return t("更新隐私标记") },get archive() { return t("归档") },get restore() { return t("恢复资料") },get note_added() { return t("添加备注") },get correction_added() { return t("添加纠错申请") },get correction_response() { return t("模拟医院回复") }}
const sourceLabels = {get owner() { return t("本人") },get self() { return t("本人") },get system() { return t("系统整理") },get simulation() { return t("模拟医院") },get mock() { return t("模拟操作") }}
const recordTypes = ['Lab Report', 'Visit Summary', 'Medication', 'Allergy', 'Imaging', 'Other']

function displayDate(value, withTime = false) {
  if (!value) return t('未提供')
  return dayjs(value).format(withTime ? 'YYYY-MM-DD HH:mm' : 'YYYY-MM-DD')
}

function SourceTag({ record }) {
  useLanguage()
  return record.source_type === 'hospital'
    ? <Tag color="blue" icon={<SafetyCertificateOutlined />}>{t("模拟医院同步")}</Tag>
    : <Tag color="green">{t("个人录入")}</Tag>
}

function RecordTypeTag({ type }) {
  useLanguage()
  const colors = { 'Lab Report': 'cyan', 'Visit Summary': 'geekblue', Medication: 'purple', Allergy: 'volcano', Imaging: 'gold' }
  return <Tag color={colors[type]}>{recordLabels[type] || type}</Tag>
}

export function RecordsPage() {
  useLanguage()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [records, setRecords] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [conditions, setConditions] = React.useState([])
  const [showImports, setShowImports] = React.useState(searchParams.get('sync') === '1')
  const [pending, setPending] = React.useState([])
  const [filters, setFilters] = React.useState({ q: '', type: undefined, source: undefined, dates: null, condition: undefined, archived: 'active' })
  const [appliedFilters, setAppliedFilters] = React.useState(filters)
  const [pagination, setPagination] = React.useState({ page: 1, pageSize: 20, total: 0 })
  const requestSequence = React.useRef(0)

  async function loadRecords(nextFilters = filters, nextPage = 1, pageSize = pagination.pageSize) {
    const sequence = ++requestSequence.current
    setAppliedFilters(nextFilters); setLoading(true); setError('')
    setPagination((current) => ({ ...current, page: nextPage, pageSize }))
    try {
      const params = {
        q: nextFilters.q || undefined,
        type: nextFilters.type,
        source: nextFilters.source,
        condition: nextFilters.condition,
        archived: nextFilters.archived,
        from: nextFilters.dates?.[0]?.format('YYYY-MM-DD'),
        to: nextFilters.dates?.[1]?.format('YYYY-MM-DD'),
        page: nextPage,
        page_size: pageSize,
      }
      const response = await api.get('/records', { params })
      if (sequence !== requestSequence.current) return
      setRecords(response.data.records)
      setConditions(response.data.conditions || [])
      setPending(response.data.pending_records || [])
      setPagination({ page: response.data.page, pageSize: response.data.page_size, total: response.data.total })
    } catch (requestError) {
      if (sequence === requestSequence.current) setError(apiMessage(requestError))
    } finally { if (sequence === requestSequence.current) setLoading(false) }
  }

  React.useEffect(() => {
    let active = true
    const sequence = ++requestSequence.current
    api.get('/records', { params: { page: 1, page_size: 20 } }).then((response) => {
      if (active && sequence === requestSequence.current) {
        setRecords(response.data.records); setConditions(response.data.conditions || [])
        setPending(response.data.pending_records || [])
        setPagination({ page: response.data.page, pageSize: response.data.page_size, total: response.data.total })
      }
    }).catch((requestError) => {
      if (active && sequence === requestSequence.current) setError(apiMessage(requestError))
    }).finally(() => {
      if (active && sequence === requestSequence.current) setLoading(false)
    })
    return () => { active = false }
  }, [])

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function resetFilters() {
    const empty = { q: '', type: undefined, source: undefined, dates: null, condition: undefined, archived: 'active' }
    setFilters(empty); loadRecords(empty)
  }

  return <div className="page-stack records-page">
    <div className="page-heading">
      <div><Title level={1}>{t("健康资料")}</Title><Paragraph>{t("保存原件、按类查找，再把确认过的信息用于健康解读。")}</Paragraph></div>
      <Space wrap><Button onClick={() => navigate('/records/new')}>{t("写健康记录")}</Button><Button icon={<PlusOutlined />} onClick={() => navigate('/records/upload')}>{t("上传报告")}</Button><Button type="primary" onClick={() => setShowImports(true)}>{t("同步医院资料")}</Button></Space>
    </div>
    <HealthWorkspaceNav />
    {showImports && <HospitalSync onClose={() => setShowImports(false)} onImported={() => loadRecords(appliedFilters, pagination.page)} />}
    {pending.length > 0 && <details className="document-review"><summary>{t("待核对信息 · ")}{pending.length}{t(" 份资料")}</summary><Paragraph type="secondary">{t("识别出的指标和健康信息尚未加入正式档案。可以现在核对，也可以稍后处理。")}</Paragraph><List dataSource={pending} renderItem={(item) => <List.Item actions={[<Link key="review" to={`/records/${item.record_id}?review=1`}>{t("核对信息")}</Link>]}><List.Item.Meta title={recordValue(item, 'title')} description={t(`${item.extractions.reduce((sum, draft) => sum + draft.candidate_count, 0)} 条读数 · ${item.extractions.reduce((sum, draft) => sum + draft.fact_count, 0)} 条健康信息`)} /></List.Item>} /></details>}

    <Card className="filter-card">
      <div className="record-search-row"><Input allowClear value={filters.q} prefix={<SearchOutlined />} placeholder={t("搜索疾病、标题或 PDF 内容，输入部分名称即可")} onChange={(event) => updateFilter('q', event.target.value)} onPressEnter={() => loadRecords()} /><Button aria-label={t("搜索")} type="primary" onClick={() => loadRecords()}>{t("搜索")}</Button><Button onClick={resetFilters}>{t("清空筛选")}</Button></div>
      <details className="quiet-details"><summary>{t("按时间、类型、来源筛选")}{Object.entries(appliedFilters).some(([key,value]) => key !== 'q' && (key === 'archived' ? value !== 'active' : Boolean(value))) ? t(' · 已设置筛选') : ''}</summary><div className="record-filter-options">
        <label>{t("资料类型")}<Select allowClear aria-label={t("资料类型 filter")} value={filters.type} placeholder={t("全部类型")} options={recordTypes.map((value) => ({ value, label: recordLabels[value] }))} onChange={(value) => updateFilter('type', value)} /></label>
        <label>{t("来源")}<Select allowClear aria-label={t("来源筛选")} value={filters.source} placeholder={t("全部来源")} options={[{ value: 'hospital', label: t('模拟医院同步') }, { value: 'self', label: t('我上传或填写的资料') }]} onChange={(value) => updateFilter('source', value)} /></label>
        <label>{t("疾病或主题")}<Select allowClear showSearch aria-label={t("疾病筛选")} value={filters.condition} placeholder={t("全部疾病或主题")} options={conditions.map((value) => ({ value, label: value }))} onChange={(value) => updateFilter('condition', value)} /></label>
        <label>{t("状态")}<Select aria-label={t("归档筛选")} value={filters.archived} options={[{ value: 'active', label: t('使用中') }, { value: 'archived', label: t('已归档') }, { value: 'all', label: t('全部资料') }]} onChange={(value) => updateFilter('archived', value)} /></label>
        <label>{t("资料日期")}<RangePicker value={filters.dates} onChange={(value) => updateFilter('dates', value)} /></label>
      </div></details>
    </Card>

    {error && <Alert type="error" showIcon message={t("无法加载健康资料")} description={error} action={<Button onClick={() => loadRecords(appliedFilters, pagination.page)}>{t("重试")}</Button>} />}
    {loading ? <Card><Skeleton active paragraph={{ rows: 6 }} /></Card> : !error && <>
      <div className="results-heading"><Text strong>{pagination.total}{t(" 份资料 · ")}{records.length}{t(" 份在当前页")}</Text><Text type="secondary">{t("按资料日期从新到旧")}</Text></div>
      {records.length === 0 ? <Card><Empty description={<><b>{t("没有找到相关资料")}</b><br /><Text type="secondary">{t("可以同步医院资料、上传报告或写健康记录；设置过筛选时，也可以清空筛选再找。")}</Text></>}><Button type="primary" onClick={() => navigate('/records/upload')}>{t("上传报告")}</Button></Empty></Card> :
        <List className="records-list" dataSource={records} renderItem={(record) => <List.Item onClick={() => navigate(`/records/${record.id}`)} actions={[<Button key="view" type="link" onClick={(event) => { event.stopPropagation(); navigate(`/records/${record.id}`) }}>{t("查看详情")}</Button>]}>
          <List.Item.Meta
            avatar={<div className="record-icon"><FileTextOutlined /></div>}
            title={<Space wrap><span>{recordValue(record, 'title')}</span><RecordTypeTag type={record.record_type} /><SourceTag record={record} />{record.archived && <Tag>{t("已归档")}</Tag>}{record.sensitive && <Tag color="red">{t("敏感")}</Tag>}{record.search_match === 'approximate' && <Tag color="gold">{t("近似匹配")}</Tag>}</Space>}
            description={<><div className="record-list-details"><span>{recordValue(record, 'condition') || t('未填写疾病或主题')}</span><span>{t("资料日期：")}{displayDate(record.record_date)}</span><span>{t("来源：")}{recordValue(record, 'source_name')}</span>{record.attachments.length > 0 && <span>{record.attachments.length}{t(" 份文件")}</span>}</div>{(record.search_hits || []).map((hit, index) => <Link className="document-search-hit" key={`${hit.attachment_id}-${hit.page}-${index}`} to={hit.path} onClick={(event) => event.stopPropagation()}><Text strong>{hit.filename}{hit.page ? t(` · 第 ${hit.page} 页`) : t(' · 文件名匹配')}</Text><Text>{hit.snippet}</Text></Link>)}</>}
          />
        </List.Item>}/>
      }
      {pagination.total > 0 && <Pagination current={pagination.page} pageSize={pagination.pageSize} total={pagination.total} showSizeChanger pageSizeOptions={[10, 20, 50, 100]} onChange={(page, size) => loadRecords(appliedFilters, size === pagination.pageSize ? page : 1, size)} />}
    </>}
  </div>
}

export function RecordFormPage({ editing = false }) {
  useLanguage()
  const navigate = useNavigate()
  const { id } = useParams()
  const [form] = Form.useForm()
  const [record, setRecord] = React.useState(null)
  const [loading, setLoading] = React.useState(editing)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState('')
  const [conflict, setConflict] = React.useState(null)
  const [mergeChoices, setMergeChoices] = React.useState({})

  React.useEffect(() => {
    if (!editing) return
    api.get(`/records/${id}`).then(({ data }) => {
      setRecord(data.record)
      form.setFieldsValue({ ...data.record, record_date: dayjs(data.record.record_date) })
    }).catch((requestError) => setError(apiMessage(requestError))).finally(() => setLoading(false))
  }, [editing, form, id])

  async function submit(values) {
    if (conflict) return
    setSaving(true); setError('')
    const payload = { ...values, record_date: values.record_date.format('YYYY-MM-DD') }
    try {
      const response = editing
        ? await api.patch(`/records/${id}`, { ...payload, version: record.version })
        : await api.post('/records', payload)
      message.success(editing ? t('已保存新版本。') : t('健康记录已保存。'))
      navigate(`/records/${response.data.record.id}`)
    } catch (requestError) {
      setError(apiMessage(requestError))
      if (requestError.response?.status === 409 && requestError.response.data.record) {
        setConflict({ latest: requestError.response.data.record, draft: payload })
        setMergeChoices({})
      }
    } finally { setSaving(false) }
  }

  if (loading) return <div className="page-stack"><Card><Skeleton active /></Card></div>
  if (editing && !record) return <NavigateBack title={t("无法打开资料")} description={error} onBack={() => navigate('/records')} />
  if (editing && record && !record.is_editable) return <NavigateBack title={t("这条资料只读")} description={t("请先恢复归档资料。医院原件不能直接改写，可以调整分类或添加个人备注。")} onBack={() => navigate(`/records/${id}`)} />

  const fields = ['title', 'record_type', 'condition', 'record_date', 'source_name', 'content']
  const disputed = conflict ? fields.filter((key) => (conflict.draft[key] || '') !== (record[key] || '') && (conflict.latest[key] || '') !== (record[key] || '') && (conflict.draft[key] || '') !== (conflict.latest[key] || '')) : []
  function reloadLatest() {
    form.setFieldsValue({ ...conflict.latest, record_date: dayjs(conflict.latest.record_date), change_note: '' })
    setRecord(conflict.latest); setConflict(null); setError('')
  }
  function applyMerge() {
    const merged = { ...conflict.draft }
    fields.forEach((key) => {
      if ((conflict.draft[key] || '') === (record[key] || '') || mergeChoices[key] === 'latest') merged[key] = conflict.latest[key]
    })
    form.setFieldsValue({ ...merged, record_date: dayjs(merged.record_date) })
    setRecord(conflict.latest); setConflict(null); setError('')
    message.info(t('合并草稿已准备好，核对表单后可保存新版本。'))
  }

  return <div className="page-stack form-page">
    <Button className="inline-back" type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate(editing ? `/records/${id}` : '/records')}>{t("返回")}{editing ? t('资料详情') : t('健康资料')}</Button>
    <div><Title level={1}>{editing ? t('编辑健康记录') : t('写健康记录')}</Title><Paragraph>{editing ? t('保存后生成新版本，保留此前的信息。') : t('填写你自己管理的健康记录，也可以从健康资料页同步医院文件。')}</Paragraph></div>
    {error && <Alert type="error" showIcon message={t(error)} />}
    <Card>
      <Paragraph type="secondary">{t("保存后可以在详情页补充 PDF 或图片附件。")}</Paragraph>
      <Form form={form} layout="vertical" onFinish={submit} initialValues={{ record_type: 'Other', record_date: dayjs(), source_name: t('个人录入') }}>
        <div className="form-grid">
          <Form.Item label={t("记录标题")} name="title" rules={[{ required: true, min: 2, message: t('请填写记录标题') }]}><Input placeholder={t("例如：康复复诊记录")} /></Form.Item>
          <div><Form.Item label={t("资料类型")} name="record_type" rules={[{ required: true }]}><Select options={recordTypes.map((value) => ({ value, label: recordLabels[value] }))} /></Form.Item><Button onClick={async () => {
            try { const { data } = await api.post('/records/classify', form.getFieldsValue(['title', 'content'])); Modal.confirm({ title: t('Suggested category: {category}', { category: recordLabels[data.record_type] || data.record_type }), content: t(data.reason), okText: t('使用此分类'), onOk: () => form.setFieldValue('record_type', data.record_type) }) }
            catch (requestError) { message.error(apiMessage(requestError)) }
          }}>{t("建议分类")}</Button></div>
          <Form.Item label={t("资料日期")} name="record_date" rules={[{ required: true, message: t('请选择资料日期') }]}><DatePicker className="full-width" /></Form.Item>
          <Form.Item label={t("疾病或健康主题")} name="condition"><Input placeholder={t("可选，例如腰痛")} /></Form.Item>
          <Form.Item className="span-two" label={t("来源或记录人")} name="source_name" extra={t("可以注明信息由谁提供。")}><Input /></Form.Item>
          <Form.Item className="span-two" label={t("记录说明")} name="content" rules={[{ required: true, message: t('请填写记录说明') }]}><Input.TextArea rows={7} placeholder={t("记录检查发现、医生建议、用药剂量、反应等需要留存的信息。")} /></Form.Item>
          {editing && <Form.Item className="span-two" label={t("本次修改原因")} name="change_note" rules={[{ required: true, message: t('请简要说明修改内容') }]}><Input placeholder={t("例如：复诊后更新用药记录")} maxLength={240} showCount /></Form.Item>}
        </div>
        <div className="form-actions"><Button onClick={() => navigate(editing ? `/records/${id}` : '/records')}>{t("取消")}</Button><Button type="primary" htmlType="submit" disabled={Boolean(conflict)} loading={saving}>{editing ? t('保存新版本') : t('保存记录')}</Button></div>
      </Form>
    </Card>
    <Modal open={Boolean(conflict)} title={t("保存前请处理版本冲突")} closable={false} footer={<Space wrap><Button onClick={reloadLatest}>{t("放弃草稿，加载最新版本")}</Button><Button type="primary" disabled={disputed.some((key) => !mergeChoices[key])} onClick={applyMerge}>{t("应用合并结果")}</Button></Space>}>
      <Paragraph>{t("你的草稿已保留。请加载最新版本，或逐项核对合并后再保存。只在另一版本改变的字段会自动保留。")}</Paragraph>
      {conflict && fields.filter((key) => (conflict.draft[key] || '') !== (conflict.latest[key] || '')).map((key) => <Card key={key} size="small" title={fieldLabels[key] || key}>
        <Paragraph><Text strong>{t("你的草稿： ")}</Text>{conflict.draft[key] || t('（空）')}</Paragraph><Paragraph><Text strong>{t("最新版本： ")}</Text>{conflict.latest[key] || t('（空）')}</Paragraph>
        {disputed.includes(key) ? <Select aria-label={`Merge ${key}`} className="full-width" placeholder={t("选择要保留的内容")} value={mergeChoices[key]} onChange={(value) => setMergeChoices({ ...mergeChoices, [key]: value })} options={[{ value: 'draft', label: t('该字段保留我的草稿') }, { value: 'latest', label: t('该字段保留最新版本') }]} /> : <Text type="secondary">{t("修改没有冲突，将保留已更新内容。")}</Text>}
      </Card>)}
    </Modal>
  </div>
}

function NavigateBack({ title, description, onBack }) {
  useLanguage()
  return <div className="page-stack"><Alert type="info" showIcon message={title} description={description} action={<Button onClick={onBack}>{t("返回资料")}</Button>} /></div>
}

export function RecordDetailPage() {
  useLanguage()
  const navigate = useNavigate()
  const { id } = useParams()
  const [record, setRecord] = React.useState(null)
  const [error, setError] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [annotationForm] = Form.useForm()

  async function mutate(path, payload, method = 'patch') {
    setBusy(true)
    try {
      const { data } = await api[method](`/records/${id}/${path}`, payload)
      setRecord(data.record); message.success(t(data.message) || t('已保存。'))
      return true
    } catch (requestError) {
      message.error(apiMessage(requestError))
      if (requestError.response?.status === 409 && requestError.response.data.record) setRecord(requestError.response.data.record)
      return false
    } finally { setBusy(false) }
  }

  React.useEffect(() => { api.get(`/records/${id}`).then(({ data }) => setRecord(data.record)).catch((requestError) => setError(apiMessage(requestError))) }, [id])
  if (error) return <NavigateBack title={t("无法打开资料")} description={error} onBack={() => navigate('/records')} />
  if (!record) return <div className="page-stack"><Card><Skeleton active /></Card></div>

  return <div className="page-stack record-detail-page">
    <Button className="inline-back" type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate('/records')}>{t("返回健康资料")}</Button>
    <div className="page-heading">
      <div><Space wrap><RecordTypeTag type={record.record_type} /><SourceTag record={record} />{record.archived && <Tag>{t("已归档")}</Tag>}{record.sensitive && <Tag color="red">{t("敏感")}</Tag>}</Space><Title level={1}>{recordValue(record, 'title')}</Title><Paragraph>{recordValue(record, 'condition') || t('未填写疾病或主题')}</Paragraph></div>
      <Space wrap>{record.is_editable && <Button icon={<EditOutlined />} onClick={() => navigate(`/records/${id}/edit`)}>{t("编辑记录")}</Button>}<Button icon={<HistoryOutlined />} onClick={() => navigate(`/records/${id}/history`)}>{t("版本与活动历史")}</Button><Button disabled={record.archived || record.sensitive} onClick={() => navigate(`/sharing?record=${id}`)}>{t("共享资料")}</Button><Popconfirm title={record.archived ? t('恢复这条资料？') : t('归档这条资料？')} description={t("原件和历史会保留。归档期间停止共享；恢复后，未到期授权可能重新生效。需要永久停止时请撤销授权。")} onConfirm={() => mutate('archive', { version: record.version, archived: !record.archived })}><Button loading={busy}>{record.archived ? t('恢复') : t('归档')}</Button></Popconfirm></Space>
    </div>
    {record.source_type === 'hospital' && <Guidance id="provider-document" title={t("原件保留，分类可调整")}>{t("这份资料来自模拟医院。分类和疾病标签可以调整；原始 PDF 不会改变。个人备注不会发送到医院。")}</Guidance>}
    {record.archived && <Alert type="info" showIcon message={t("资料已归档")} description={t("原始内容、附件和历史仍可查阅。请先恢复后再编辑。")} />}
    <Card title={t("记录说明")}><Paragraph className="record-content">{recordValue(record, 'content')}</Paragraph></Card>
    <details className="quiet-details"><summary>{t("日期、来源与版本")}</summary><Card>
      <Descriptions column={{ xs: 1, sm: 2 }} items={[
        { key: 'date', label: t('资料日期'), children: displayDate(record.record_date) },
        { key: 'type', label: t('资料类型'), children: recordLabels[record.record_type] },
        { key: 'source', label: t('来源 / 记录人'), children: recordValue(record, 'source_name') },
        { key: 'sync', label: t('同步时间'), children: record.synced_at ? displayDate(record.synced_at, true) : t('非医院同步') },
        { key: 'updated', label: t('最近更新'), children: displayDate(record.updated_at, true) },
        { key: 'version', label: t('当前版本'), children: t(`版本 ${record.version}`) },
      ]} />
    </Card></details>
    <RecordAttachments record={record} onChange={setRecord} />
    {!record.archived && <details className="quiet-details"><summary>{t("调整个人分类与疾病标签")}</summary><Card><Paragraph type="secondary">{t("仅调整你查找资料时使用的分类和主题，不改变原始 PDF。")}</Paragraph><Form key={`classification-${record.version}`} layout="vertical" initialValues={{ record_type: record.record_type, condition: record.condition }} onFinish={(values) => mutate('classification', { ...values, version: record.version })}><div className="form-grid"><Form.Item name="record_type" label={t("资料分类")}><Select options={recordTypes.map((value) => ({ value, label: recordLabels[value] }))} /></Form.Item><Form.Item name="condition" label={t("疾病或主题")}><Input maxLength={120} /></Form.Item></div><Button htmlType="submit" loading={busy}>{t("保存分类")}</Button></Form></Card></details>}
    <details className="quiet-details"><summary>{t("隐私标记 · ")}{record.sensitive ? t('整条资料敏感') : record.sensitive_fields?.length ? t(`${record.sensitive_fields.length} 个敏感字段`) : t('仅自己可见，除非主动共享')}</summary><Card>
      <Guidance id="record-privacy" title={t("隐私标记如何影响共享")}>{t("敏感字段不会出现在后续共享中；含敏感字段时不开放完整原件。删除标记后未到期授权可能重新可用，永久停止请撤销授权。个人备注保持私密。")}</Guidance>
      <Form key={record.version} layout="vertical" initialValues={{ sensitive: record.sensitive, sensitive_fields: record.sensitive_fields || [] }} onFinish={(values) => mutate('privacy', { ...values, version: record.version })}>
        <Form.Item name="sensitive" valuePropName="checked"><Checkbox>{t("整条资料设为敏感")}</Checkbox></Form.Item>
        <Form.Item name="sensitive_fields" label={t("敏感字段")}><Select mode="multiple" options={['title', 'record_type', 'record_date', 'source_name', 'condition', 'content'].map((value) => ({ value, label: fieldLabels[value] || value }))} /></Form.Item>
        <Button htmlType="submit" loading={busy}>{t("保存隐私标记")}</Button>
      </Form>
    </Card></details>
    <details className="quiet-details"><summary>{t("个人备注与纠错申请 (")}{record.annotations?.length || 0})</summary><Card>
      <Paragraph>{t("只保存到你的账号。可以模拟机构回复来演示处理流程，不会向真实医院发送申请。")}</Paragraph>
      <Form form={annotationForm} layout="vertical" initialValues={{ kind: 'note' }} onFinish={async (values) => { if (await mutate('annotations', values, 'post')) annotationForm.resetFields(['content']) }}>
        <Form.Item name="kind" label={t("内容类型")}><Select options={[{ value: 'note', label: t('个人备注') }, { value: 'correction', label: t('本地纠错申请') }]} /></Form.Item>
        <Form.Item name="content" label={t("内容")} rules={[{ required: true, min: 3, max: 2000 }]}><Input.TextArea rows={3} maxLength={2000} showCount /></Form.Item>
        <Button type="primary" htmlType="submit" loading={busy}>{t("保存")}</Button>
      </Form>
      <List dataSource={record.annotations || []} locale={{ emptyText: t('尚无个人备注或纠错申请。') }} renderItem={(item) => <List.Item actions={item.kind === 'correction' && item.status === 'awaiting_review' ? [<Button key="simulate" disabled={busy} onClick={() => mutate(`annotations/${item.id}/simulate-response`, {}, 'post')}>{t("模拟医院回复")}</Button>] : []}>
        <List.Item.Meta title={<Space wrap><Tag>{item.kind === 'correction' ? t('纠错申请') : t('个人备注')}</Tag><Tag>{{saved:t('已保存'),awaiting_review:t('待回复'),resolved:t('已回复'),closed:t('已关闭')}[item.status] || item.status}</Tag><Text type="secondary">{displayDate(item.created_at, true)}</Text></Space>} description={<><Paragraph>{recordValue(item, 'content')}</Paragraph>{item.response && <Alert type="info" message={t(item.response)} />}</>} />
      </List.Item>} />
    </Card></details>
  </div>
}

export function RecordHistoryPage() {
  useLanguage()
  const navigate = useNavigate()
  const { id } = useParams()
  const [versions, setVersions] = React.useState(null)
  const [events, setEvents] = React.useState([])
  const [error, setError] = React.useState('')

  React.useEffect(() => { api.get(`/records/${id}/history`).then(({ data }) => { setVersions(data.versions); setEvents(data.events || []) }).catch((requestError) => setError(apiMessage(requestError))) }, [id])
  return <div className="page-stack history-page">
    <Button className="inline-back" type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate(`/records/${id}`)}>{t("返回资料")}</Button>
    <div><Title level={1}>{t("版本与活动历史")}</Title><Paragraph>{t("查看资料何时变化、由谁操作，以及每个版本保存的内容。")}</Paragraph></div>
    {error && <Alert type="error" showIcon message={t(error)} />}
    {!versions && !error ? <Card><Skeleton active /></Card> : versions && <Card><Timeline items={versions.map((item, index) => ({
      color: index === 0 ? 'green' : 'gray',
      children: <div className="version-item"><Space><Text strong>{t("版本 ")}{item.version}</Text>{index === 0 && <Tag color="green">{t("当前")}</Tag>}</Space><Text>{t(item.change_note)}</Text><Text type="secondary">{item.changed_by} · {displayDate(item.created_at, true)}</Text><details><summary>{t("查看该版本信息")}</summary><Descriptions size="small" column={1} items={[
        { key: 'title', label: t('标题'), children: recordValue(item.snapshot, 'title') },
        { key: 'type', label: t('类型'), children: recordLabels[item.snapshot.record_type] },
        { key: 'condition', label: t('疾病或主题'), children: recordValue(item.snapshot, 'condition') || t('（空）') },
        { key: 'date', label: t('资料日期'), children: displayDate(item.snapshot.record_date) },
        { key: 'source', label: t('来源'), children: recordValue(item.snapshot, 'source_name') },
        { key: 'content', label: t('内容'), children: recordValue(item.snapshot, 'content') },
      ]} /></details><details><summary>{t("与上一版本比较 (")}{item.changes?.length || 0}{t(" 个字段变化)")}</summary>{(item.changes || []).map((change) => <div key={change.field}><Text strong>{fieldLabels[change.field] || change.field}</Text><Paragraph type="secondary">{t("修改前： ")}{change.before ?? t('（原先没有）')}</Paragraph><Paragraph>{t("修改后： ")}{change.after ?? t('（空）')}</Paragraph></div>)}</details></div>,
    }))} /></Card>}
    {versions && <Card title={t("资料与附件活动")}><Paragraph type="secondary">{t("删除附件后，文件名等操作记录仍会保留。模拟操作单独标明。")}</Paragraph><List dataSource={events} locale={{ emptyText: t('这条旧资料尚无活动记录。') }} renderItem={(event) => <List.Item><List.Item.Meta title={<Space wrap><Text strong>{actionLabels[event.action] || event.action.replaceAll('_', ' ')}</Text><Tag>{sourceLabels[event.source] || event.source}</Tag></Space>} description={<>{['system', 'simulation', 'mock'].includes(event.source) ? t(event.actor_name) : event.actor_name} · {displayDate(event.created_at, true)}{event.details.filename && <Paragraph>{event.details.filename} · {event.details.size ?? ''}{t(" bytes")}</Paragraph>}{event.details.changed_fields && <Paragraph>{t("变更： ")}{event.details.changed_fields.map((field) => fieldLabels[field] || field).join(', ') || t('无文字变更')}</Paragraph>}</>} /></List.Item>} /></Card>}
  </div>
}
