import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HealthOverview from './HealthOverview'
import HealthProfile from './HealthProfile'
import api from './api'
import { setLanguage } from './i18n'

vi.mock('./api', () => ({ default: { get: vi.fn(), put: vi.fn() }, apiMessage: (failure) => failure.response?.data?.message || 'Request failed' }))
vi.mock('./auth', () => ({ useAuth: () => ({ user: { id: 42, full_name: 'Test Owner' } }) }))
vi.mock('./Guidance', () => ({ default: ({ title, children }) => <details><summary>{title}</summary>{children}</details> }))
vi.mock('./HealthWorkspaceNav', () => ({ default: () => <nav aria-label="Health records workspace">Documents / Health history</nav> }))
const section = () => ({status: 'unknown', items: []})
function profile() { return {revision: 0, updated_at: null, sections: {past_history: section(), family_history: section(), medications: section(), allergies: section()}} }
function overview() { return {generated_at: '2026-09-27T12:00:00Z', profile: profile(), readings: [{key: 'blood_pressure', label: 'Blood pressure', reading: null}], records: {count: 0, recent: []}, attention: {health_alert_count: 0, alerts: [], due_task_count: 0, due_tasks: []}, care: {appointment_count: 0, appointments: [], upcoming_tasks: []}, sharing: {active_count: 0, expiring: [], pending_unusual_count: 0, unusual_count: 0}, integration: {message: 'Demonstration connections only.'}} }
function renderPage(component, path = '/overview') { return render(<MemoryRouter initialEntries={[path]}><Routes><Route path={path} element={component} />{path !== '/profile' && <Route path="/profile" element={<div>Profile destination</div>} />}<Route path="/records" element={<div>Sync destination</div>} /><Route path="/records/upload" element={<div>Upload destination</div>} /><Route path="/insights" element={<div>Insights destination</div>} /></Routes></MemoryRouter>) }

beforeEach(() => { localStorage.clear(); setLanguage('zh'); api.get.mockReset(); api.put.mockReset() })

