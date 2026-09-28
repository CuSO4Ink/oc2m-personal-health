import { t, useLanguage } from './i18n'
import React from 'react'
import { Alert, Button, Card, Checkbox, DatePicker, Descriptions, Form, Input, List, Modal, Select, Skeleton, Space, Tag, Typography, message } from 'antd'
import { Link } from 'react-router-dom'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import { useAuth } from './auth'
import Guidance from './Guidance'
import HealthWorkspaceNav from './HealthWorkspaceNav'
import './PersonalWorkspace.css'

const { Title, Paragraph, Text } = Typography
const sections = [
  { key: 'past_history', get label() { return t("既往病史") }, get short() { return t("既往病史") }, get name() { return t("疾病或手术名称") }, get hint() { return t("记录以前患过的疾病、手术或其他重要经历。") }, fields: [['start_date', '发病或诊断日期', 'date'], ['end_date', '结束日期', 'date'], ['detail', '情况与备注']] },
  { key: 'family_history', get label() { return t("家族病史") }, get short() { return t("家族病史") }, get name() { return t("疾病名称") }, get hint() { return t("记录家人患过的疾病和亲属关系。") }, fields: [['relationship', '亲属关系'], ['detail', '已知情况']] },
  { key: 'medications', get label() { return t("用药情况") }, get short() { return t("用药情况") }, get name() { return t("药品或补充剂名称") }, get hint() { return t("按已有医嘱记录用药情况，填写内容不会生成新的用药建议。") }, fields: [['dose', '医嘱剂量'], ['frequency', '医嘱频次'], ['start_date', '开始日期', 'date'], ['end_date', '结束日期', 'date'], ['detail', '开具医生与备注']] },
  { key: 'allergies', get label() { return t("过敏情况") }, get short() { return t("过敏情况") }, get name() { return t("过敏原名称") }, get hint() { return t("记录已知过敏原和发生过的反应。") }, fields: [['severity', '严重程度（如已知）'], ['detail', '过敏反应与情况']] },
]
const statusLabel = (status) => status === 'none' ? t('明确无已知情况') : status === 'recorded' ? t('已有记录') : t('尚未填写或不确定')
const blankEntry = () => ({ id: crypto.randomUUID(), name: '', sensitive: false })
const emptySection = () => ({ status: 'unknown', items: [] })
function draftText(section, draft) {
  if (!section || !draft) return ''
  return [section.label, t('Status: {status}', {status: statusLabel(draft.status)}), ...draft.items.map((item, index) => ['\n' + t('Entry {number}: {name}', {number: index + 1, name: item.name || t('Name not entered')}), ...section.fields.filter(([field]) => item[field]).map(([field, label]) => `${t(label)}: ${item[field]}`), t('Sensitive: {value}', {value: item.sensitive ? t('Yes') : t('No')})].join('\n'))].join('\n')
}

function EntrySummary({ item, section, sources = [] }) {
  useLanguage()
  const facts = section.fields.filter(([field]) => item[field])
  return <div className="history-entry-summary"><Space wrap><Text strong>{item.name}</Text>{item.sensitive && <Tag>{t("敏感信息")}</Tag>}</Space>
    {facts.length > 0 && <details className="history-entry-details"><summary>{t("查看详情")}</summary><div className="history-entry-facts">{facts.map(([field, label]) => <Text key={field} type="secondary"><b>{t(label)}: </b>{item[field]}</Text>)}</div></details>}
    {sources.filter((source) => source.section === section.key && source.profile_item_id === item.id).map((source) => <div className="history-source" key={source.id}><Tag color="blue">{source.linked_existing ? t('报告关联既有条目') : t('报告核对后加入')}</Tag><Link to={source.review_path || source.record_path}>{t("查看报告依据")}{source.page ? t(` · 第 ${source.page} 页`) : ''}</Link>{source.current_item_matches === false && <Text type="secondary">{t("此条目后来有过修改，来源保留原确认内容。")}</Text>}</div>)}
  </div>
}

