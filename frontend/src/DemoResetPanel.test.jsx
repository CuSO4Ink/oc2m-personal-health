import React from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import DemoResetPanel from './DemoResetPanel'
import api from './api'
import { setLanguage } from './i18n'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn() }, apiMessage: error => error.response?.data?.message || 'Reset failed' }))
beforeEach(() => { setLanguage('en'); api.get.mockReset(); api.post.mockReset() })

it('does not offer database clearing outside the dedicated demo', async () => {
  api.get.mockResolvedValue({data: {available: false}})
  const { container } = render(<DemoResetPanel accountEmail="owner@example.test" />)
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/demo/reset-account'))
  expect(container.textContent).toBe('')
  expect(api.post).not.toHaveBeenCalled()
})

it('discloses account and conversation scope, and cancellation never clears data', async () => {
  api.get.mockResolvedValue({data: {available: true}})
  render(<DemoResetPanel accountEmail="owner@example.test" />)
  fireEvent.click(await screen.findByRole('button', {name: 'Reset my demo data'}))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('owner@example.test')).toBeTruthy()
  expect(within(dialog).getByText(/cleared for both participants/)).toBeTruthy()
  expect(within(dialog).getByText(/Other accounts’ health records are not affected/)).toBeTruthy()
  expect(api.post).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', {name: 'Cancel'}))
  expect(api.post).not.toHaveBeenCalled()
})

it('requires confirmation, sends no target user id, then returns to the empty workflow', async () => {
  api.get.mockResolvedValue({data: {available: true}})
  api.post.mockResolvedValue({data: {reset: true}})
  const onReset = vi.fn()
  render(<DemoResetPanel accountEmail="owner@example.test" onReset={onReset} />)
  fireEvent.click(await screen.findByRole('button', {name: 'Reset my demo data'}))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', {name: 'Reset my demo data'}))
  await waitFor(() => expect(onReset).toHaveBeenCalledOnce())
  expect(api.post).toHaveBeenCalledExactlyOnceWith('/demo/reset-account', {confirmed: true})
})

it('retains the dialog on failure and switches language before confirmation', async () => {
  api.get.mockResolvedValue({data: {available: true}})
  api.post.mockRejectedValue({response: {data: {message: 'Reset failed'}}})
  const onReset = vi.fn()
  render(<DemoResetPanel accountEmail="owner@example.test" onReset={onReset} />)
  fireEvent.click(await screen.findByRole('button', {name: 'Reset my demo data'}))
  await act(async () => setLanguage('zh'))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('重置当前账号的演示数据？')).toBeTruthy()
  fireEvent.click(within(dialog).getByRole('button', {name: '重置我的演示数据'}))
  await screen.findByText('Reset failed')
  expect(onReset).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog')).toBeTruthy()
})
