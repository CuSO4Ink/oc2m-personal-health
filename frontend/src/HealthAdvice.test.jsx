import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import HealthAdvice from './HealthAdvice'
import api from './api'
import { setLanguage } from './i18n'

vi.mock('./api', () => ({default: {get: vi.fn(), post: vi.fn()}, apiMessage: failure => failure.response?.data?.message || 'Load failed'}))

function latest(language = 'en', summary = 'Saved advice') {
  return {id: 1, language, model: 'deepseek-flash', created_at: '2026-09-28T08:00:00Z', summary,
    concerns: [{title: 'Report statement to verify', summary: 'This report statement still needs confirmation.', evidenceIds: ['s1']}],
    daily_actions: [], limitations: ['Limited information, not a diagnosis.'],
    sources: [{id: 's1', type: 'document_page', label: 'Report source', path: '/records/4?document=2&page=1', page: 1, confirmed: false}]}
}
function status(overrides = {}) {
  return {configured: true, consent: {granted: true}, input: {fingerprint: 'snapshot-1', has_data: true, profile_items: 1, measurements: 2, records: 1},
    latest: latest(), stale: false, generating: false, ...overrides}
}
function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => {resolve = yes; reject = no})
  return {promise, resolve, reject}
}
function renderPage() { return render(<MemoryRouter><HealthAdvice /></MemoryRouter>) }
beforeEach(() => { setLanguage('en'); api.get.mockReset(); api.post.mockReset() })

it('requires an explicit first consent and labels unconfirmed PDF evidence', async () => {
  api.get.mockResolvedValue({data: status({consent: {granted: false}, latest: null})})
  api.post.mockResolvedValue({data: status()})
  renderPage()
  const agree = await screen.findByLabelText('I agree to send this health information to DeepSeek for advice.')
  const generate = screen.getByRole('button', {name: 'Generate health advice'})
  expect(generate.disabled).toBe(true)
  expect(api.post).not.toHaveBeenCalled()
  expect(screen.getByText(/including health items marked sensitive/)).toBeTruthy()
  fireEvent.click(agree)
  expect(api.post).not.toHaveBeenCalled()
  fireEvent.click(generate)
  await screen.findByText('Saved advice')
  expect(api.post).toHaveBeenCalledExactlyOnceWith('/advice/generate', {language: 'en', acknowledged: true}, {timeout: 100000})
  fireEvent.click(screen.getByText('Evidence & source records'))
  expect(screen.getByText('Report text — verify before relying on it')).toBeTruthy()
  expect(screen.getByRole('link', {name: 'Report source · Page 1'}).getAttribute('href')).toBe('/records/4?document=2&page=1')
  expect(screen.getByText('AI-generated information for discussion and daily self-care; not a diagnosis or a medication plan.')).toBeTruthy()
})

it('automatically refreshes an already-consented stale snapshot once and does not replace generation with a focus read', async () => {
  const generation = deferred()
  api.get.mockResolvedValue({data: status({stale: true})})
  api.post.mockReturnValue(generation.promise)
  renderPage()
  await waitFor(() => expect(api.post).toHaveBeenCalledOnce())
  expect(api.post.mock.calls[0][1]).toEqual({language: 'en'})
  fireEvent.focus(window)
  expect(api.get).toHaveBeenCalledOnce()
  await act(async () => generation.resolve({data: status({latest: latest('en', 'Updated advice')})}))
  await screen.findByText('Updated advice')
  api.get.mockResolvedValue({data: status({latest: latest('en', 'Updated advice')})})
  fireEvent.click(screen.getByRole('button', {name: /Check for updates/}))
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2))
  expect(api.post).toHaveBeenCalledOnce()
})

