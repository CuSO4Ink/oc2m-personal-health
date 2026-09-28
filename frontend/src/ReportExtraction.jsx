import { t, useLanguage } from './i18n'
import React from 'react'
import { Alert, Button, Checkbox, Collapse, DatePicker, Input, InputNumber, Modal, Select, Space, Spin, Table, Tabs, Tag, Typography, message } from 'antd'
import { Link } from 'react-router-dom'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'
import { recordValue } from './recordDisplay'
import { metricLabels, sectionLabels } from './healthLabels'
import './ReportReview.css'

const { Paragraph, Text } = Typography
const contexts = { blood_glucose: [['fasting','空腹'],['after_meal','餐后'],['random','随机']], heart_rate: [['resting','静息'],['exercise','运动后'],['unknown','未确认场景']] }
const specials = [['general','一般情况'],['pregnancy','孕期'],['individual_target','个人医疗目标'],['unknown','不确定']]
const options = (items) => items.map(([value,label]) => ({value,label:t(label)}))
const fieldLabels = {get detail() { return t("备注 / 反应") },get relationship() { return t("亲属关系") },get dose() { return t("剂量") },get frequency() { return t("频次") },get severity() { return t("严重程度") },get start_date() { return t("开始 / 确诊日期") },get end_date() { return t("结束日期") }}
const factFields = {past_history:['start_date','end_date','detail'],family_history:['relationship','detail'],medications:['dose','frequency','start_date','end_date','detail'],allergies:['detail','severity']}

export default function ReportExtraction(props) {
  useLanguage()
  if (!props.open) return null
  return <ExtractionReview key={`${props.record.id}:${props.attachment?.id || 'text'}:${props.extractionId || 'new'}`} {...props} />
}

