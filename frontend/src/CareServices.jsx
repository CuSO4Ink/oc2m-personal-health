import React from 'react'
import { CalendarOutlined, CheckCircleOutlined, ClockCircleOutlined, EnvironmentOutlined, HeartOutlined, MedicineBoxOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { Alert, Button, Card, DatePicker, Descriptions, Empty, Form, Input, List, Modal, Popconfirm, Checkbox, Select, Skeleton, Space, Statistic, Steps, Tabs, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { Link, useSearchParams } from 'react-router-dom'
import api, { apiMessage } from './api'
import Guidance from './Guidance'
import BookingShareScope from './BookingShareScope'
import { initialBookingScope, scopeCount } from './bookingScope'
import { SharedContent } from './SharingPrivacy'
import DocumentPreview from './DocumentPreview'
import { useLanguage, t } from './i18n'

const { Title, Paragraph, Text } = Typography

function formatDate(value, withTime = false) {
  return dayjs(value).format(withTime ? 'YYYY-MM-DD HH:mm' : 'YYYY-MM-DD')
}

function appointmentStatus(status) {
  return status === 'confirmed' ? <Tag color="green">{t("已确认")}</Tag> : <Tag>{t("已取消")}</Tag>
}

function reminderStatus(status) {
  if (status === 'overdue') return <Tag color="red">{t("已到期")}</Tag>
  if (status === 'completed') return <Tag color="green">{t("已完成")}</Tag>
  if (status === 'cancelled') return <Tag>{t("已取消")}</Tag>
  return <Tag color="blue">{t("待进行")}</Tag>
}

export default function CareServicesPage() {
  const { t, language } = useLanguage()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedTab = ['appointments', 'reminders'].includes(searchParams.get('tab')) ? searchParams.get('tab') : 'reminders'
  const [editingReminder, setEditingReminder] = React.useState(null)
  const [services, setServices] = React.useState([])
  const [appointments, setAppointments] = React.useState([])
  const [reminders, setReminders] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [specialty, setSpecialty] = React.useState('all')
  const [serviceSearch, setServiceSearch] = React.useState('')
  const [rescheduling, setRescheduling] = React.useState(null)
  const [bookingService, setBookingService] = React.useState(null)
  const [bookingStep, setBookingStep] = React.useState(0)
  const [bookingDraft, setBookingDraft] = React.useState(null)
  const [booking, setBooking] = React.useState(false)
  const [reminderOpen, setReminderOpen] = React.useState(() => Boolean(searchParams.get('new')))
  const [savingReminder, setSavingReminder] = React.useState(false)
  const [bookingForm] = Form.useForm()
  const shareEnabled = Form.useWatch('share_enabled', bookingForm)
  const [sharePreview, setSharePreview] = React.useState(null)
  const [filePreview, setFilePreview] = React.useState(null)
  const [reminderForm] = Form.useForm()
  const reminderMetric = {blood_pressure: t('血压'), blood_glucose: t('血糖'), heart_rate: t('心率')}[searchParams.get('new')]
  const initialReminder = {title: reminderMetric ? t('Record {metric}', { metric: reminderMetric }) : '', category: reminderMetric ? 'measurement' : 'general', next_due_at: dayjs().add(1,'day'), repeat_days: 0, schedule_note: t('仅一次')}


  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [servicesResponse, appointmentsResponse, remindersResponse] = await Promise.all([
        api.get('/services/medical'), api.get('/services/appointments'), api.get('/services/reminders'),
      ])
      setServices(servicesResponse.data.services); setAppointments(appointmentsResponse.data.appointments)
      setReminders(remindersResponse.data.reminders)
    } catch (requestError) { setError(apiMessage(requestError)) }
    finally { setLoading(false) }
  }, [])

  React.useEffect(() => {
    let active = true
    Promise.all([api.get('/services/medical'), api.get('/services/appointments'), api.get('/services/reminders')])
      .then(([servicesResponse, appointmentsResponse, remindersResponse]) => {
        if (!active) return
        setServices(servicesResponse.data.services); setAppointments(appointmentsResponse.data.appointments)
        setReminders(remindersResponse.data.reminders)
      }).catch((requestError) => { if (active) setError(apiMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  function openBooking(service, appointment = null) {
    setRescheduling(appointment)
    setBookingService(service); setBookingStep(0); setBookingDraft(null); setSharePreview(null); bookingForm.resetFields()
    bookingForm.setFieldsValue({ reason: appointment?.reason || '', recipient_id: appointment?.clinician?.id, share_enabled: false, sharing_scope: initialBookingScope(), share_expires: dayjs().add(14, 'day') })
  }

  async function reviewBooking() {
    setBooking(true)
    try {
      const { share_enabled, sharing_scope, share_expires, ...values } = await bookingForm.validateFields()
      let sharing_draft
      setSharePreview(null)
      if (share_enabled && !rescheduling) {
        if (!scopeCount(sharing_scope)) { message.error(t('Select at least one item to share.')); return }
        const payload = { ...sharing_scope, recipient_id: values.recipient_id, purpose: values.reason, starts_at: new Date().toISOString(), expires_at: share_expires.toISOString() }
        const { data } = await api.post('/sharing/grants/draft-preview', payload)
        sharing_draft = { ...payload, preview_token: data.preview_token }
        setSharePreview(data)
      }
      setBookingDraft({ ...values, ...(sharing_draft ? { sharing_draft } : {}) }); setBookingStep(1)
    } catch (failure) { if (!failure.errorFields) message.error(apiMessage(failure)) }
    finally { setBooking(false) }
  }

  async function confirmBooking() {
    setBooking(true)
    try {
      if (rescheduling) await api.patch(`/services/appointments/${rescheduling.id}/reschedule`, {slot_id: bookingDraft.slot_id, expected_slot_id: rescheduling.slot.id})
      else await api.post('/services/appointments', bookingDraft)
      message.success(rescheduling ? t('预约时间已在本站更新。') : t('预约已保存在本站。'))
      setBookingService(null); setSharePreview(null); await load()
    } catch (requestError) { message.error(apiMessage(requestError)); if ([400, 409].includes(requestError.response?.status)) { setBookingStep(0); setSharePreview(null) } }
    finally { setBooking(false) }
  }

  async function cancelAppointment(id) {
    try {
      await api.patch(`/services/appointments/${id}/cancel`)
      message.success(t('预约已取消，模拟名额已释放。'))
      await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  function openReminder(reminder = null) {
    setEditingReminder(reminder)
    reminderForm.resetFields()
    reminderForm.setFieldsValue(reminder ? { ...reminder, next_due_at: dayjs(reminder.next_due_at) } : { category: 'general', next_due_at: dayjs().add(1, 'day'), schedule_note: t('仅一次'), repeat_days: 0 })
    setReminderOpen(true)
  }

  async function saveReminder(values) {
    setSavingReminder(true)
    try {
      const payload = { ...values, next_due_at: values.next_due_at.toISOString() }
      if (editingReminder) await api.patch(`/services/reminders/${editingReminder.id}`, payload)
      else await api.post('/services/reminders', payload)
      message.success(editingReminder ? t('健康提醒已更新。') : t('健康提醒已创建。')); setReminderOpen(false); setSearchParams({tab: 'reminders'}, {replace: true}); await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSavingReminder(false) }
  }

  async function completeReminder(id) {
    try {
      await api.patch(`/services/reminders/${id}/complete`)
      message.success(t('提醒已标记完成。')); await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function cancelReminder(id) {
    try { await api.patch(`/services/reminders/${id}/cancel`); message.success(t('提醒已取消，历史记录保留。')); await load() }
    catch (requestError) { message.error(apiMessage(requestError)) }
  }

  async function stopRepeat(id) {
    try {await api.patch(`/services/reminders/${id}/stop-repeat`); message.success(t('已停止后续重复，当前任务保留。')); await load()}
    catch(error) {message.error(apiMessage(error))}
  }

  const confirmedAppointments = appointments.filter((item) => item.status === 'confirmed' && dayjs(item.slot.starts_at).isAfter(dayjs()))
  const nextAppointment = confirmedAppointments[0]
  const openReminders = reminders.filter((item) => !['completed', 'cancelled'].includes(item.status))
  const overdueCount = reminders.filter((item) => item.status === 'overdue').length
  const specialties = [...new Set(services.map((service) => service.specialty))]
  const filteredServices = services.filter((service) => (specialty === 'all' || service.specialty === specialty) && `${service.name} ${service.specialty} ${service.facility.name}`.toLowerCase().includes(serviceSearch.toLowerCase()))
  const selectedSlot = bookingService?.slots.find((slot) => slot.id === bookingDraft?.slot_id)
  const availableSlots = (bookingService?.slots || []).filter((slot) => slot.available && dayjs(slot.starts_at).isAfter(dayjs()) && slot.id !== rescheduling?.slot.id)
  const selectedClinician = bookingService?.clinicians?.find((person) => person.id === bookingDraft?.recipient_id) || rescheduling?.clinician

  const appointmentsPanel = <div className="service-panel">
    <section><div className="section-heading"><div><Title level={3}>{t("我的预约")}</Title><Paragraph>{t("这里显示本站保存的预约。选择医生后，可在预约时一并授权资料。")}</Paragraph></div></div>{appointments.length === 0 ? <Card><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("还没有预约")} /></Card> : <div className="appointment-list">{appointments.map((appointment) => <Card key={appointment.id} className="appointment-card"><div className="appointment-date"><b>{dayjs(appointment.slot.starts_at).format('DD')}</b><span>{dayjs(appointment.slot.starts_at).format(language === 'zh' ? 'M月' : 'MMM')}</span></div><div className="appointment-info"><Space>{appointmentStatus(appointment.status)}<Text type="secondary">{formatDate(appointment.slot.starts_at, true)}</Text></Space><Title level={4}>{appointment.service.name}</Title><Text>{appointment.service.facility.name}</Text><Text type="secondary">{t("原因：")}{appointment.reason}</Text>{appointment.clinician && <Text>{t('Clinician')}: {appointment.clinician.full_name}</Text>}{appointment.sharing && <Link to={`/sharing?tab=permissions&grant=${appointment.sharing.grant_id}`}>{t('Manage linked sharing permission')}</Link>}</div>{appointment.status === 'confirmed' && dayjs(appointment.slot.starts_at).isAfter(dayjs()) && <Space wrap><Button disabled={!services.find((service) => service.id === appointment.service.id)?.slots.some((slot) => slot.available && slot.id !== appointment.slot.id)} onClick={() => {const service = services.find((item) => item.id === appointment.service.id); if(service) {openBooking(service, appointment); bookingForm.setFieldsValue({reason: appointment.reason})}}}>{t("改期")}</Button><Popconfirm title={t("取消这次预约？")} description={t("取消后释放名额，并撤销本次预约创建的共享授权。")} okText={t("取消预约")} okButtonProps={{ danger: true }} onConfirm={() => cancelAppointment(appointment.id)}><Button danger>{t("取消")}</Button></Popconfirm></Space>}</Card>)}</div>}</section>
    <section><div className="section-heading"><div><Title level={3}>{t("查找医疗服务")}</Title><Paragraph>{t("选择模拟机构、服务和可预约时间。")}</Paragraph></div><Space wrap><Input allowClear prefix={<SearchOutlined />} placeholder={t("搜索服务")} value={serviceSearch} onChange={(event) => setServiceSearch(event.target.value)} /><Select value={specialty} onChange={setSpecialty} options={[{ value: 'all', label: t('所有专科') }, ...specialties.map((value) => ({ value, label: value }))]} /></Space></div>{filteredServices.length === 0 ? <Card><Empty description={t("没有符合筛选条件的服务")} /></Card> : <div className="medical-service-grid">{filteredServices.map((service) => <Card key={service.id} className="medical-service-card"><div><Space><Tag color="blue">{service.specialty}</Tag></Space><Title level={4}>{service.name}</Title><Text>{service.facility.name}</Text><div className="service-detail"><span><EnvironmentOutlined /> {service.facility.address}</span><span><ClockCircleOutlined /> {service.duration_minutes}{t(" 分钟 · ")}{{in_person: t('到院'), online: t('线上'), phone: t('电话')}[service.appointment_mode] || service.appointment_mode}</span><span>{service.cost_label}</span></div></div><div className="availability"><Text strong>{service.slots.filter((slot) => slot.available).length}{t(" 个可选时段")}</Text><Button type="primary" disabled={!service.slots.some((slot) => slot.available)} onClick={() => openBooking(service)}>{t("选择时间")}</Button></div></Card>)}</div>}</section>
  </div>

  const remindersPanel = <div className="service-panel"><div className="section-heading"><div><Title level={3}>{t("我的健康提醒")}</Title><Paragraph>{t("记录自己的用药、复查或其他日常安排。")}</Paragraph></div><Button type="primary" icon={<PlusOutlined />} onClick={() => openReminder()}>{t("添加提醒")}</Button></div><div className="reminder-stats"><Card><Statistic title={t("待办")} value={openReminders.length} /></Card><Card><Statistic title={t("已到期")} value={overdueCount} /></Card></div>{reminders.length === 0 ? <Card><Empty description={t("还没有健康提醒")}><Button type="primary" onClick={() => openReminder()}>{t("添加提醒")}</Button></Empty></Card> : <List className="reminder-list" pagination={{pageSize: 8}} dataSource={reminders} renderItem={(reminder) => <List.Item className={String(reminder.id) === searchParams.get('reminder') ? 'linked-item' : ''} actions={!['completed', 'cancelled'].includes(reminder.status) ? [<Button key="edit" onClick={() => openReminder(reminder)}>{t("编辑")}</Button>, <Popconfirm key="cancel" title={t("取消这条提醒及其后续重复？")} onConfirm={() => cancelReminder(reminder.id)}><Button danger>{t("取消")}</Button></Popconfirm>, ...(reminder.repeat_days ? [<Popconfirm key="stop" title={t("停止后续重复提醒？")} onConfirm={() => stopRepeat(reminder.id)}><Button>{t("停止重复")}</Button></Popconfirm>] : []), <Button key="complete" type="primary" ghost icon={<CheckCircleOutlined />} onClick={() => completeReminder(reminder.id)}>{t("标记完成")}</Button>] : []}><List.Item.Meta avatar={<div className={`reminder-icon ${reminder.category}`}>{reminder.category === 'medication' ? <MedicineBoxOutlined /> : reminder.category === 'appointment' ? <CalendarOutlined /> : <HeartOutlined />}</div>} title={<Space wrap><Text strong>{reminder.title}</Text>{reminderStatus(reminder.status)}<Tag>{reminder.repeat_days ? t(`每 ${reminder.repeat_days * 24} 小时`) : t('一次性提醒')}</Tag></Space>} description={<div className="reminder-detail"><span>{formatDate(reminder.next_due_at, true)}</span><span>{reminder.schedule_note}</span>{reminder.repeat_days > 0 && <span>{t("完成后生成下一次提醒，已错过的日期会跳过。")}</span>}<span>{t("来源：")}{reminder.source_name}</span>{reminder.notes && <span>{reminder.notes}</span>}</div>} /></List.Item>} />}</div>


  return <div className="page-stack care-page">
    <div className="page-heading"><div><Title level={1}>{t("提醒与服务")}</Title><Paragraph>{t("安排用药、复查提醒，或选择医生和就诊时间。")}</Paragraph></div></div>
    <Guidance id="care-demo" title={t("预约与服务的使用说明")}>{t("本页机构和医生为虚构示例。预约、改期和资料授权保存在本站，不会通知真实医院或医生，也不收取费用。")}</Guidance>
    {error && <Alert type="error" showIcon message={t("无法加载提醒与服务")} description={error} action={<Button onClick={load}>{t("重试")}</Button>} />}
    {loading ? <Card><Skeleton active paragraph={{ rows: 9 }} /></Card> : !error && <>
      {selectedTab === 'appointments' && <div className="care-summary"><Card className="next-care-card"><Text type="secondary">{t("下次预约")}</Text>{nextAppointment ? <><Space>{appointmentStatus(nextAppointment.status)}<Text>{formatDate(nextAppointment.slot.starts_at, true)}</Text></Space><Title level={3}>{nextAppointment.service.name}</Title><Text>{nextAppointment.service.facility.name}</Text></> : <><Title level={3}>{t("暂无预约")}</Title><Text type="secondary">{t("可在下方选择医生和时间。")}</Text></>}</Card><Card><Statistic title={t("待办提醒")} value={openReminders.length} prefix={<HeartOutlined />} /><Text type={overdueCount ? 'danger' : 'secondary'}>{overdueCount ? t(`${overdueCount} 条已到期`) : t('暂无到期提醒')}</Text></Card></div>}
      <Tabs activeKey={selectedTab} onChange={(tab) => setSearchParams({ tab }, { replace: true })} items={[{ key: 'reminders', label: t(`我的提醒（${openReminders.length}）`), children: remindersPanel }, { key: 'appointments', label: t('医疗预约'), children: appointmentsPanel }]} />
    </>}

    <Modal width={860} title={rescheduling ? t('Reschedule appointment') : t('Book an appointment')} open={Boolean(bookingService)} onCancel={() => setBookingService(null)} footer={null} destroyOnHidden>
      {bookingService && <><Steps size="small" current={bookingStep} items={[{ title: t('Choose clinician and time') }, { title: t('Review and confirm') }]} />
        <Form className="booking-form" form={bookingForm} layout="vertical" style={{ display: bookingStep === 0 ? 'block' : 'none' }}>
          <Card size="small"><Text strong>{bookingService.name}</Text><div><Text type="secondary">{bookingService.facility.name} · {bookingService.facility.address}</Text></div></Card>
          {!rescheduling && <Form.Item label={t('Clinician')} name="recipient_id" rules={[{ required: Boolean(bookingService.clinicians?.length), message: t('Choose a clinician') }]}><Select placeholder={t('Choose a clinician')} options={(bookingService.clinicians || []).map((person) => ({ value: person.id, label: `${person.full_name} · ${person.role}` }))} /></Form.Item>}
          {rescheduling?.clinician && <Paragraph>{t('Clinician')}: {rescheduling.clinician.full_name}</Paragraph>}
          <Form.Item label={t('Available time (your local time)')} name="slot_id" rules={[{ required: true, message: t('Choose an available time') }]}><Select aria-label={t('Available time (your local time)')} placeholder={t('Choose an available time')} options={availableSlots.map((slot) => ({ value: slot.id, label: `${formatDate(slot.starts_at, true)} · ${t('{count} places available', { count: slot.available_places })}` }))} /></Form.Item>
          {!availableSlots.length && <Alert type="info" message={t('No future times are available. Please return to the service list.')} />}
          <Form.Item label={t('Reason for appointment')} name="reason" rules={[{ required: true, min: 3, message: t('Briefly describe the reason for your appointment') }]}><Input.TextArea rows={3} maxLength={300} showCount disabled={Boolean(rescheduling)} /></Form.Item>
          {!rescheduling && Boolean(bookingService.clinicians?.length) && <><Form.Item name="share_enabled" valuePropName="checked"><Checkbox>{t('Share selected health information with this clinician')}</Checkbox></Form.Item>{shareEnabled && <><Form.Item name="sharing_scope"><BookingShareScope /></Form.Item><Form.Item label={t('Sharing expires at')} name="share_expires" rules={[{ required: true }]}><DatePicker showTime /></Form.Item></>}</>}
          {rescheduling?.sharing && <Alert type="info" message={t('Rescheduling does not extend sharing access. Review its expiry in Sharing and access.')} />}
          <div className="form-actions"><Button onClick={() => setBookingService(null)}>{t('Cancel')}</Button><Button type="primary" loading={booking} disabled={!availableSlots.length} onClick={reviewBooking}>{t('Review appointment')}</Button></div>
        </Form>
        {bookingStep === 1 && bookingDraft && <div className="booking-review"><Descriptions bordered column={1} size="small" items={[{ key: 'service', label: t('Service'), children: bookingService.name }, { key: 'clinician', label: t('Clinician'), children: selectedClinician?.full_name || '—' }, { key: 'provider', label: t('Facility'), children: bookingService.facility.name }, { key: 'time', label: t('Time'), children: selectedSlot ? formatDate(selectedSlot.starts_at, true) : '—' }, { key: 'location', label: t('Address'), children: bookingService.facility.address }, { key: 'reason', label: t('Reason'), children: bookingDraft.reason }]} />
          {sharePreview ? <><Title level={5}>{t('The clinician will see exactly this content')}</Title><Paragraph>{t('Sharing expires at')}: {formatDate(bookingDraft.sharing_draft.expires_at, true)} · {bookingDraft.sharing_draft.allow_download ? t('View and export') : t('View only')}</Paragraph><SharedContent data={sharePreview} onFile={(file) => setFilePreview(file)} /><Alert type="info" message={t('Confirming books the appointment and creates this fixed sharing permission. You can revoke it in Sharing and access.')} /></> : <Paragraph>{t('No new health information will be shared for this appointment.')}</Paragraph>}
          <div className="form-actions"><Button onClick={() => setBookingStep(0)}>{t('Back to edit')}</Button><Button type="primary" loading={booking} onClick={confirmBooking}>{rescheduling ? t('Confirm reschedule') : t('Confirm appointment')}</Button></div>
        </div>}
      </>}
    </Modal>
    <Modal width={960} title={filePreview?.filename} open={Boolean(filePreview)} onCancel={() => setFilePreview(null)} footer={<Button onClick={() => setFilePreview(null)}>{t('Close')}</Button>} destroyOnHidden>{filePreview && <DocumentPreview url={`/api/records/${filePreview.record_id}/attachments/${filePreview.id}`} filename={filePreview.filename} contentType={filePreview.content_type} />}</Modal>

    <Modal title={editingReminder ? t("编辑健康提醒") : t("添加健康提醒")} open={reminderOpen} onCancel={() => setReminderOpen(false)} footer={null} destroyOnHidden><Form form={reminderForm} initialValues={initialReminder} layout="vertical" onFinish={saveReminder}><Form.Item label={t("提醒事项")} name="title" rules={[{ required: true, min: 2, message: t('请填写提醒事项') }]}><Input maxLength={160} placeholder={t("例如：记录晚间血压")} /></Form.Item><Form.Item label={t("提醒类型")} name="category" rules={[{ required: true }]}><Select options={[{ value: 'medication', label: t('用药') }, { value: 'measurement', label: t('健康测量') }, { value: 'appointment', label: t('就诊准备') }, { value: 'general', label: t('其他健康安排') }]} /></Form.Item><Form.Item label={t("下次提醒时间")} name="next_due_at" rules={[{ required: true }]}><DatePicker showTime className="full-width" /></Form.Item><Form.Item label={t("重复频率")} name="repeat_days"><Select options={[{value: 0, label: t('仅一次')}, {value: 1, label: t('每 24 小时')}, {value: 7, label: t('每 7 天')}]} /></Form.Item><Paragraph type="secondary">{t("重复提醒在本次完成后生成下一次，已完成记录会保留。重复间隔固定，夏令时切换时本地显示时间可能变化。")}</Paragraph><Form.Item label={t("时间补充说明")} name="schedule_note"><Input placeholder={t("可选，例如早餐后")} /></Form.Item><Form.Item label={t("备注")} name="notes"><Input.TextArea rows={3} maxLength={300} showCount /></Form.Item><div className="form-actions"><Button onClick={() => setReminderOpen(false)}>{t("取消")}</Button><Button type="primary" htmlType="submit" loading={savingReminder}>{t("保存提醒")}</Button></div></Form></Modal>

  </div>
}
