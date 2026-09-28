import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { setLanguage, useLanguage } from './i18n'

beforeEach(() => { localStorage.clear(); setLanguage('en') })

it('starts in English when no preference is stored and interpolates translated text', async () => {
  localStorage.clear()
  vi.resetModules()
  const fresh = await import('./i18n')
  expect(fresh.t('首页')).toBe('Home')
  expect(fresh.t('你好，{name}', { name: 'Alex' })).toBe('Hello, Alex')
  fresh.setLanguage('zh')
  expect(fresh.t('Hello, {name}', { name: 'Alex' })).toBe('你好，Alex')
  expect(fresh.t('Your original health note')).toBe('Your original health note')
})

it('persists both language choices and reads the preference on the next load', async () => {
  localStorage.setItem('health-language', 'zh')
  vi.resetModules()
  const firstLoad = await import('./i18n')
  expect(firstLoad.t('Home')).toBe('首页')
  firstLoad.setLanguage('en')
  expect(localStorage.getItem('health-language')).toBe('en')
  expect(document.documentElement.lang).toBe('en')
  vi.resetModules()
  const nextLoad = await import('./i18n')
  expect(nextLoad.t('首页')).toBe('Home')
  nextLoad.setLanguage('zh')
  expect(localStorage.getItem('health-language')).toBe('zh')
  expect(document.documentElement.lang).toBe('zh-CN')
})

it('updates labels in both directions without losing an unsaved form draft', () => {
  function DraftForm() {
    const { t, setLanguage: switchLanguage } = useLanguage()
    const [draft, setDraft] = React.useState('')
    return <form><label>{t('Source')}<input value={draft} onChange={(event) => setDraft(event.target.value)} /></label><button type="button" aria-label="Switch to Chinese" onClick={() => switchLanguage('zh')}>中文</button><button type="button" aria-label="Switch to English" onClick={() => switchLanguage('en')}>English</button><button type="button">{t('Save')}</button></form>
  }
  render(<DraftForm />)
  const field = screen.getByLabelText('Source')
  fireEvent.change(field, { target: { value: 'My report note / 我的原始草稿' } })
  fireEvent.click(screen.getByRole('button', { name: 'Switch to Chinese' }))
  expect(screen.getByLabelText('来源')).toBe(field)
  expect(field.value).toBe('My report note / 我的原始草稿')
  expect(screen.getByRole('button', { name: '保存' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Switch to English' }))
  expect(screen.getByLabelText('Source')).toBe(field)
  expect(field.value).toBe('My report note / 我的原始草稿')
  expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy()
})
