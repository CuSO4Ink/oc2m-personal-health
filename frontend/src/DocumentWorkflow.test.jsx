import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { message } from 'antd'
import { RecordsPage } from './HealthRecords'
import HospitalSync from './HospitalSync'
import RecordAttachments from './RecordAttachments'
import api from './api'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }, apiMessage: () => 'Request failed' }))
vi.mock('./DocumentPreview', () => ({ default: ({ url, initialPage }) => <div data-testid="document-source">{url}#page={initialPage}</div> }))
vi.mock('./ReportExtraction', () => ({ default: ({ open, extractionId }) => open ? <div>Review draft {extractionId}</div> : null }))
vi.mock('./auth', () => ({ useAuth: () => ({ user: { id: 1 } }) }))
beforeEach(() => vi.clearAllMocks())
afterEach(async () => { await act(async () => { message.destroy() }) })

it('shows a page-specific PDF match and keeps the review queue separate from search', async () => {
  api.get.mockResolvedValue({ data: { records: [{ id: 8, title: 'Ultrasound report', record_type: 'Imaging', record_date: '2026-09-20', source_type: 'hospital', source_name: 'Demo hospital', attachments: [{ id: 12 }], search_hits: [{ attachment_id: 12, filename: 'ultrasound.pdf', page: 6, snippet: 'Thyroid nodule follow-up', path: '/records/8?document=12&page=6' }] }], pending_records: [{ record_id: 9, title: 'Vitals to review', extractions: [{ candidate_count: 3, fact_count: 1 }] }], total: 1, page: 1, page_size: 20 } })
  render(<MemoryRouter><RecordsPage /></MemoryRouter>)
  const link = await screen.findByRole('link', { name: /ultrasound.pdf.*第 6 页/ })
  expect(link.getAttribute('href')).toBe('/records/8?document=12&page=6')
  fireEvent.click(screen.getByText('待核对信息 · 1 份资料'))
  expect(screen.getByText('3 条读数 · 1 条健康信息')).toBeTruthy()
  expect(screen.getByRole('link', { name: '核对信息' }).getAttribute('href')).toBe('/records/9?review=1')
})

it('previews the batch before importing and never opens individual extraction dialogs', async () => {
  const onImported = vi.fn()
  const item = { external_id: 'lab-1', title: '九月检验报告', filename: 'lab.pdf', record_date: '2026-09-20', selected_type: 'Lab Report', status: 'ready' }
  const job = { id: 3, revision: 1, items: [item], counts: { ready: 1, imported: 0, duplicate: 0, failed: 0 } }
  api.get.mockResolvedValue({ data: { jobs: [] } })
  api.post.mockResolvedValueOnce({ data: { job } }).mockResolvedValueOnce({ data: { job: { ...job, revision: 2, items: [{ ...item, status: 'imported', record_id: 8, index_status: 'complete' }], counts: { ready: 0, imported: 1, duplicate: 0, failed: 0 } } } })
  render(<MemoryRouter><HospitalSync onImported={onImported} onClose={() => {}} /></MemoryRouter>)
  fireEvent.click(screen.getByRole('button', { name: '查看可同步的资料' }))
  await screen.findByText('九月检验报告')
  expect(api.post).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: '同步这 1 份资料' }))
  await screen.findByText(/同步完成。发现的候选/)
  fireEvent.click(screen.getByText(/最近一次同步 · 1 份已同步/))
  await screen.findByText('全文可搜索')
  expect(onImported).toHaveBeenCalledTimes(1)
  expect(api.post.mock.calls[1]).toEqual(['/records/imports/3/confirm', { revision: 1, selections: { 'lab-1': 'Lab Report' } }])
  expect(screen.queryByText(/Review draft/)).toBeNull()
})

it('opens the exact source page and refreshes partial OCR without recreating a record', async () => {
  const attachment = { id: 12, filename: 'source.pdf', content_type: 'application/pdf', size: 2000, index: { status: 'partial', total_pages: 6, processed_pages: [1], warnings: ['Unread page'] } }
  const record = { id: 8, attachments: [attachment], is_editable: false, pending_extractions: [] }
  const onChange = vi.fn()
  api.post.mockResolvedValue({ data: { record: { ...record, attachments: [{ ...attachment, index: { status: 'complete', total_pages: 6, processed_pages: [1, 2, 3, 4, 5, 6] } }] } } })
  render(<MemoryRouter initialEntries={['/records/8?document=12&page=6']}><RecordAttachments record={record} onChange={onChange} /></MemoryRouter>)
  await waitFor(() => expect(screen.getByTestId('document-source').textContent).toBe('/api/records/8/attachments/12#page=6'))
  fireEvent.click(screen.getByRole('button', { name: '关闭预览', exact: true }))
  fireEvent.click(screen.getByRole('button', { name: '重新整理' }))
  await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1))
  expect(api.post).toHaveBeenCalledWith('/records/8/attachments/12/index')
})