export default function HealthProfile() {
  useLanguage()
  const { refresh: refreshAuth } = useAuth()
  const [account, setAccount] = React.useState(null)
  const [basicOpen, setBasicOpen] = React.useState(false)
  const [basicSaving, setBasicSaving] = React.useState(false)
  const [basicForm] = Form.useForm()
  const [sources, setSources] = React.useState([])
  const [sourceError, setSourceError] = React.useState(false)
  const [profile, setProfile] = React.useState(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [editing, setEditing] = React.useState(null)
  const [draft, setDraft] = React.useState(null)
  const [dirty, setDirty] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [saveError, setSaveError] = React.useState('')
  const [conflict, setConflict] = React.useState(null)
  const [conflictOpen, setConflictOpen] = React.useState(false)
  const [historyOpen, setHistoryOpen] = React.useState(false)
  const [history, setHistory] = React.useState(null)
  const [historyError, setHistoryError] = React.useState('')
  React.useEffect(() => {
    let active = true
    api.get('/account').then(({ data }) => { if (active && data.user) setAccount(data) }).catch(() => {})
    api.get('/extractions/profile-provenance').then(({ data }) => { if (active) setSources(data.sources || []) }).catch(() => { if (active) setSourceError(true) })
    api.get('/records/profile').then(({ data }) => { if (active) setProfile(data.profile) })
      .catch((failure) => { if (active) setError(apiMessage(failure)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  React.useEffect(() => {
    function warn(event) { if (dirty) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  function openEditor(section) {
    const saved = profile.sections[section.key] || emptySection()
    setEditing(section)
    setDraft(saved.status === 'unknown' ? {status: 'recorded', items: [blankEntry()]} : structuredClone(saved))
    setDirty(false); setSaveError(''); setConflict(null); setConflictOpen(false)
  }
  function closeEditor() {
    if (saving) return
    const close = () => { setEditing(null); setDraft(null); setDirty(false); setSaveError(''); setConflict(null) }
    if (dirty) Modal.confirm({title: t('放弃尚未保存的修改？'), content: t('已保存的信息不受影响。'), okText: t('放弃修改'), onOk: close})
    else close()
  }
  function updateDraft(next) { setDraft(next); setDirty(true); setSaveError('') }
  function updateItem(index, field, value) { updateDraft({...draft, items: draft.items.map((item, row) => row === index ? {...item, [field]: value} : item)}) }
  function changeStatus(status) {
    const apply = () => updateDraft({status, items: status === 'recorded' ? (draft.items.length ? draft.items : [blankEntry()]) : []})
    if (status !== 'recorded' && draft.items.some((item) => item.name.trim())) Modal.confirm({title: t('将本类记录改为该状态？'), content: t('保存后仅更新当前类别，旧内容仍保留在修改历史。'), okText: t('修改状态'), onOk: apply})
    else apply()
  }
  async function save() {
    if (saving || conflict) return
    if (draft.status === 'recorded' && (!draft.items.length || draft.items.some((item) => !item.name?.trim()))) { setSaveError(t('请填写每项名称，或选择明确无已知情况／不确定。')); return }
    setSaving(true); setSaveError('')
    try {
      const { data } = await api.put('/records/profile', {revision: profile.revision, sections: {...profile.sections, [editing.key]: draft}})
      setProfile(data.profile); refreshSources(); setDirty(false); setEditing(null); setDraft(null); message.success(t(`${editing.short}已保存。`))
    } catch (failure) {
      setSaveError(apiMessage(failure))
      if (failure.response?.status === 409) { setConflict(failure.response.data.profile); setConflictOpen(true) }
    } finally { setSaving(false) }
  }
  async function refreshSources() {
    try { const { data } = await api.get('/extractions/profile-provenance'); setSources(data.sources || []); setSourceError(false) }
    catch { setSources([]); setSourceError(true) }
  }
  async function openHistory() {
    setHistoryOpen(true); setHistory(null); setHistoryError('')
    try { const { data } = await api.get('/records/profile/history'); setHistory(data.revisions) }
    catch (failure) { setHistoryError(apiMessage(failure)) }
  }
  function editBasic() {
    basicForm.setFieldsValue({full_name: account.user.full_name, phone: account.profile.phone, date_of_birth: account.profile.date_of_birth ? dayjs(account.profile.date_of_birth) : null})
    setBasicOpen(true)
  }
  async function saveBasic(values) {
    setBasicSaving(true)
    try {
      const { data } = await api.patch('/account/profile', {...values, date_of_birth: values.date_of_birth?.format('YYYY-MM-DD') || null, preferred_language: account.profile.preferred_language})
      setAccount(data); setBasicOpen(false); await refreshAuth?.(); message.success(t('基础信息已保存。'))
    } catch (failure) { message.error(apiMessage(failure)) }
    finally { setBasicSaving(false) }
  }

  return <div className="page-stack personal-history">
    <Modal title={t("编辑基础信息")} open={basicOpen} onCancel={() => !basicSaving && setBasicOpen(false)} footer={null} destroyOnHidden><Form form={basicForm} layout="vertical" onFinish={saveBasic}><Form.Item name="full_name" label={t("姓名")} rules={[{required: true, min: 2, max: 100, message: t('请填写 2–100 个字符的姓名')}]}><Input autoComplete="name" /></Form.Item><Form.Item name="date_of_birth" label={t("出生日期")}><DatePicker style={{width: '100%'}} disabledDate={(value) => value && !value.isBefore(dayjs(), 'day')} /></Form.Item><Form.Item name="phone" label={t("联系电话")}><Input maxLength={40} autoComplete="tel" /></Form.Item><Space><Button onClick={() => setBasicOpen(false)} disabled={basicSaving}>{t("取消")}</Button><Button type="primary" htmlType="submit" loading={basicSaving}>{t("保存基础信息")}</Button></Space></Form></Modal>
    <HealthWorkspaceNav />
    <div className="page-heading"><div><Title level={1}>{t("个人健康信息")}</Title><Paragraph>{t("基础信息、既往病史、家族病史、用药和过敏，在这里按类补充。")}</Paragraph></div><Button disabled={!profile || loading} onClick={openHistory}>{t("修改历史")}</Button></div>
    {account ? <Card className="profile-basics" title={t("基础信息")} extra={<Button onClick={editBasic}>{t("编辑基础信息")}</Button>}><Descriptions column={{xs: 1, sm: 1, md: 3}} items={[{key: 'name', label: t('姓名'), children: account.user.full_name}, {key: 'birth', label: t('出生日期'), children: account.profile.date_of_birth || t('尚未填写')}, {key: 'phone', label: t('联系电话'), children: account.profile.phone || t('尚未填写')}]} /></Card> : <div className="history-account-link"><Text type="secondary">{t("姓名与出生日期")}</Text><Link to="/account">{t("管理基础信息")}</Link></div>}
    {sourceError && <Text type="secondary">{t("报告来源暂未加载，已保存的健康信息仍可查看。")}</Text>}
    {loading ? <Card><Skeleton active paragraph={{ rows: 6 }} /></Card> : !profile ? <Alert type="error" showIcon message={t("个人健康信息加载失败")} description={error} action={<Button onClick={() => window.location.reload()}>{t("重新加载")}</Button>} /> : <>
      <div className="history-summary-grid">{sections.map((section) => {
        const saved = profile.sections[section.key] || emptySection()
        return <Card key={section.key} className="history-summary-card"><div className="history-summary-heading"><Title level={3}>{section.short}</Title><Button aria-label={`${saved.status === 'unknown' ? t('添加') : t('编辑')} ${section.label}`} onClick={() => openEditor(section)}>{saved.status === 'unknown' ? t('添加') : t('编辑')}</Button></div>
          <Tag>{statusLabel(saved.status)}</Tag>
          {saved.status === 'recorded' ? <><div className="history-summary-entries">{saved.items.slice(0, 2).map((item, index) => <EntrySummary key={item.id || index} item={item} section={section} sources={sources} />)}</div>{saved.items.length > 2 && <details className="history-more-entries"><summary>{t("展开其余 ")}{saved.items.length - 2}{t(" 项")}</summary>{saved.items.slice(2).map((item, index) => <EntrySummary key={item.id || index} item={item} section={section} sources={sources} />)}</details>}</> : <Paragraph type="secondary">{saved.status === 'none' ? t('你已明确填写无已知情况。') : t('还没有填写，不代表不存在相关情况。')}</Paragraph>}
        </Card>
      })}</div>
      <Text type="secondary">{t("已保存版本 ")}{profile.revision} · {profile.updated_at ? new Date(profile.updated_at).toLocaleString() : t('尚未保存')}</Text>
    </>}
    <Guidance id="health-history" title={t("如何填写与使用这些信息")}><Paragraph>{t("不确定表示尚未记录或不了解；明确无已知情况则是你的主动确认。用药情况记录已有医嘱，不会推荐剂量。")}</Paragraph><Paragraph>{t("报告提取的信息经你核对后才会合入。共享时可以选择具体内容；健康信息不会自动发布到社区。旧版本可在修改历史中查看。")}</Paragraph></Guidance>

    <Modal className="history-editor" width={700} title={editing?.label} open={Boolean(editing)} onCancel={closeEditor} mask={{closable: false}} destroyOnHidden footer={<Space><Button disabled={saving} onClick={closeEditor}>{t("取消")}</Button><Button type="primary" loading={saving} disabled={!dirty || Boolean(conflict)} onClick={save}>{t("保存本类信息")}</Button></Space>}>
      {editing && draft && <><Paragraph type="secondary">{editing.hint}</Paragraph><label className="history-status-label">{t("记录状态")}<Select aria-label={t(`${editing.label}记录状态`)} value={draft.status} disabled={saving} onChange={changeStatus} options={[{value: 'recorded', label: t('填写具体记录')}, {value: 'none', label: t('明确无已知情况')}, {value: 'unknown', label: t('不确定或尚未填写')}]} /></label>
        {saveError && <Alert type="error" showIcon message={saveError} action={conflict && <Button onClick={() => setConflictOpen(true)}>{t("查看冲突")}</Button>} />}
        {draft.status !== 'recorded' ? <Paragraph className="history-status-note">{draft.status === 'none' ? t('保存后表示你明确确认暂无已知情况。') : t('保存后表示此类情况尚不确定，不作健康结论。')}</Paragraph> : <div className="history-editor-entries">{draft.items.map((item, index) => <Card key={item.id} size="small" title={t(`第 ${index + 1} 项`)} extra={<Button type="text" danger disabled={saving} onClick={() => { const items = draft.items.filter((_, row) => row !== index); updateDraft({status: items.length ? 'recorded' : 'unknown', items}) }}>{t("移除")}</Button>}>
          <div className="history-editor-fields"><label htmlFor={`history-name-${index}`}>{editing.name}<Input id={`history-name-${index}`} aria-label={`${editing.label} ${editing.name} ${index + 1}`} required value={item.name || ''} maxLength={160} disabled={saving} onChange={(event) => updateItem(index, 'name', event.target.value)} /></label>
          {editing.fields.map(([field, label, type]) => <label key={field} htmlFor={`history-${field}-${index}`}>{t(label)}<Input id={`history-${field}-${index}`} aria-label={`${editing.label} ${t(label)} ${index + 1}`} type={type || 'text'} value={item[field] || ''} maxLength={1000} disabled={saving} onChange={(event) => updateItem(index, field, event.target.value)} /></label>)}</div><Checkbox disabled={saving} checked={Boolean(item.sensitive)} onChange={(event) => updateItem(index, 'sensitive', event.target.checked)}>{t("标记为敏感个人信息")}</Checkbox>
        </Card>)}<Button disabled={saving || draft.items.length >= 100} onClick={() => updateDraft({...draft, items: [...draft.items, blankEntry()]})}>{t("再添加一项")}</Button></div>}
      </>}
    </Modal>
    <Modal open={conflictOpen} title={t("健康信息已在其他页面更新")} onCancel={() => setConflictOpen(false)} footer={<Space wrap><Button onClick={() => setConflictOpen(false)}>{t("返回我的草稿")}</Button><Button type="primary" onClick={() => { setProfile(conflict); refreshSources(); setConflict(null); setConflictOpen(false); setEditing(null); setDraft(null); setDirty(false); setSaveError('') }}>{t("放弃草稿，加载最新版本")}</Button></Space>}>
      <Paragraph>{t("草稿仍被保留。为防止覆盖新版本，当前不能再次保存；加载最新版本前可以复制需要保留的内容。")}</Paragraph><Input.TextArea aria-label={t("尚未保存的草稿")} readOnly rows={10} value={draftText(editing, draft)} />
    </Modal>
    <Modal open={historyOpen} title={t("健康信息修改历史")} width={850} onCancel={() => setHistoryOpen(false)} footer={<Button onClick={() => setHistoryOpen(false)}>{t("关闭")}</Button>}>
      <Paragraph>{t("已保存的历史版本仅供本人查看。移除当前条目不会删除旧版本，未保存的草稿不在其中。")}</Paragraph>
      {historyError && <Alert type="error" message={historyError} action={<Button onClick={openHistory}>{t("重试")}</Button>} />}
      {!history && !historyError && <Skeleton active />}
      {history && <List dataSource={history} locale={{emptyText: t('暂无修改历史。')}} renderItem={(revision) => <List.Item><div className="full-width"><Space wrap><Text strong>{t("版本 ")}{revision.revision}</Text><Text type="secondary">{revision.created_at ? new Date(revision.created_at).toLocaleString() : t('时间未知')} · {revision.actor_name}</Text></Space>
        {revision.snapshot ? <details><summary>{t("查看当时保存的内容")}</summary>{sections.map((section) => {
          const saved = revision.snapshot[section.key] || emptySection()
          return <Card key={section.key} size="small" title={section.label} extra={<Tag>{statusLabel(saved.status)}</Tag>}>
            {saved.items.map((item, index) => <Descriptions key={item.id || index} size="small" column={1} title={item.name} items={[...section.fields.filter(([field]) => item[field]).map(([field, label]) => ({key: field, label: t(label), children: item[field]})), {key: 'sensitive', label: t('敏感信息'), children: item.sensitive ? t('是') : t('否')}]} />)}
            {!saved.items.length && <Text type="secondary">{saved.status === 'none' ? t('明确记录为无已知情况。') : t('尚未记录确定结论。')}</Text>}
          </Card>
        })}</details> : <Text type="secondary">{t("此旧记录仅保留了版本号，没有内容快照。")}</Text>}
      </div></List.Item>} />}
    </Modal>
  </div>
}
