import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { message } from 'antd'
import { RecordFormPage, RecordsPage } from './HealthRecords'
import api from './api'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, apiMessage: () => 'This record changed. Compare before saving.' }))
afterEach(async () => { await act(async () => { message.destroy() }) })

const base = { id: 4, title: 'Original title', record_type: 'Other', record_date: '2026-09-10', condition: 'Original topic', source_name: '个人录入', content: 'Original details', version: 1, is_editable: true }
const latest = { ...base, title: 'Updated elsewhere', content: 'New details from another session', version: 2 }

function renderEdit() {
  render(<MemoryRouter initialEntries={['/records/4/edit']}><Routes><Route path="/records/:id/edit" element={<RecordFormPage editing />} /><Route path="/records/:id" element={<div>Saved record page</div>} /></Routes></MemoryRouter>)
}

async function submitConflictingDraft() {
  renderEdit()
  fireEvent.change(await screen.findByDisplayValue('Original title'), { target: { value: 'My local title' } })
  fireEvent.change(screen.getByLabelText('本次修改原因'), { target: { value: 'Correct my title' } })
  const save = screen.getByRole('button', { name: '保存新版本' })
  fireEvent.click(save)
  await screen.findByText('保存前请处理版本冲突')
  return save
}

describe('record edit conflict resolution', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue({ data: { record: base } })
    api.patch.mockRejectedValueOnce({ response: { status: 409, data: { record: latest } } })
      .mockResolvedValue({ data: { record: { ...latest, version: 3 } } })
  })

  it('keeps the draft and blocks repeated saving until the latest version is explicitly loaded', async () => {
    const save = await submitConflictingDraft()
    expect(screen.getByLabelText('记录标题').value).toBe('My local title')
    expect(save.disabled).toBe(true)
    fireEvent.click(save)
    expect(api.patch).toHaveBeenCalledTimes(1)
    expect(api.patch.mock.calls[0][1].version).toBe(1)
    fireEvent.click(screen.getByRole('button', { name: '放弃草稿，加载最新版本' }))
    await waitFor(() => expect(screen.getByLabelText('记录标题').value).toBe('Updated elsewhere'))
    expect(screen.getByLabelText('记录说明').value).toBe('New details from another session')
    fireEvent.change(screen.getByLabelText('本次修改原因'), { target: { value: 'Reviewed latest' } })
    fireEvent.click(save)
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(2))
    expect(api.patch.mock.calls[1][1].version).toBe(2)
    expect(api.patch.mock.calls[1][1].title).toBe('Updated elsewhere')
  })

  it('requires a choice for an overlapping field and preserves remote non-overlapping changes when merging', async () => {
    const save = await submitConflictingDraft()
    const merge = screen.getByRole('button', { name: '应用合并结果' })
    expect(merge.disabled).toBe(true)
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Merge title' }))
    fireEvent.click(await screen.findByText('该字段保留我的草稿'))
    fireEvent.click(merge)
    await waitFor(() => expect(save.disabled).toBe(false))
    expect(screen.getByLabelText('记录标题').value).toBe('My local title')
    expect(screen.getByLabelText('记录说明').value).toBe('New details from another session')
    fireEvent.click(save)
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(2))
    expect(api.patch.mock.calls[1][1]).toMatchObject({ version: 2, title: 'My local title', content: 'New details from another session' })
  })
})

describe('record server pagination', () => {
  it('loads the next server page and resets to page one when filters are applied', async () => {
    vi.clearAllMocks()
    api.get.mockImplementation(async (_url, { params } = {}) => {
      const page = params?.page || 1
      const filtered = Boolean(params?.q)
      const rows = filtered ? [{ ...base, id: 1, title: 'Filtered result' }] : Array.from({ length: page === 1 ? 20 : 1 }, (_, index) => ({ ...base, id: (page - 1) * 20 + index + 1, title: `Paged record ${(page - 1) * 20 + index + 1}` }))
      return { data: { records: rows.map((record) => ({ ...record, attachments: [] })), conditions: ['Original topic'], count: rows.length, total: filtered ? 1 : 21, page, page_size: 20 } }
    })
    render(<MemoryRouter><RecordsPage /></MemoryRouter>)
    await screen.findByText('Paged record 1')
    fireEvent.click(screen.getByTitle('Next Page'))
    await screen.findByText('Paged record 21')
    expect(api.get.mock.calls.at(-1)[1].params).toMatchObject({ page: 2, page_size: 20 })
    fireEvent.change(screen.getByPlaceholderText('搜索疾病、标题或 PDF 内容，输入部分名称即可'), { target: { value: 'filtered' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索' }))
    await screen.findByText('Filtered result')
    expect(api.get.mock.calls.at(-1)[1].params).toMatchObject({ page: 1, page_size: 20, q: 'filtered' })
  })
})
