import React from 'react'
import { CalendarOutlined, CheckCircleOutlined, ClockCircleOutlined, EnvironmentOutlined, HeartOutlined, MedicineBoxOutlined, PlusOutlined, SafetyCertificateOutlined, SearchOutlined, TeamOutlined } from '@ant-design/icons'
import { Alert, Button, Card, DatePicker, Descriptions, Empty, Form, Input, List, Modal, Popconfirm, Radio, Select, Skeleton, Space, Statistic, Steps, Tabs, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import api, { apiMessage } from './api'

const { Title, Paragraph, Text } = Typography

function formatDate(value, withTime = false) {
  return dayjs(value).format(withTime ? 'ddd, D MMM YYYY · HH:mm' : 'D MMM YYYY')
}

function appointmentStatus(status) {
  return status === 'confirmed' ? <Tag color="green">Confirmed</Tag> : <Tag>Cancelled</Tag>
}

function reminderStatus(status) {
  if (status === 'overdue') return <Tag color="red">Due now</Tag>
  if (status === 'completed') return <Tag color="green">Completed</Tag>
  return <Tag color="blue">Upcoming</Tag>
}

export default function CareServicesPage() {
  const [services, setServices] = React.useState([])
  const [appointments, setAppointments] = React.useState([])
  const [reminders, setReminders] = React.useState([])
  const [elderListings, setElderListings] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [specialty, setSpecialty] = React.useState('all')
  const [serviceSearch, setServiceSearch] = React.useState('')
  const [elderCategory, setElderCategory] = React.useState('all')
  const [elderSearch, setElderSearch] = React.useState('')
  const [bookingService, setBookingService] = React.useState(null)
  const [bookingStep, setBookingStep] = React.useState(0)
  const [bookingDraft, setBookingDraft] = React.useState(null)
  const [booking, setBooking] = React.useState(false)
  const [reminderOpen, setReminderOpen] = React.useState(false)
  const [savingReminder, setSavingReminder] = React.useState(false)
  const [selectedElder, setSelectedElder] = React.useState(null)
  const [bookingForm] = Form.useForm()
  const [reminderForm] = Form.useForm()

  const load = React.useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [servicesResponse, appointmentsResponse, remindersResponse, elderResponse] = await Promise.all([
        api.get('/services/medical'), api.get('/services/appointments'), api.get('/services/reminders'), api.get('/services/elder-care'),
      ])
      setServices(servicesResponse.data.services); setAppointments(appointmentsResponse.data.appointments)
      setReminders(remindersResponse.data.reminders); setElderListings(elderResponse.data.listings)
    } catch (requestError) { setError(apiMessage(requestError)) }
    finally { setLoading(false) }
  }, [])

  React.useEffect(() => {
    let active = true
    Promise.all([api.get('/services/medical'), api.get('/services/appointments'), api.get('/services/reminders'), api.get('/services/elder-care')])
      .then(([servicesResponse, appointmentsResponse, remindersResponse, elderResponse]) => {
        if (!active) return
        setServices(servicesResponse.data.services); setAppointments(appointmentsResponse.data.appointments)
        setReminders(remindersResponse.data.reminders); setElderListings(elderResponse.data.listings)
      }).catch((requestError) => { if (active) setError(apiMessage(requestError)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  function openBooking(service) {
    setBookingService(service); setBookingStep(0); setBookingDraft(null); bookingForm.resetFields()
  }

  async function reviewBooking() {
    try { setBookingDraft(await bookingForm.validateFields()); setBookingStep(1) }
    catch { /* Ant Design displays field errors. */ }
  }

  async function confirmBooking() {
    setBooking(true)
    try {
      await api.post('/services/appointments', bookingDraft)
      message.success('Appointment confirmed by the service.')
      setBookingService(null); await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setBooking(false) }
  }

  async function cancelAppointment(id) {
    try {
      await api.patch(`/services/appointments/${id}/cancel`)
      message.success('Appointment cancelled and the place was released.')
      await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  function openReminder() {
    reminderForm.resetFields(); reminderForm.setFieldsValue({ category: 'general', next_due_at: dayjs().add(1, 'day'), schedule_note: 'One time' }); setReminderOpen(true)
  }

  async function saveReminder(values) {
    setSavingReminder(true)
    try {
      await api.post('/services/reminders', { ...values, next_due_at: values.next_due_at.toISOString() })
      message.success('Health reminder created.'); setReminderOpen(false); await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
    finally { setSavingReminder(false) }
  }

  async function completeReminder(id) {
    try {
      await api.patch(`/services/reminders/${id}/complete`)
      message.success('Reminder marked as completed.'); await load()
    } catch (requestError) { message.error(apiMessage(requestError)) }
  }

  const confirmedAppointments = appointments.filter((item) => item.status === 'confirmed' && dayjs(item.slot.starts_at).isAfter(dayjs()))
  const nextAppointment = confirmedAppointments[0]
  const openReminders = reminders.filter((item) => item.status !== 'completed')
  const overdueCount = reminders.filter((item) => item.status === 'overdue').length
  const specialties = [...new Set(services.map((service) => service.specialty))]
  const filteredServices = services.filter((service) => (specialty === 'all' || service.specialty === specialty) && `${service.name} ${service.specialty} ${service.facility.name}`.toLowerCase().includes(serviceSearch.toLowerCase()))
  const elderCategories = [...new Set(elderListings.map((listing) => listing.category))]
  const filteredElder = elderListings.filter((listing) => (elderCategory === 'all' || listing.category === elderCategory) && `${listing.name} ${listing.address} ${listing.summary}`.toLowerCase().includes(elderSearch.toLowerCase()))
  const selectedSlot = bookingService?.slots.find((slot) => slot.id === bookingDraft?.slot_id)

  const appointmentsPanel = <div className="service-panel">
    <section><div className="section-heading"><div><Title level={3}>Your appointments</Title><Paragraph>Bookings shown here use the latest status returned by the service.</Paragraph></div></div>{appointments.length === 0 ? <Card><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No appointments booked" /></Card> : <div className="appointment-list">{appointments.map((appointment) => <Card key={appointment.id} className="appointment-card"><div className="appointment-date"><b>{dayjs(appointment.slot.starts_at).format('DD')}</b><span>{dayjs(appointment.slot.starts_at).format('MMM')}</span></div><div className="appointment-info"><Space>{appointmentStatus(appointment.status)}<Text type="secondary">{formatDate(appointment.slot.starts_at, true)}</Text></Space><Title level={4}>{appointment.service.name}</Title><Text>{appointment.service.facility.name}</Text><Text type="secondary">Reason: {appointment.reason}</Text></div>{appointment.status === 'confirmed' && <Popconfirm title="Cancel this appointment?" description="The appointment place will be released. Online rescheduling will be added later." okText="Cancel appointment" okButtonProps={{ danger: true }} onConfirm={() => cancelAppointment(appointment.id)}><Button danger>Cancel</Button></Popconfirm>}</Card>)}</div>}</section>
    <section><div className="section-heading"><div><Title level={3}>Find a medical service</Title><Paragraph>Select a verified provider, service and currently available appointment time.</Paragraph></div><Space wrap><Input allowClear prefix={<SearchOutlined />} placeholder="Search services" value={serviceSearch} onChange={(event) => setServiceSearch(event.target.value)} /><Select value={specialty} onChange={setSpecialty} options={[{ value: 'all', label: 'All specialties' }, ...specialties.map((value) => ({ value, label: value }))]} /></Space></div>{filteredServices.length === 0 ? <Card><Empty description="No services match these filters" /></Card> : <div className="medical-service-grid">{filteredServices.map((service) => <Card key={service.id} className="medical-service-card"><div><Space><Tag color="blue">{service.specialty}</Tag>{service.facility.verified && <Tag color="green" icon={<SafetyCertificateOutlined />}>Verified provider</Tag>}</Space><Title level={4}>{service.name}</Title><Text>{service.facility.name}</Text><div className="service-detail"><span><EnvironmentOutlined /> {service.facility.address}</span><span><ClockCircleOutlined /> {service.duration_minutes} minutes · {service.appointment_mode.replace('_', ' ')}</span><span>{service.cost_label}</span></div></div><div className="availability"><Text strong>{service.slots.filter((slot) => slot.available).length} appointment times available</Text><Button type="primary" disabled={!service.slots.some((slot) => slot.available)} onClick={() => openBooking(service)}>Choose a time</Button></div></Card>)}</div>}</section>
  </div>

  const remindersPanel = <div className="service-panel"><div className="section-heading"><div><Title level={3}>Health reminders</Title><Paragraph>Keep personal tasks separate from provider instructions and system alerts.</Paragraph></div><Button type="primary" icon={<PlusOutlined />} onClick={openReminder}>Add Reminder</Button></div><div className="reminder-stats"><Card><Statistic title="To do" value={openReminders.length} /></Card><Card><Statistic title="Due now" value={overdueCount} /></Card></div>{reminders.length === 0 ? <Card><Empty description="No health reminders"><Button type="primary" onClick={openReminder}>Add reminder</Button></Empty></Card> : <List className="reminder-list" dataSource={reminders} renderItem={(reminder) => <List.Item actions={reminder.status !== 'completed' ? [<Button key="complete" type="primary" ghost icon={<CheckCircleOutlined />} onClick={() => completeReminder(reminder.id)}>Mark complete</Button>] : []}><List.Item.Meta avatar={<div className={`reminder-icon ${reminder.category}`}>{reminder.category === 'medication' ? <MedicineBoxOutlined /> : reminder.category === 'appointment' ? <CalendarOutlined /> : <HeartOutlined />}</div>} title={<Space wrap><Text strong>{reminder.title}</Text>{reminderStatus(reminder.status)}</Space>} description={<div className="reminder-detail"><span>{formatDate(reminder.next_due_at, true)}</span><span>{reminder.schedule_note}</span><span>Source: {reminder.source_name}</span>{reminder.notes && <span>{reminder.notes}</span>}</div>} /></List.Item>} />}</div>

  const elderPanel = <div className="service-panel"><Alert type="info" showIcon message="Information directory" description="These listings are for service discovery. Availability, eligibility, booking and fees must be confirmed directly with the provider until the local care directory is integrated." /><div className="section-heading"><div><Title level={3}>Elder care services</Title><Paragraph>Compare service types, accessibility information and where each listing came from.</Paragraph></div><Space wrap><Input allowClear prefix={<SearchOutlined />} placeholder="Search name or area" value={elderSearch} onChange={(event) => setElderSearch(event.target.value)} /><Select value={elderCategory} onChange={setElderCategory} options={[{ value: 'all', label: 'All service types' }, ...elderCategories.map((value) => ({ value, label: value }))]} /></Space></div>{filteredElder.length === 0 ? <Card><Empty description="No care services match these filters" /></Card> : <div className="elder-grid">{filteredElder.map((listing) => <Card key={listing.id} className="elder-card"><Tag color="purple">{listing.category}</Tag><Title level={4}>{listing.name}</Title><Paragraph>{listing.summary}</Paragraph><div className="service-detail"><span><EnvironmentOutlined /> {listing.address}</span><span><TeamOutlined /> {listing.services.slice(0, 2).join(' · ')}</span><span>Updated {formatDate(listing.updated_at)} · {listing.source_name}</span></div><Button onClick={() => setSelectedElder(listing)}>View information</Button></Card>)}</div>}</div>

  return <div className="page-stack care-page">
    <div className="page-heading"><div><Title level={1}>Care Services</Title><Paragraph>Book care, keep track of health tasks and find local support information in one place.</Paragraph></div></div>
    {error && <Alert type="error" showIcon message="Care services could not be loaded" description={error} action={<Button onClick={load}>Try again</Button>} />}
    {loading ? <Card><Skeleton active paragraph={{ rows: 9 }} /></Card> : <>
      <div className="care-summary"><Card className="next-care-card"><Text type="secondary">Next appointment</Text>{nextAppointment ? <><Space>{appointmentStatus(nextAppointment.status)}<Text>{formatDate(nextAppointment.slot.starts_at, true)}</Text></Space><Title level={3}>{nextAppointment.service.name}</Title><Text>{nextAppointment.service.facility.name}</Text></> : <><Title level={3}>Nothing booked</Title><Text type="secondary">Browse available services below.</Text></>}</Card><Card><Statistic title="Health tasks to do" value={openReminders.length} prefix={<HeartOutlined />} /><Text type={overdueCount ? 'danger' : 'secondary'}>{overdueCount ? `${overdueCount} due now` : 'Nothing overdue'}</Text></Card></div>
      <Tabs defaultActiveKey="appointments" items={[{ key: 'appointments', label: 'Medical Appointments', children: appointmentsPanel }, { key: 'reminders', label: `Health Reminders (${openReminders.length})`, children: remindersPanel }, { key: 'elder', label: 'Elder Care Information', children: elderPanel }]} />
    </>}

    <Modal width={680} title="Book an appointment" open={Boolean(bookingService)} onCancel={() => setBookingService(null)} footer={null} destroyOnHidden>
      {bookingService && <><Steps size="small" current={bookingStep} items={[{ title: 'Choose time' }, { title: 'Review & confirm' }]} />{bookingStep === 0 ? <Form className="booking-form" form={bookingForm} layout="vertical"><Card size="small"><Text strong>{bookingService.name}</Text><div><Text type="secondary">{bookingService.facility.name} · {bookingService.duration_minutes} minutes</Text></div></Card><Form.Item label="Available appointment time" name="slot_id" rules={[{ required: true, message: 'Select an appointment time' }]}><Radio.Group className="slot-grid">{bookingService.slots.filter((slot) => slot.available).map((slot) => <Radio.Button key={slot.id} value={slot.id}><b>{dayjs(slot.starts_at).format('ddd D MMM')}</b><span>{dayjs(slot.starts_at).format('HH:mm')} · {slot.available_places} {slot.available_places === 1 ? 'place' : 'places'}</span></Radio.Button>)}</Radio.Group></Form.Item><Form.Item label="Reason for appointment" name="reason" rules={[{ required: true, min: 3, message: 'Briefly describe the reason for your appointment' }]}><Input.TextArea rows={4} maxLength={300} showCount placeholder="This helps the service prepare for your visit." /></Form.Item><div className="form-actions"><Button onClick={() => setBookingService(null)}>Cancel</Button><Button type="primary" onClick={reviewBooking}>Review booking</Button></div></Form> : <div className="booking-review"><Alert type="info" showIcon message="Confirm the appointment details returned by this service" /><Descriptions bordered column={1} size="small" items={[{ key: 'service', label: 'Service', children: bookingService.name }, { key: 'provider', label: 'Provider', children: bookingService.facility.name }, { key: 'time', label: 'Time', children: formatDate(selectedSlot.starts_at, true) }, { key: 'location', label: 'Location', children: bookingService.facility.address }, { key: 'reason', label: 'Reason', children: bookingDraft.reason }, { key: 'cost', label: 'Cost information', children: bookingService.cost_label }]} /><div className="form-actions"><Button onClick={() => setBookingStep(0)}>Back</Button><Button type="primary" loading={booking} onClick={confirmBooking}>Confirm Appointment</Button></div></div>}</>}
    </Modal>

    <Modal title="Add health reminder" open={reminderOpen} onCancel={() => setReminderOpen(false)} footer={null} destroyOnHidden><Form form={reminderForm} layout="vertical" onFinish={saveReminder}><Form.Item label="Reminder title" name="title" rules={[{ required: true, min: 2, message: 'Enter a reminder title' }]}><Input placeholder="e.g. Record evening blood pressure" /></Form.Item><Form.Item label="Category" name="category" rules={[{ required: true }]}><Select options={[{ value: 'medication', label: 'Medication' }, { value: 'measurement', label: 'Health measurement' }, { value: 'appointment', label: 'Appointment preparation' }, { value: 'general', label: 'General health task' }]} /></Form.Item><Form.Item label="Next due" name="next_due_at" rules={[{ required: true }]}><DatePicker showTime className="full-width" /></Form.Item><Form.Item label="Schedule description" name="schedule_note" rules={[{ required: true, message: 'Describe when this task repeats' }]}><Input placeholder="e.g. Every morning" /></Form.Item><Form.Item label="Notes" name="notes"><Input.TextArea rows={3} maxLength={300} showCount /></Form.Item><div className="form-actions"><Button onClick={() => setReminderOpen(false)}>Cancel</Button><Button type="primary" htmlType="submit" loading={savingReminder}>Save Reminder</Button></div></Form></Modal>

    <Modal title="Elder care service information" open={Boolean(selectedElder)} onCancel={() => setSelectedElder(null)} footer={<Button onClick={() => setSelectedElder(null)}>Close</Button>}>{selectedElder && <><Tag color="purple">{selectedElder.category}</Tag><Title level={3}>{selectedElder.name}</Title><Paragraph>{selectedElder.summary}</Paragraph><Descriptions column={1} bordered size="small" items={[{ key: 'address', label: 'Area / address', children: selectedElder.address }, { key: 'services', label: 'Services listed', children: selectedElder.services.join(', ') }, { key: 'access', label: 'Accessibility', children: selectedElder.accessibility }, { key: 'source', label: 'Information source', children: selectedElder.source_name }, { key: 'updated', label: 'Last updated', children: formatDate(selectedElder.updated_at, true) }]} /><Alert className="directory-note" type="warning" showIcon message="Booking is not connected yet" description="Contact and live availability integration will be added after the customer confirms the responsible care-service directory." /></>}</Modal>
  </div>
}
