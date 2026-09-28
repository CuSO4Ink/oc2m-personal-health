import { afterEach, beforeEach, vi } from 'vitest'
import { setLanguage } from './i18n'
import { act, cleanup } from '@testing-library/react'
import { message } from 'antd'

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query) => ({ matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() }),
})
globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
window.scrollTo = vi.fn()
Element.prototype.scrollIntoView = vi.fn()
const computedStyle = window.getComputedStyle
beforeEach(() => setLanguage('zh'))
window.getComputedStyle = (element) => computedStyle(element)
afterEach(async () => {
  // AntD static notices own a separate React root and outlive page unmounts.
  await act(async () => { message.destroy(); cleanup() })
  vi.restoreAllMocks()
})