it('does not automatically retry a failed first generation after the server saves consent', async () => {
  api.get.mockResolvedValue({data: status({consent: {granted: false}, latest: null})})
  const failed = status({latest: null, error: 'provider_timeout', message: 'Provider timed out'})
  api.post.mockRejectedValue({response: {status: 504, data: failed}})
  renderPage()
  fireEvent.click(await screen.findByLabelText('I agree to send this health information to DeepSeek for advice.'))
  fireEvent.click(screen.getByRole('button', {name: 'Generate health advice'}))
  await screen.findByText('Provider timed out')
  await act(async () => {})
  expect(api.post).toHaveBeenCalledOnce()
  api.get.mockResolvedValue({data: failed})
  fireEvent.click(screen.getByRole('button', {name: /Check for updates/}))
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2))
  expect(api.post).toHaveBeenCalledOnce()
})

it('keeps old advice after a provider failure without looping on the same fingerprint', async () => {
  const failed = status({stale: true, error: 'provider_unavailable', message: 'Provider unavailable'})
  api.get.mockResolvedValue({data: failed})
  api.post.mockRejectedValue({response: {status: 502, data: failed}})
  renderPage()
  await screen.findByText('Provider unavailable')
  expect(screen.getByText('Saved advice')).toBeTruthy()
  expect(screen.getByText('Information changed — update needed')).toBeTruthy()
  fireEvent.focus(window)
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2))
  expect(api.post).toHaveBeenCalledOnce()
})

it('does not generate advice when there is no usable health data', async () => {
  api.get.mockResolvedValue({data: status({input: {fingerprint: 'empty', has_data: false}, latest: null, stale: true})})
  renderPage()
  await screen.findByText('Add health information or a report to get started.')
  expect(api.post).not.toHaveBeenCalled()
  expect(screen.queryByLabelText('I agree to send this health information to DeepSeek for advice.')).toBeNull()
})

it('retries an initial load failure with GET without sending unconsented information', async () => {
  api.get.mockRejectedValueOnce({response: {data: {message: 'Initial load failed'}}}).mockResolvedValueOnce({data: status({consent: {granted: false}, latest: null})})
  renderPage()
  await screen.findByText('Initial load failed')
  fireEvent.click(screen.getByRole('button', {name: 'Retry'}))
  await screen.findByLabelText('I agree to send this health information to DeepSeek for advice.')
  expect(api.get).toHaveBeenCalledTimes(2)
  expect(api.post).not.toHaveBeenCalled()
})

it('ignores an old generation after switching language away and back', async () => {
  const oldGeneration = deferred()
  let englishLoads = 0
  api.get.mockImplementation(async (_path, {params}) => ({data: params.language === 'zh'
    ? status({latest: latest('zh', '当前中文建议')})
    : ++englishLoads === 1 ? status({stale: true}) : status({latest: latest('en', 'Current English advice')})}))
  api.post.mockReturnValue(oldGeneration.promise)
  renderPage()
  await waitFor(() => expect(api.post).toHaveBeenCalledOnce())
  await act(async () => setLanguage('zh'))
  await screen.findByText('当前中文建议')
  await act(async () => setLanguage('en'))
  await screen.findByText('Current English advice')
  await act(async () => oldGeneration.resolve({data: status({latest: latest('en', 'Obsolete English advice')})}))
  expect(screen.getByText('Current English advice')).toBeTruthy()
  expect(screen.queryByText('Obsolete English advice')).toBeNull()
  expect(api.post).toHaveBeenCalledOnce()
})

it('ignores obsolete language GET success and failure responses', async () => {
  const firstEnglish = deferred(), chinese = deferred()
  api.get.mockReturnValueOnce(firstEnglish.promise).mockReturnValueOnce(chinese.promise).mockResolvedValueOnce({data: status({latest: latest('en', 'Newest session advice')})})
  renderPage()
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1))
  await act(async () => setLanguage('zh'))
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2))
  await act(async () => setLanguage('en'))
  await screen.findByText('Newest session advice')
  await act(async () => {
    firstEnglish.resolve({data: status({latest: latest('en', 'Obsolete GET advice')})})
    chinese.reject({response: {data: {message: 'Obsolete language failure'}}})
  })
  expect(screen.getByText('Newest session advice')).toBeTruthy()
  expect(screen.queryByText('Obsolete GET advice')).toBeNull()
  expect(screen.queryByText('Obsolete language failure')).toBeNull()
  expect(api.post).not.toHaveBeenCalled()
})