function ExtractionReview({record, attachment=null, extractionId=null, onClose, onImported}) {
  useLanguage()
  const [capabilities,setCapabilities]=React.useState(null), [language,setLanguage]=React.useState('auto')
  const [busy,setBusy]=React.useState(false), [loading,setLoading]=React.useState(Boolean(extractionId))
  const [error,setError]=React.useState(''), [conflict,setConflict]=React.useState(false)
  const [draft,setDraft]=React.useState(null), [text,setText]=React.useState('')
  const [rows,setRows]=React.useState([]), [facts,setFacts]=React.useState([])
  const [acknowledged,setAcknowledged]=React.useState(false), [bulkDate,setBulkDate]=React.useState(null), [result,setResult]=React.useState(null)
  function applyDraft(value) {
    setDraft(value); setText(value.reviewed_text); setConflict(false); setAcknowledged(false)
    setRows(value.candidates.map((item)=>({...item,selected:false,measured_at:item.measured_at && dayjs(item.measured_at).isValid()?dayjs(item.measured_at):null,special_context:'general'})))
    setFacts((value.facts||[]).map((item)=>({...item,...(item.confirmed_values||{}),id:item.id,selected:false})))
  }
  React.useEffect(()=>{
    let active=true
    api.get('/extractions/capabilities').then(({data})=>{if(active)setCapabilities(data)}).catch(()=>{})
    if(extractionId)api.get(`/extractions/${extractionId}`).then(({data})=>{
      if(!active)return
      if(data.extraction.record_id!==record.id)throw new Error(t('待确认内容不属于当前档案。'))
      applyDraft(data.extraction)
    }).catch((err)=>{if(active)setError(err.response?apiMessage(err):err.message)}).finally(()=>{if(active)setLoading(false)})
    return()=>{active=false}
  },[extractionId,record.id])
  const selected=rows.filter((item)=>item.selected&&!item.existing_measurement_id), selectedFacts=facts.filter((item)=>item.selected&&!item.existing_profile_item_id)
  const count=selected.length+selectedFacts.length, textChanged=Boolean(draft&&text!==draft.reviewed_text), readOnly=Boolean(draft?.confirmed_at)
  const disabled=busy||readOnly||conflict||record.archived
  function change(setter,id,update){setter((items)=>items.map((item)=>item.id===id?{...item,...update}:item));setAcknowledged(false)}
  async function request(run){setBusy(true);setError('');try{await run()}catch(err){setError(apiMessage(err));if(err.response?.status===409)setConflict(true)}finally{setBusy(false)}}
  function prepare(manual=false){return request(async()=>{const {data}=await api.post('/extractions',{record_id:record.id,attachment_id:attachment?.id,language,...(manual?{text}:{})});applyDraft(data.extraction);setResult(null)})}
  function reparse(){return request(async()=>{const {data}=await api.patch(`/extractions/${draft.id}/review`,{revision:draft.revision,text});applyDraft(data.extraction)})}
  function reload(){return request(async()=>{const {data}=await api.get(`/extractions/${draft.id}`);applyDraft(data.extraction)})}
  function confirm(){
    if(!count||selected.some((item)=>!item.measured_at||item.value==null||(item.metric_type==='blood_pressure'&&item.secondary_value==null)||(item.metric_type==='blood_glucose'&&!item.context))){setError(t('请补全所选指标的数值、测量时间和血糖测量场景。'));return}
    return request(async()=>{
      const {data}=await api.post(`/extractions/${draft.id}/confirm`,{revision:draft.revision,profile_revision:draft.profile_revision,acknowledged,
        selections:selected.map((item)=>({candidate_id:item.id,value:item.value,secondary_value:item.secondary_value,unit:item.unit,context:item.context,measured_at:item.measured_at.toISOString(),special_context:item.special_context})),
        facts:selectedFacts.map((item)=>({candidate_id:item.id,section:item.section,name:item.name,sensitive:Boolean(item.sensitive),...Object.fromEntries(factFields[item.section].map((field)=>[field,item[field]||'']))}))})
      applyDraft(data.extraction);setResult(data);onImported?.(data.measurements);window.dispatchEvent(new Event('notifications:changed'));message.success(t(data.message))
    })
  }
  function selectionFor(items,setter,existingKey){return{selectedRowKeys:items.filter((item)=>item.selected).map((item)=>item.id),onChange:(keys)=>{setter((current)=>current.map((item)=>({...item,selected:keys.includes(item.id)})));setAcknowledged(false)},getCheckboxProps:(item)=>({disabled:disabled||Boolean(item[existingKey]),'aria-label':t(`选择${item.metric_type?metricLabels[item.metric_type]:sectionLabels[item.section]}候选${item.line_number}`)})}}
  function evidence(item){return <div className="review-evidence"><Text type="secondary">{item.page?t(`第 ${item.page} 页 · `):''}{t("原文第 ")}{item.line_number}{t(" 行")}</Text><Paragraph copyable>{item.evidence}</Paragraph>{item.time_source&&<Text type="secondary">{t("已预填原文明确标记的测量时间，请核对；原文无时区时按本机时区解释。")}</Text>}</div>}
  const readingColumns=[
    {title:t('指标'),width:100,render:(_,item)=><><Text strong>{metricLabels[item.metric_type]}</Text>{item.existing_measurement_id&&<Tag color="green">{t("已导入")}</Tag>}</>},
    {title:t('数值 / 单位'),width:235,render:(_,item)=>item.existing_measurement_id?<span>{item.confirmed_values.value}{item.confirmed_values.secondary_value!=null?`/${item.confirmed_values.secondary_value}`:''} {item.confirmed_values.unit}</span>:<><Space.Compact><InputNumber aria-label={t(`${metricLabels[item.metric_type]}数值`)} value={item.value} onChange={(value)=>change(setRows,item.id,{value})} disabled={disabled}/>{item.metric_type==='blood_pressure'&&<InputNumber aria-label={t("舒张压数值")} value={item.secondary_value} onChange={(secondary_value)=>change(setRows,item.id,{secondary_value})} disabled={disabled}/>}<Select aria-label={t(`${metricLabels[item.metric_type]}单位`)} value={item.unit} onChange={(unit)=>change(setRows,item.id,{unit})} options={(item.metric_type==='blood_glucose'?['mmol/L','mg/dL']:[item.unit]).map((unit)=>({value:unit,label:unit}))} disabled={disabled}/></Space.Compact>{item.unit==='mg/dL'&&<small className="review-conversion">{t("确认后存为 ")}{(Number(item.value)/18).toFixed(2)}{t(" mmol/L（÷18），保留原单位")}</small>}</>},
    {title:t('测量时间'),width:205,render:(_,item)=>item.existing_measurement_id?dayjs(item.confirmed_values.measured_at).format('YYYY-MM-DD HH:mm'):<DatePicker aria-label={t(`${metricLabels[item.metric_type]}测量时间`)} showTime value={item.measured_at} onChange={(measured_at)=>change(setRows,item.id,{measured_at})} placeholder={t("请补全测量时间")} disabled={disabled}/>},
    {title:t('测量场景'),width:170,render:(_,item)=>item.existing_measurement_id?<Link to={`/insights?metric=${item.metric_type}&reading=${item.existing_measurement_id}`} onClick={onClose}>{t("查看已导入指标")}</Link>:<Space direction="vertical" size={6}>{contexts[item.metric_type]&&<Select aria-label={t(`${metricLabels[item.metric_type]}测量场景`)} value={item.context||undefined} placeholder={t("请选择场景")} onChange={(context)=>change(setRows,item.id,{context})} options={options(contexts[item.metric_type])} disabled={disabled}/>}<Select aria-label={t(`${metricLabels[item.metric_type]}适用情况`)} value={item.special_context} onChange={(special_context)=>change(setRows,item.id,{special_context})} options={options(specials)} disabled={disabled}/></Space>},
  ]
  const factColumns=[
    {title:t('类别'),width:105,render:(_,item)=><>{sectionLabels[item.section]}{item.existing_profile_item_id&&<Tag color="green">{t("已关联")}</Tag>}</>},
    {title:t('明确记录的名称'),width:210,render:(_,item)=><Input aria-label={t(`${sectionLabels[item.section]}名称`)} value={item.name} onChange={(event)=>change(setFacts,item.id,{name:event.target.value})} maxLength={160} disabled={disabled||Boolean(item.existing_profile_item_id)}/>},
    {title:t('核对详情'),render:(_,item)=><div className="review-fact-fields">{factFields[item.section].map((field)=><label key={field}>{fieldLabels[field]}<Input aria-label={`${item.name}${fieldLabels[field]}`} value={item[field]||''} onChange={(event)=>change(setFacts,item.id,{[field]:event.target.value})} placeholder={field.endsWith('date')?'YYYY-MM-DD':undefined} maxLength={1000} disabled={disabled||Boolean(item.existing_profile_item_id)}/></label>)}<Checkbox checked={item.sensitive} onChange={(event)=>change(setFacts,item.id,{sensitive:event.target.checked})} disabled={disabled||Boolean(item.existing_profile_item_id)}>{t("敏感信息")}</Checkbox></div>},
  ]
  return <Modal open className="report-review-modal" title={t("核对报告信息")} onCancel={onClose} width={1120} destroyOnHidden footer={<div className="review-footer"><Text type="secondary">{readOnly?t('确认记录已保留，可随时回查来源。'):t(`已选择 ${selected.length} 条指标、${selectedFacts.length} 条健康史`)}</Text><Space><Button onClick={onClose}>{t("关闭")}</Button>{draft&&!readOnly&&<Button type="primary" loading={busy} disabled={disabled||textChanged||!acknowledged||!count} onClick={confirm}>{t("确认导入（")}{count}）</Button>}</Space></div>}>
    <Spin spinning={loading}>
      <div className="review-source"><div><Text strong>{recordValue(draft, 'filename')||recordValue(attachment, 'filename')||recordValue(record, 'title')}</Text><Paragraph type="secondary">{t("核对需要保存的内容；未选中的条目不会加入健康信息。")}</Paragraph></div><Space wrap><Link to={`/records/${record.id}`} onClick={onClose}>{t("返回来源档案")}</Link>{draft?.attachment_available&&<a href={`/api/records/${record.id}/attachments/${draft.attachment_id}`} target="_blank" rel="noreferrer">{t("查看原始文件")}</a>}</Space></div>
      {error&&<Alert type="error" showIcon title={t(error)} action={conflict&&<Button onClick={reload} loading={busy}>{t("放弃修改并加载最新")}</Button>}/>}
      {result&&<Alert type="success" showIcon title={t(result.message)} description={<Space wrap>{result.measurements.map((item)=><Link key={item.id} to={`/insights?metric=${item.metric_type}&reading=${item.id}`} onClick={onClose}>{t("查看导入的")}{metricLabels[item.metric_type]} #{item.id}</Link>)}{!!result.profile_facts?.length&&<Link to="/profile" onClick={onClose}>{t("查看个人健康信息")}</Link>}<Link to="/insights" onClick={onClose}>{t("查看健康状况")}</Link></Space>}/>}
      {!draft&&!extractionId&&<div className="review-start"><Paragraph>{t("从原文寻找血压、血糖、心率，以及明确标记的诊断、用药、过敏和家族史。结果只作为待确认内容，不自动写入健康信息。")}</Paragraph><Space wrap>{attachment&&<Select aria-label={t("识别语言")} value={language} onChange={setLanguage} options={[{value:'auto',label:t('设备默认语言')},...(capabilities?.ocr?.languages||[]).map((value)=>({value,label:value==='zh-Hans-CN'?t('简体中文'):value==='en-US'?'English':value}))]}/>}<Button type="primary" loading={busy} disabled={record.archived} onClick={()=>prepare(false)}>{t("提取待确认内容")}</Button></Space>{capabilities?.ocr&&!capabilities.ocr.available&&<Paragraph type="secondary">{t("本机图片识别不可用。可读取文本 PDF，或粘贴原文继续。")}</Paragraph>}</div>}
      {draft&&<><div className="review-summary"><Tag>{readOnly?t('已确认'):t('待核对')}</Tag><Text>{rows.length}{t(" 条指标 · ")}{facts.length}{t(" 条健康史")}</Text>{draft.page_info?.total_pages!=null&&<Text type="secondary">{t("已读 ")}{draft.page_info.processed_pages.length} / {draft.page_info.total_pages}{t(" 页")}</Text>}</div>
        <Tabs defaultActiveKey={rows.length?'readings':'facts'} items={[{key:'readings',label:t(`指标（${rows.length}）`),children:<>{!readOnly&&rows.length>0&&<div className="review-batch"><DatePicker aria-label={t("批量测量时间")} showTime value={bulkDate} onChange={setBulkDate} placeholder={t("为选中指标设置时间")}/><Button disabled={disabled||!bulkDate||!selected.length} onClick={()=>{setRows((items)=>items.map((item)=>item.selected?{...item,measured_at:bulkDate}:item));setAcknowledged(false)}}>{t("应用到已选指标")}</Button><Text type="secondary">{t("时间按本机时区显示；上传时间不会作为测量时间。")}</Text></div>}<Table rowKey="id" size="small" pagination={false} scroll={{x:850}} dataSource={rows} columns={readingColumns} rowSelection={!readOnly?selectionFor(rows,setRows,'existing_measurement_id'):undefined} expandable={{expandedRowRender:evidence}} locale={{emptyText:t('未找到明确标签和单位的支持指标，可在下方校对原文。')}}/></>},{key:'facts',label:t(`健康史（${facts.length}）`),children:<><Paragraph type="secondary">{t("只确认报告中明确记载的事实。同名既有条目保持原值，不覆盖手工信息；否定、待排和不确定诊断不会作为确诊导入。")}</Paragraph><Table rowKey="id" size="small" pagination={false} scroll={{x:780}} dataSource={facts} columns={factColumns} rowSelection={!readOnly?selectionFor(facts,setFacts,'existing_profile_item_id'):undefined} expandable={{expandedRowRender:evidence}} locale={{emptyText:t('没有找到明确标记的健康史事实。')}}/></>}]} />
        {!readOnly&&count>0&&<Checkbox className="review-acknowledge" checked={acknowledged} disabled={disabled||textChanged} onChange={(event)=>setAcknowledged(event.target.checked)}>{t("我已核对所选内容、单位、测量时间和适用情况，同意加入个人健康信息。")}</Checkbox>}
      </>}
      {textChanged&&<Alert type="warning" title={t("原文有修改，请重新查找候选。已有勾选和调整将被清除。")}/>}
      {(!extractionId||draft)&&<Collapse className="review-text" defaultActiveKey={[]} items={[{key:'text',label:draft?t('原文与校对'):t('粘贴原文'),children:<><Input.TextArea aria-label={t("报告原文")} rows={8} value={text} maxLength={60000} showCount onChange={(event)=>{setText(event.target.value);setAcknowledged(false)}} disabled={disabled}/>{!readOnly&&<Button loading={busy} disabled={!text.trim()||disabled} onClick={draft?reparse:()=>prepare(true)}>{t("按此原文重新查找")}</Button>}{draft?.text_edited&&<details><summary>{t("首次提取原文（保留不变）")}</summary><pre>{draft.original_text}</pre></details>}</>},{key:'limits',label:t('处理范围与识别说明'),children:<><Paragraph>{t("本地处理，不发送到云端。草稿最多保留 60,000 字符；文档处理范围和未处理页以来源档案状态为准。读不出的内容可手工校对，不使用模拟值填补。")}</Paragraph>{draft?.warnings.map((warning,index)=><Paragraph type="secondary" key={index}>{t(warning)}</Paragraph>)}<Paragraph>{t("只预填原文明确标记的完整测量日期时间，仍需本人确认。无时间、无单位和模糊数字不会被猜测；健康史只识别限定标签模板，不推断疾病。")}</Paragraph></>}]} />}
    </Spin>
  </Modal>
}
