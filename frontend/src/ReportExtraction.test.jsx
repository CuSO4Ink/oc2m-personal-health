import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { message } from 'antd'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ReportExtraction from './ReportExtraction'
import api from './api'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, apiMessage: () => 'This extraction changed. Reload before continuing.' }))

const record = { id: 4, title: 'Source report', archived: false }
afterEach(async () => { await act(async () => { message.destroy() }) })
const candidate = { id: 'bp', metric_type: 'blood_pressure', value: 128, secondary_value: 82, unit: 'mmHg', context: '', evidence: 'Blood pressure: 128/82 mmHg', line_number: 2 }
const draft = { id: 9, record_id: 4, filename: 'Report.pdf', method: 'pdf_text', warnings: [], original_text: candidate.evidence, reviewed_text: candidate.evidence, candidates: [candidate], revision: 1, page_info: { total_pages: 1, processed_pages: [1] } }

function review(props = {}) { render(<MemoryRouter><ReportExtraction record={record} attachment={{ id: 2, filename: 'Report.pdf' }} open onClose={vi.fn()} {...props} /></MemoryRouter>) }

describe('explicit report-reading review', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue({ data: { pdf_text: true, ocr: { available: true, languages: ['en-US'] } } })
    api.post.mockResolvedValue({ data: { extraction: draft } })
  })

  it('never extracts on open or selects candidates automatically, and requires a date before import', async () => {
    review()
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '提取待确认内容' }))
    const select = await screen.findByLabelText('选择血压候选2')
    expect(select.checked).toBe(false)
    const importButton = screen.getByRole('button', { name: /确认导入/ })
    expect(importButton.disabled).toBe(true)
    fireEvent.click(select)
    fireEvent.click(screen.getByLabelText(/我已核对所选内容/))
    fireEvent.click(importButton)
    await screen.findByText('请补全所选指标的数值、测量时间和血糖测量场景。')
    expect(api.post).toHaveBeenCalledTimes(1)
  })

  it('keeps corrected text and stops reparsing after conflict until explicit reload', async () => {
    api.get.mockImplementation(async (url) => url.endsWith('/9') ? { data: { extraction: draft } } : { data: { ocr: { available: true, languages: [] } } })
    api.patch.mockRejectedValue({ response: { status: 409 } })
    review({ extractionId: 9 })
    await screen.findByLabelText('选择血压候选2')
    fireEvent.click(screen.getByText('原文与校对'))
    const textarea = await screen.findByLabelText('报告原文')
    fireEvent.change(textarea, { target: { value: 'Blood pressure: 130/82 mmHg' } })
    const reparse = screen.getByRole('button', { name: '按此原文重新查找' })
    fireEvent.click(reparse)
    await screen.findByText('This extraction changed. Reload before continuing.')
    expect(textarea.value).toBe('Blood pressure: 130/82 mmHg')
    expect(reparse.disabled).toBe(true)
    fireEvent.click(reparse)
    expect(api.patch).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: '放弃修改并加载最新' }))
    await waitFor(() => expect(textarea.value).toBe(candidate.evidence))
  })

  it('prefills an explicit report time and submits readings and health facts together after confirmation', async () => {
    const ready = {...draft, profile_revision:3, candidates:[{...candidate,measured_at:'2026-09-20T08:00:00'}], facts:[{id:'diagnosis',section:'past_history',name:'Hypertension',detail:'Report statement',line_number:3,evidence:'Diagnosis: Hypertension'}]}
    api.get.mockImplementation(async (url) => url.endsWith('/9') ? {data:{extraction:ready}} : {data:{ocr:{available:true,languages:[]}}})
    api.post.mockResolvedValue({data:{extraction:{...ready,confirmed_at:'2026-09-20T08:30:00Z'},measurements:[],profile_facts:[],message:'已确认'}})
    review({extractionId:9})
    // Labeled controls avoid repeated visibility/name scans of AntD's retained
    // inactive tab panel in jsdom; real components and user confirmation stay intact.
    const readingSelect = await screen.findByLabelText('选择血压候选2')
    fireEvent.click(readingSelect)
    expect(screen.getByLabelText('血压测量时间').value).toContain('2026-09-20')
    const factTab = screen.getByRole('tab',{name:'健康史（1）'})
    fireEvent.click(factTab)
    const factSelect = await screen.findByLabelText('选择既往病史候选3')
    fireEvent.click(factSelect)
    const ack = screen.getByLabelText(/我已核对所选内容/)
    fireEvent.click(ack)
    fireEvent.click(screen.getByText('确认导入（2）'))
    await waitFor(()=>expect(api.post).toHaveBeenCalledTimes(1))
    expect(api.post.mock.calls[0][1]).toMatchObject({profile_revision:3,acknowledged:true,facts:[{candidate_id:'diagnosis',name:'Hypertension'}],selections:[{candidate_id:'bp',value:128}]})
    await screen.findByText('确认记录已保留，可随时回查来源。')
  })
})
