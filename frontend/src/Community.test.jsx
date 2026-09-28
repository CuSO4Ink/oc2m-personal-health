import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import Community from './Community'
import CommunityConnections from './CommunityConnections'
import api from './api'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }, apiMessage: () => 'Request failed' }))
vi.mock('./auth', () => ({ useAuth: () => ({ user: { id: 91 } }) }))
vi.setConfig({ testTimeout: 20000 })

const profile = { enabled: true, nickname: 'Member abc123', public_id: 'test-member', invite_code: 'PRIVATE-CODE', discoverable: false }
const circle = { id: 1, name: 'Daily wellbeing', topic: 'Wellbeing', joined: true, member_count: 4, description: 'Everyday experiences' }
const post = { id: 7, author_name: 'Anonymous member', anonymous: true, is_owner: false, can_connect: false, circle, body: 'Walking with a friend helped me keep a routine.', created_at: '2026-09-27T10:00:00Z', like_count: 0, liked: false, comment_count: 1, comments: [{ id: 8, author_name: 'Anonymous member', anonymous: true, is_owner: false, body: 'I enjoyed a short walk too.', created_at: '2026-09-27T10:10:00Z' }] }

function mount(element, path = '/community') { return render(<ConfigProvider theme={{ token: { motion: false } }}><MemoryRouter initialEntries={[path]}>{element}</MemoryRouter></ConfigProvider>) }

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  api.get.mockImplementation(async (url) => {
    if (url === '/community') return { data: { profile, circles: [circle], posts: [post], has_more: false, blocks: [], reports: [], safety: {} } }
    if (url === '/community/connections') return { data: { friends: [], incoming: [], outgoing: [] } }
    throw new Error('Unexpected GET ' + url)
  })
})

describe('Community navigation and progressive disclosure', () => {
  it('leads with the feed, expands replies on request and keeps anonymous posts uncontactable', async () => {
    mount(<Community />)
    await screen.findByText(post.body)
    expect(screen.getByText('动态').getAttribute('aria-selected')).toBe('true')
    expect(screen.queryByText(post.comments[0].body)).toBeNull()
    expect(screen.queryByLabelText('社区昵称')).toBeNull()
    fireEvent.click(screen.getByText('1 条评论').closest('button'))
    expect(await screen.findByText(post.comments[0].body)).toBeTruthy()
    expect(screen.getByLabelText('匿名评论').checked).toBe(true)
    fireEvent.click(screen.getByLabelText('帖子菜单：Anonymous member'))
    expect(await screen.findByText('举报帖子')).toBeTruthy()
    expect(screen.queryByText('申请好友')).toBeNull()
  })

  it('offers a circle next step from an empty feed, instead of a dead end', async () => {
    api.get.mockResolvedValue({ data: { profile: { ...profile, nickname: 'Alex' }, circles: [{ ...circle, joined: false }], posts: [], blocks: [], reports: [], safety: {} } })
    mount(<Community />)
    fireEvent.click((await screen.findByText('浏览圈子')).closest('button'))
    expect(screen.getByText('圈子').getAttribute('aria-selected')).toBe('true')
    expect(await screen.findByText('加入圈子')).toBeTruthy()
  })

  it('remembers skipping the nickname prompt, while settings remain reachable and save the identity', async () => {
    const first = mount(<Community />)
    fireEvent.click((await screen.findByText('稍后')).closest('button'))
    first.unmount()
    mount(<Community />)
    await screen.findByText(post.body)
    expect(screen.queryByText('设置昵称')).toBeNull()
    fireEvent.click(screen.getByText('社区设置').closest('button'))
    const nickname = await screen.findByLabelText('社区昵称')
    fireEvent.change(nickname, { target: { value: 'Willow' } })
    api.patch.mockResolvedValue({ data: { profile: { ...profile, nickname: 'Willow' } } })
    fireEvent.click(screen.getByText('保存社区身份').closest('button'))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/community/identity', { nickname: 'Willow', discoverable: false }))
    await waitFor(() => expect(document.querySelector('.ant-drawer-open')).toBeNull())
    expect(screen.getByText(post.body)).toBeTruthy()
  })
})

describe('Friend request drawer', () => {
  it('requires accepting a request before presenting a conversation, and preserves the consent action', async () => {
    const pending = { id: 12, nickname: 'Willow', can_message: false, unread: 0 }
    let accepted = false
    api.get.mockImplementation(async () => ({ data: { friends: accepted ? [{ ...pending, can_message: true }] : [], incoming: accepted ? [] : [pending], outgoing: [] } }))
    api.patch.mockImplementation(async () => { accepted = true; return { data: {} } })
    mount(<CommunityConnections profile={profile} onReport={vi.fn()} onChanged={vi.fn()} onOpenSettings={vi.fn()} />)
    fireEvent.click((await screen.findByText('查看申请')).closest('button'))
    const dialog = await screen.findByRole('dialog', { name: '好友申请' })
    expect(screen.queryByText('消息')).toBeNull()
    fireEvent.click(within(dialog).getByRole('button', { name: /^接\s*受$/ }))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/community/connections/12', { action: 'accept' }))
    fireEvent.click(within(dialog).getByLabelText('Close'))
    expect(await screen.findByText('消息')).toBeTruthy()
  })
})
