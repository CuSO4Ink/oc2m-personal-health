import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import { beforeEach, expect, it, vi } from 'vitest'
import CareServices from './CareServices'
import api from './api'
import { setLanguage } from './i18n'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, apiMessage: () => 'Request failed' }))
vi.mock('./Guidance', () => ({ default: () => null }))
vi.mock('antd', async (load) => {
  const actual = await load()
  function DateInput({ value, id }) { return <input id={id} value={value?.format('YYYY-MM-DD') || ''} readOnly /> }
  DateInput.RangePicker = function RangeInput() { return <div>Date range</div> }
  function Choice({ options = [], value, onChange, id, 'aria-label': label, placeholder }) { return <select id={id} aria-label={label} value={value ?? ''} onChange={(event) => onChange(options.find((option) => String(option.value) === event.target.value)?.value)}><option value="">{placeholder}</option>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select> }
  return { ...actual, Select: Choice, DatePicker: DateInput }
})
const future = new Date(Date.now() + 86400000).toISOString()
const service = { id: 1, name: 'General review', specialty: 'General practice', duration_minutes: 20, appointment_mode: 'in_person', facility: { name: 'Maple Grove Clinic', address: '128 Maple Avenue' }, clinicians: [{ id: 7, full_name: 'Dr. Lee', role: 'General practitioner' }], slots: [{ id: 10, starts_at: future, available: true, available_places: 3 }, { id: 11, starts_at: '2020-01-01T09:00:00Z', available: true, available_places: 3 }] }
beforeEach(() => {
  vi.clearAllMocks(); setLanguage('en')
  api.get.mockImplementation(async (path) => ({ data: {
    '/services/medical': { services: [service] }, '/services/appointments': { appointments: [] }, '/services/reminders': { reminders: [] },
    '/records': { records: [], total: 0 }, '/sharing/scope-options': { profile: { sections: { allergies: { status: 'recorded', items: [{ id: 'pollen', name: 'Pollen' }] } } }, measurements: [] },
  }[path] }))
  api.post.mockImplementation(async (path) => ({ data: path.endsWith('draft-preview') ? { preview_token: 'reviewed-scope', records: [], attachments: [], profile: [{ section: 'allergies', revision: 1, status: 'recorded', items: [{ id: 'pollen', name: 'Pollen' }] }], measurements: [] } : { appointment: { id: 99 } } }))
})
async function openBooking() {
  const view = render(<ConfigProvider theme={{ token: { motion: false } }}><MemoryRouter initialEntries={['/services?tab=appointments']}><CareServices /></MemoryRouter></ConfigProvider>)
  await screen.findByText('General review')
  fireEvent.click(within(view.container.querySelector('.medical-service-card')).getByRole('button'))
  const dialog = await screen.findByRole('dialog', { name: 'Book an appointment' })
  fireEvent.change(within(dialog).getByLabelText('Clinician'), { target: { value: '7' } })
  fireEvent.change(within(dialog).getByLabelText('Available time (your local time)'), { target: { value: '10' } })
  fireEvent.change(within(dialog).getByLabelText('Reason for appointment'), { target: { value: 'Follow up on my results' } })
  return dialog
}
it('offers only future times and books the chosen doctor without automatically sharing records', async () => {
  const dialog = await openBooking()
  expect(within(dialog).getByLabelText('Available time (your local time)').querySelector('option[value="11"]')).toBeNull()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Review appointment' }))
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Confirm appointment' }))
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/services/appointments', { recipient_id: 7, slot_id: 10, reason: 'Follow up on my results' }))
  expect(api.get.mock.calls.some(([path]) => path === '/services/elder-care')).toBe(false)
})
it('previews an optional selected scope before sending it with the booking', async () => {
  const dialog = await openBooking()
  fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Share selected health information with this clinician' }))
  fireEvent.click(await within(dialog).findByRole('tab', { name: 'Health history' }))
  fireEvent.click(await within(dialog).findByRole('checkbox', { name: /Whole category:/ }))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Review appointment' }))
  const confirm = await within(dialog).findByRole('button', { name: 'Confirm appointment' })
  expect(api.post.mock.calls).toHaveLength(1)
  const preview = api.post.mock.calls[0]
  expect(preview[0]).toBe('/sharing/grants/draft-preview')
  expect(preview[1].recipient_id).toBe(7)
  expect(preview[1].profile_sections).toEqual(['allergies'])
  expect(preview[1].attachment_ids).toEqual([])
  fireEvent.click(confirm)
  await waitFor(() => expect(api.post.mock.calls.some(([path, body]) => path === '/services/appointments' && body.sharing_draft?.preview_token === 'reviewed-scope')).toBe(true))
})
