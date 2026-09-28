import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import { beforeEach, expect, it, vi } from 'vitest'
import SharingPrivacy, { SharedContent } from './SharingPrivacy'
import api from './api'
import { setLanguage } from './i18n'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, apiMessage: (error) => error.response?.data?.message || 'Request failed' }))
vi.mock('./Guidance', () => ({ default: ({ title, children }) => <details><summary>{title}</summary>{children}</details> }))
// Calendar widgets are covered in browser QA; keep these tests focused on permission choices and requests.
vi.mock('antd', async (load) => {
  const actual = await load()
  function DateInput({ value, id, 'aria-label': label }) { return <input id={id} aria-label={label} value={value?.format('YYYY-MM-DD') || ''} readOnly /> }
  DateInput.RangePicker = function RangeInput({ value, 'aria-label': label }) { return <input aria-label={label} value={value?.map((item) => item.format('YYYY-MM-DD')).join(' — ') || ''} readOnly /> }
  return { ...actual, DatePicker: DateInput }
})
const sections = { past_history: { status: 'unknown', items: [] }, family_history: { status: 'unknown', items: [] }, medications: { status: 'unknown', items: [] }, allergies: { status: 'recorded', items: [{ id: 'pollen', name: '花粉过敏', sensitive: false }] } }

beforeEach(() => {
  vi.clearAllMocks(); setLanguage('zh')
  api.get.mockImplementation(async (path) => {
    const responses = {
      '/sharing/grants': { grants: [] }, '/sharing/recipients': { recipients: [{ id: 3, full_name: 'Demo clinician', role: 'Doctor', organisation: 'Demo clinic' }] },
      '/sharing/access-events': { events: [], total: 0 }, '/sharing/audit-events': { events: [], total: 0 },
      '/records': { records: [{ id: 1, title: '检查摘要', record_type: 'Lab Report', record_date: '2026-09-20', attachments: [{ id: 2, filename: 'source.pdf', content_type: 'application/pdf', size: 300 }] }], total: 1 },
      '/sharing/scope-options': { profile: { revision: 4, sections }, measurements: [] },
    }
    return { data: responses[path] }
  })
  api.post.mockImplementation(async (path) => ({ data: path.endsWith('draft-preview') ? { preview_token: 'reviewed-snapshot', records: [], attachments: [], profile: [], measurements: [] } : { grant: { id: 10 } } }))
})

async function openForm() {
  render(<ConfigProvider theme={{ token: { motion: false } }}><MemoryRouter><SharingPrivacy /></MemoryRouter></ConfigProvider>)
  await waitFor(() => expect(screen.getByRole('button', { name: /新建共享/ }).disabled).toBe(false), { timeout: 8000 })
  fireEvent.click(screen.getByRole('button', { name: /新建共享/ }))
  const dialog = await screen.findByRole('dialog', { name: '新建共享' })
  await within(dialog).findByText('检查摘要')
  fireEvent.mouseDown(within(dialog).getByLabelText('演示接收人'))
  fireEvent.click(await screen.findByText('Demo clinician · 医生 · Demo clinic', { selector: '.ant-select-item-option-content' }))
  fireEvent.change(within(dialog).getByLabelText('共享用途'), { target: { value: '复诊准备' } })
  return dialog
}

it('lets a user share only a selected original file after explicit acknowledgement and previews before committing', async () => {
  const dialog = await openForm()
  fireEvent.click(within(dialog).getByRole('checkbox', { name: '完整原件：source.pdf' }))
  await waitFor(() => expect(within(dialog).getByRole('button', { name: '预览实际共享内容' }).disabled).toBe(false))
  expect(within(dialog).getByRole('checkbox', { name: '我已检查并同意共享完整原件；隐藏文字字段不会自动给 PDF 或图片打码。' }).checked).toBe(false)
  expect(api.post).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('checkbox', { name: '我已检查并同意共享完整原件；隐藏文字字段不会自动给 PDF 或图片打码。' }))
  fireEvent.click(within(dialog).getByRole('button', { name: '预览实际共享内容' }))
  await within(dialog).findByRole('button', { name: '确认授权' }, { timeout: 8000 })
  expect(api.post.mock.calls[0][1].record_ids).toEqual([])
  expect(api.post.mock.calls[0][1].attachment_ids).toEqual([2])
  expect(api.post.mock.calls[0][1].acknowledge_original_files).toBe(true)
  await waitFor(() => expect(within(dialog).getByRole('button', { name: /确认授权/ }).disabled).toBe(false))
  fireEvent.click(within(dialog).getByRole('button', { name: '确认授权' }))
  await waitFor(() => expect(api.post.mock.calls.some(([path, body]) => path === '/sharing/grants' && body.preview_token === 'reviewed-snapshot')).toBe(true))
}, 30000)

