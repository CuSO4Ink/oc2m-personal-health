import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigProvider, message } from 'antd'
import CircleDetailsDrawer from './CircleDetailsDrawer'
import api from './api'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn() }, apiMessage: () => 'Request failed' }))
vi.mock('./i18n', async (importOriginal) => ({ ...await importOriginal(), useLanguage: () => ({ t: (text, variables) => text.replace(/\{(\w+)\}/g, (match, key) => variables?.[key] ?? match) }) }))
vi.setConfig({ testTimeout: 20000 })

const circle = { id: 4, name: 'Everyday routines', topic: 'Peer support', description: 'Small changes in daily life.', guidance: 'Respect each other.', joined: false, member_count: 3 }
const member = { public_id: 'public-jamie', nickname: 'Jamie', can_request: true, connection_status: 'available', connection_id: null }
function mount(props = {}) {
  return render(<ConfigProvider theme={{ token: { motion: false } }}><CircleDetailsDrawer circle={circle} onClose={vi.fn()} onChanged={vi.fn()} onDiscussion={vi.fn()} onConnections={vi.fn()} {...props} /></ConfigProvider>)
}
beforeEach(() => { vi.clearAllMocks() })
afterEach(async () => { cleanup(); await act(async () => { message.destroy() }) })

describe('Circle introduction and member contacts', () => {
  it('shows the introduction before joining, then fetches members and sends an explicit circle request', async () => {
    const onChanged = vi.fn()
    api.get.mockImplementation(async (url) => ({ data: url.endsWith('/members') ? { members: [member], total: 1, page: 1 } : { circle } }))
    api.post.mockImplementation(async (url) => ({ data: url.endsWith('/membership') ? { circle: { ...circle, joined: true } } : { connection: { id: 99 } } }))
    mount({ onChanged })
    expect(await screen.findByText(circle.description)).toBeTruthy()
    expect(screen.getByText(circle.guidance)).toBeTruthy()
    expect(api.get).not.toHaveBeenCalledWith('/community/circles/4/members', expect.anything())
    fireEvent.click(screen.getByRole('tab', { name: 'Members' }))
    expect(screen.getByText('Join this circle to see its member directory.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Join circle' }))
    expect(await screen.findByText('Jamie')).toBeTruthy()
    expect(screen.getByText('1 visible members')).toBeTruthy()
    expect(screen.queryByText('3 visible members')).toBeNull()
    expect(onChanged).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Add friend' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/community/connections', { circle_id: 4, public_id: 'public-jamie' }))
    expect(await screen.findByText('Request sent')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Message' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Add friend' })).toBeNull()
  })

  it('opens an existing friend conversation, and routes incoming requests to consent review', async () => {
    const onConnections = vi.fn()
    const joined = { ...circle, joined: true }
    api.get.mockImplementation(async (url) => ({ data: url.endsWith('/members') ? { members: [{ ...member, connection_status: 'friends', can_request: false, connection_id: 42 }, { ...member, public_id: 'public-alex', nickname: 'Alex', connection_status: 'incoming', can_request: false, connection_id: 43 }], total: 2, page: 1 } : { circle: joined } }))
    mount({ circle: joined, onConnections })
    fireEvent.click(screen.getByRole('tab', { name: 'Members' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Message' }))
    expect(onConnections).toHaveBeenCalledWith(42)
    fireEvent.click(screen.getByRole('button', { name: 'Review friend request' }))
    expect(onConnections).toHaveBeenCalledWith()
    expect(screen.queryByRole('button', { name: 'Add friend' })).toBeNull()
  })

  it('refreshes the directory after contact becomes unavailable without claiming a request succeeded', async () => {
    const joined = { ...circle, joined: true }
    let available = true
    api.get.mockImplementation(async (url) => ({ data: url.endsWith('/members') ? { members: available ? [member] : [], total: available ? 1 : 0, page: 1 } : { circle: joined } }))
    api.post.mockImplementation(async () => { available = false; throw new Error('Member unavailable') })
    mount({ circle: joined })
    fireEvent.click(screen.getByRole('tab', { name: 'Members' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Add friend' }))
    expect(await screen.findByText('No discoverable members to show yet.')).toBeTruthy()
    expect(screen.getByText('0 visible members')).toBeTruthy()
    expect(screen.queryByText('Request sent')).toBeNull()
    expect(screen.queryByText('Jamie')).toBeNull()
  })
})