describe('focused home', () => {
  it('gives an empty account one next step and explains how records, measurements and advice connect', async () => {
    setLanguage('en')
    api.get.mockResolvedValue({data: overview()})
    renderPage(<HealthOverview />)
    await screen.findByRole('heading', {name: 'Start with what you already know'})
    expect(document.querySelectorAll('.home-next-card .ant-btn-primary')).toHaveLength(1)
    const journey = screen.getByRole('region', {name: 'How your health information connects'})
    expect(within(journey).getAllByRole('heading').map((heading) => heading.textContent)).toEqual(['Keep your records', 'Track measurements', 'Understand next steps'])
    expect(within(journey).getByRole('link', {name: /Basic information & history/}).getAttribute('href')).toBe('/profile')
    expect(within(journey).getByRole('link', {name: /Reports & documents/}).getAttribute('href')).toBe('/records')
    expect(within(journey).getByRole('link', {name: /View trends & readings/}).getAttribute('href')).toBe('/insights')
    expect(within(journey).getByRole('link', {name: /View health advice/}).getAttribute('href')).toBe('/advice')
    expect(screen.queryByText('Latest measurements')).toBeNull()
    expect(screen.queryByText('No reminders due.')).toBeNull()
    fireEvent.click(within(document.querySelector('.home-next-card')).getByRole('button', {name: /Add basic health information/}))
    expect(await screen.findByText('Profile destination')).toBeTruthy()
  })

  it('prioritizes a flagged reading without calling the account healthy or showing all details', async () => {
    setLanguage('en')
    const data = overview()
    data.records = {count: 1, recent: [{id: 1, title: 'Recent report'}]}
    data.attention.health_alert_count = 2
    data.attention.alerts = [{id: 7, title: 'Flagged reading', rule_version: '1.2', measurement: {metric_type: 'blood_pressure', measured_at: data.generated_at}}]
    api.get.mockResolvedValue({data})
    renderPage(<HealthOverview />)
    await screen.findByRole('heading', {name: 'A measurement needs a closer look'})
    expect(screen.queryByRole('heading', {name: 'Start with what you already know'})).toBeNull()
    expect(screen.queryByText('No reminders due.')).toBeNull()
    expect(document.querySelectorAll('.home-next-card .ant-btn-primary')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', {name: /Review measurement/}))
    expect(await screen.findByText('Insights destination')).toBeTruthy()
  })
})

describe('health history category editing', () => {
  it('starts read-only and saves one edited category with the original revision and other categories', async () => {
    const saved = profile(); saved.revision = 3
    saved.sections.family_history = {status: 'recorded', items: [{id: 'family-entry', name: 'Diabetes', relationship: 'Parent', sensitive: true}]}
    api.get.mockResolvedValue({data: {profile: saved}})
    api.put.mockImplementation(async (_path, body) => ({data: {profile: {...saved, revision: 4, sections: body.sections}}}))
    renderPage(<HealthProfile />, '/profile')
    await screen.findByRole('button', {name: '添加 过敏情况'})
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.getByRole('link', {name: '管理基础信息'}).getAttribute('href')).toBe('/account')
    fireEvent.click(screen.getByRole('button', {name: '添加 过敏情况'}))
    const dialog = await screen.findByRole('dialog', {name: '过敏情况'})
    fireEvent.change(within(dialog).getByLabelText('过敏情况 过敏原名称 1'), {target: {value: 'Penicillin'}})
    fireEvent.change(within(dialog).getByLabelText('过敏情况 过敏反应与情况 1'), {target: {value: 'Rash'}})
    fireEvent.click(within(dialog).getByRole('button', {name: '保存本类信息'}))
    await waitFor(() => expect(api.put).toHaveBeenCalledOnce())
    const body = api.put.mock.calls[0][1]
    expect(body.revision).toBe(3)
    expect(body.sections.family_history).toEqual(saved.sections.family_history)
    expect(body.sections.past_history).toEqual(saved.sections.past_history)
    expect(body.sections.allergies.items[0].name).toBe('Penicillin')
    expect(await screen.findByText('Penicillin')).toBeTruthy()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('keeps a conflicting category draft and blocks a second save until the latest revision is loaded', async () => {
    const saved = profile(); saved.revision = 2
    const latest = {...saved, revision: 3}
    api.get.mockResolvedValue({data: {profile: saved}})
    api.put.mockRejectedValue({response: {status: 409, data: {message: 'Profile changed. Reload before saving.', profile: latest}}})
    renderPage(<HealthProfile />, '/profile')
    fireEvent.click(await screen.findByRole('button', {name: '添加 用药情况'}))
    const editor = await screen.findByRole('dialog', {name: '用药情况'})
    fireEvent.change(within(editor).getByLabelText('用药情况 药品或补充剂名称 1'), {target: {value: 'My existing medicine'}})
    fireEvent.click(within(editor).getByRole('button', {name: '保存本类信息'}))
    await screen.findByText('健康信息已在其他页面更新')
    const conflict = screen.getByText('健康信息已在其他页面更新').closest('[role="dialog"]')
    expect(within(conflict).getByLabelText('尚未保存的草稿').value).toContain('My existing medicine')
    fireEvent.click(within(conflict).getByRole('button', {name: '返回我的草稿'}))
    expect(within(editor).getByLabelText('用药情况 药品或补充剂名称 1').value).toBe('My existing medicine')
    expect(within(editor).getByRole('button', {name: '保存本类信息'}).disabled).toBe(true)
    expect(api.put).toHaveBeenCalledOnce()
    fireEvent.click(within(editor).getByRole('button', {name: '查看冲突'}))
    await screen.findByText('健康信息已在其他页面更新')
    fireEvent.click(within(screen.getByText('健康信息已在其他页面更新').closest('[role="dialog"]')).getByRole('button', {name: '放弃草稿，加载最新版本'}))
    await screen.findByText(/已保存版本 3/)
  }, 15000)
})
