import React from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ConfigProvider, message } from 'antd'
import Community from './Community'
import api from './api'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }, apiMessage: () => 'Request failed' }))
vi.mock('./auth', () => ({ useAuth: () => ({ user: { id: 91 } }) }))
vi.mock('./i18n', async (importOriginal) => ({ ...await importOriginal(), useLanguage: () => ({ t: (text) => text }), t: (text) => text }))

beforeEach(() => { vi.clearAllMocks() })
afterEach(async () => { cleanup(); await act(async () => { message.destroy() }) })

it('keeps the actual report pending when demonstrating review steps', async () => {
  const report = { id: 5, target_type: 'post', status: 'submitted', reason: 'privacy', details: 'Please review this post.', created_at: '2026-09-27T10:00:00Z' }
  api.get.mockResolvedValue({ data: { profile: { enabled: true, nickname: 'Alex' }, circles: [], posts: [], reports: [report], blocks: [], safety: { demo_review_available: true } } })
  api.post.mockResolvedValue({ data: { reports: [{ ...report, simulation_stage: 'in_review', simulation_note: 'Demo only' }], message: 'Demonstration only.' } })
  render(<ConfigProvider theme={{ token: { motion: false } }}><MemoryRouter initialEntries={['/community?tab=management']}><Community /></MemoryRouter></ConfigProvider>)
  expect(await screen.findByText('Pending review')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Demo review' }))
  expect(await screen.findByText('Reviewing (demo)')).toBeTruthy()
  expect(screen.getByText('Pending review')).toBeTruthy()
  expect(screen.getByText('Demo review only illustrates the steps. It does not resolve your report or remove content.')).toBeTruthy()
  expect(screen.queryByText('submitted')).toBeNull()
})
