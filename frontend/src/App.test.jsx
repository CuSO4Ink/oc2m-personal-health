import React from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AppShell } from './App'
import api from './api'

vi.mock('./api', () => ({ default: { get: vi.fn() }, apiMessage: () => 'Request failed' }))
vi.mock('./auth', () => ({ AuthProvider: ({ children }) => children, useAuth: () => ({ user: { initials: 'TO', full_name: 'Test Owner' }, logout: vi.fn() }) }))

function renderShell() {
  return render(<MemoryRouter initialEntries={['/overview']}><Routes><Route element={<AppShell />}><Route path="/overview" element={<div>Overview content</div>} /><Route path="/records" element={<div>Records content</div>} /><Route path="/account" element={<div>Account preferences</div>} /></Route></Routes></MemoryRouter>)
}

describe('personal navigation and notification state', () => {
  let communityEnabled
  let unread
  beforeEach(() => {
    communityEnabled = false
    unread = 2
    api.get.mockImplementation(async (url) => url === '/community' ? { data: { profile: { enabled: communityEnabled } } } : { data: { summary: { unread } } })
  })

  it('opens mobile navigation and reaches records, including an account fallback', async () => {
    renderShell()
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    const mobile = await screen.findByRole('menu', { name: '移动端导航' })
    fireEvent.click(within(mobile).getByText('健康资料'))
    expect(await screen.findByText('Records content')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '打开导航' }))
    fireEvent.click(await screen.findByRole('button', { name: '账户与安全' }))
    expect(await screen.findByText('Account preferences')).toBeTruthy()
  })

  it('hides the optional community until enabled and refreshes unread without navigation', async () => {
    renderShell()
    await screen.findByRole('button', { name: '打开通知，2 条未读' })
    expect(within(screen.getByRole('menu', { name: '主导航' })).queryByText('病友交流')).toBeNull()
    communityEnabled = true
    await act(async () => { window.dispatchEvent(new Event('community:changed')) })
    expect(await screen.findByText('病友交流')).toBeTruthy()
    communityEnabled = false
    unread = 0
    await act(async () => { window.dispatchEvent(new Event('community:changed')); window.dispatchEvent(new Event('notifications:changed')) })
    await waitFor(() => expect(screen.queryByText('病友交流')).toBeNull())
    expect(await screen.findByRole('button', { name: '打开通知，0 条未读' })).toBeTruthy()
  })
})