it('shares selected health history without requiring any document and keeps a changed-preview error recoverable', async () => {
  const dialog = await openForm()
  fireEvent.click(within(dialog).getByRole('tab', { name: '健康史' }))
  fireEvent.click(within(dialog).getByRole('checkbox', { name: /整个类别：过敏情况/ }))
  await waitFor(() => expect(within(dialog).getByRole('button', { name: '预览实际共享内容' }).disabled).toBe(false))
  fireEvent.click(within(dialog).getByRole('button', { name: '预览实际共享内容' }))
  await within(dialog).findByRole('button', { name: '确认授权' }, { timeout: 8000 })
  expect(api.post.mock.calls[0][1].profile_sections).toEqual(['allergies'])
  expect(api.post.mock.calls[0][1].record_ids).toEqual([])
  api.post.mockRejectedValueOnce({ response: { status: 409, data: { message: '资料已变化，请重新预览。' } } })
  await waitFor(() => expect(within(dialog).getByRole('button', { name: /确认授权/ }).disabled).toBe(false))
  fireEvent.click(within(dialog).getByRole('button', { name: '确认授权' }))
  const selected = await within(dialog).findByRole('checkbox', { name: /整个类别：过敏情况/ }, { timeout: 8000 })
  expect(selected.checked).toBe(true)
}, 30000)

it('renders the selected snapshots and exposes file download only when its controlled URL is supplied', () => {
  const file = { id: 2, filename: 'source.pdf', size: 300, preview_url: '/api/sharing/grants/10/attachments/2' }
  const onFile = vi.fn()
  const view = render(<SharedContent data={{ attachments: [file], profile: [{ section: 'allergies', revision: 4, status: 'recorded', items: [{ id: 'private-id', name: '花粉过敏', internal_source: 'UNSHARED SOURCE' }] }] }} onFile={onFile} />)
  expect(screen.getByText('花粉过敏')).toBeTruthy()
  expect(screen.queryByText('UNSHARED SOURCE')).toBeNull()
  expect(screen.queryByRole('button', { name: '下载原件' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '预览原件' }))
  expect(onFile).toHaveBeenCalledWith(file)
  view.rerender(<SharedContent data={{ attachments: [{ ...file, download_url: '/api/sharing/grants/10/attachments/2?download=1' }] }} onFile={onFile} />)
  expect(screen.getByRole('button', { name: '下载原件' })).toBeTruthy()
})


it('keeps the record-activity tab selected when its pagination reloads data', async () => {
  const base = api.get.getMockImplementation()
  api.get.mockImplementation(async (path, config) => path === '/sharing/audit-events' ? { data: { events: [{ id: config.params.page, action: 'record_created', created_at: '2026-09-20T10:00:00Z', source: 'owner', actor_name: 'Owner', details: {}, result: 'allowed' }], total: 21 } } : base(path, config))
  render(<ConfigProvider theme={{ token: { motion: false } }}><MemoryRouter initialEntries={['/sharing?tab=audit']}><SharingPrivacy /></MemoryRouter></ConfigProvider>)
  const tab = await screen.findByRole('tab', { name: '档案操作记录' })
  expect(tab.getAttribute('aria-selected')).toBe('true')
  fireEvent.click(screen.getByTitle('2'))
  await waitFor(() => expect(api.get.mock.calls.some(([path, config]) => path === '/sharing/audit-events' && config.params.page === 2)).toBe(true))
  await waitFor(() => expect(screen.getByRole('tab', { name: '档案操作记录' }).getAttribute('aria-selected')).toBe('true'))
})
