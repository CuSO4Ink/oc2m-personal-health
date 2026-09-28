import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { ConfigProvider } from 'antd'
import SharingPrivacy, { SharedContent } from './SharingPrivacy'
import ReportUpload from './ReportUpload'
import HospitalSync from './HospitalSync'
import { recordValue } from './recordDisplay'
import { auditDetails, scopeLabel } from './sharingLabels'
import { setLanguage, t } from './i18n'
import api from './api'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, apiMessage: () => 'Request failed' }))
vi.mock('./Guidance', () => ({ default: () => null }))
beforeEach(() => { vi.clearAllMocks(); setLanguage('en') })
const sample = { title: '2026-06-20 体检与检验报告', filename: 'check-up-2026-06-20.pdf', sample_display: { title: 'Health Check and Laboratory Report — 20 June 2026' } }

it('translates only approved sample metadata and preserves real user text and filenames', () => {
  expect(recordValue(sample, 'title')).toBe('Health Check and Laboratory Report — 20 June 2026')
  expect(recordValue({ title: '我的私人报告' }, 'title')).toBe('我的私人报告')
  expect(recordValue({ filename: '家人的检查.pdf' }, 'filename')).toBe('家人的检查.pdf')
  const view = render(<SharedContent data={{ records: [{ title: sample.title, record_type: 'Lab Report', sample_display: sample.sample_display }], profile: [{ section: 'allergies', revision: 3, status: 'recorded', items: [{ id: 'pollen', name: 'Pollen' }] }] }} />)
  expect(view.container.textContent).toContain('Snapshot version 3')
  expect(view.container.textContent).not.toMatch(/[\u3400-\u9fff]/)
  expect(view.container.textContent).not.toContain('sample_display')
})

it('localizes old backend scope summaries and audit structure without translating free text', () => {
  expect(scopeLabel({ kind: 'records', count: 2, label: '2 项档案摘要' })).toBe('2 record summaries')
  const details = auditDetails({ scope: [{ kind: 'attachments', count: 1, label: '1 项原始文件' }], sensitive_fields: ['condition'], filename: '家人的检查.pdf', purpose: '给医生看原文' })
  expect(details['Shared content']).toEqual(['1 original files'])
  expect(details['Hidden fields']).toEqual(['Condition'])
  expect(details.Filename).toBe('家人的检查.pdf')
  expect(details.purpose).toBe('给医生看原文')
})

it('renders expanded Sharing and access audit details in English', async () => {
  api.get.mockImplementation(async (path) => ({ data: {
    '/sharing/grants': { grants: [] }, '/sharing/recipients': { recipients: [] }, '/sharing/access-events': { events: [], total: 0 },
    '/sharing/audit-events': { events: [{ id: 1, action: 'share_scope_created', source: 'system', actor_name: '系统整理', result: 'allowed', created_at: '2026-09-28T10:00:00Z', details: { scope: [{ kind: 'records', count: 1, label: '1 项档案摘要' }], shared_fields: ['title', 'record_type'] } }], total: 1 },
  }[path] }))
  const view = render(<ConfigProvider theme={{ token: { motion: false } }}><MemoryRouter initialEntries={['/sharing?tab=audit']}><SharingPrivacy /></MemoryRouter></ConfigProvider>)
  await waitFor(() => expect(view.container.querySelector('.ant-table-row-expand-icon')).toBeTruthy())
  fireEvent.click(view.container.querySelector('.ant-table-row-expand-icon'))
  await screen.findByText(/Shared content/)
  expect(view.container.textContent).not.toMatch(/[\u3400-\u9fff]/)
})

it('shows English hospital sample names and removes the additional single-report download', async () => {
  api.get.mockResolvedValue({ data: { jobs: [{ id: 1, revision: 1, items: [{ ...sample, external_id: 'hospital-lab-1', record_date: '2026-06-20', status: 'ready', selected_type: 'Lab Report' }], counts: { ready: 1, imported: 0, duplicate: 0, failed: 0 } }] } })
  const hospital = render(<MemoryRouter><HospitalSync onImported={() => {}} onClose={() => {}} /></MemoryRouter>)
  await screen.findByText('Health Check and Laboratory Report — 20 June 2026')
  expect(hospital.container.textContent).not.toMatch(/[\u3400-\u9fff]/)
  hospital.unmount(); vi.clearAllMocks()
  const upload = render(<MemoryRouter><ReportUpload /></MemoryRouter>)
  expect(upload.container.querySelector('[href="/api/demo/sample-report"]')).toBeNull()
  expect(api.get).not.toHaveBeenCalled()
})

it('translates backend processing and confirmation messages with variable counts', () => {
  for (const text of ['文档共有 235 页，本次最多处理 200 页；请拆分后续页面继续整理。', '已识别 3/5 页。未识别页暂时无法全文检索，请查看原件并重试。', '已确认 3 条指标、2 条健康史；跳过或关联 1 条已有内容。']) expect(t(text)).not.toMatch(/[\u3400-\u9fff]/)
})
