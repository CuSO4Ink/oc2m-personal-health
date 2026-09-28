import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { message } from 'antd'
import api from './api'
import ReportUpload from './ReportUpload'

vi.mock('./api', () => ({default:{get:vi.fn(),post:vi.fn()},apiMessage:()=> 'Upload interrupted. Try again.'}))
vi.mock('./auth', () => ({useAuth:()=>({user:{id:41}})}))
afterEach(async () => { await act(async () => { message.destroy() }) })

it('retries a failed attachment without creating a duplicate health record', async () => {
  api.get.mockResolvedValue({data:{samples_available:false}})
  api.post.mockResolvedValueOnce({data:{record:{id:81,version:1}}})
    .mockRejectedValueOnce(new Error('Interrupted'))
    .mockResolvedValueOnce({data:{attachment:{id:9}}})
  const view=render(<MemoryRouter initialEntries={['/records/upload']}><Routes><Route path="/records/upload" element={<ReportUpload />} /><Route path="/records/:id" element={<div>Review the saved report</div>} /></Routes></MemoryRouter>)
  const file=new File(['%PDF-1.4 test report'], 'check-up.pdf',{type:'application/pdf'})
  fireEvent.change(view.container.querySelector('input[type="file"]'),{target:{files:[file]}})
  await screen.findByDisplayValue('check-up')
  fireEvent.click(screen.getByRole('button',{name:'保存并自动整理'}))
  await screen.findByText('记录已保存')
  expect(api.post.mock.calls.filter(([url])=>url==='/records')).toHaveLength(1)
  fireEvent.click(screen.getByRole('button',{name:'重试上传附件'}))
  await waitFor(()=>expect(screen.getByText('Review the saved report')).toBeTruthy())
  expect(api.post.mock.calls.filter(([url])=>url==='/records')).toHaveLength(1)
  expect(api.post.mock.calls.filter(([url])=>url==='/records/81/attachments')).toHaveLength(2)
})
