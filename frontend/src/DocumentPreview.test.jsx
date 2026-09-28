import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import DocumentPreview from './DocumentPreview'
import api from './api'
import { setLanguage } from './i18n'

const pdf = vi.hoisted(() => {
  const page = { getViewport: vi.fn(({ scale }) => ({ width: 600 * scale, height: 800 * scale })), render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })) }
  return { getPage: vi.fn(async () => page), destroy: vi.fn(), page, getDocument: vi.fn() }
})
vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: {}, getDocument: pdf.getDocument }))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '/assets/pdf.worker.mjs' }))
vi.mock('./api', () => ({ default: { get: vi.fn() }, apiMessage: () => 'Access has expired.' }))
beforeEach(() => {
  vi.clearAllMocks(); setLanguage('en')
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({})
  pdf.getDocument.mockReturnValue({ promise: Promise.resolve({ numPages: 6, getPage: pdf.getPage }), destroy: pdf.destroy })
  api.get.mockResolvedValue({ data: new Uint8Array([37, 80, 68, 70]).buffer })
})

it('renders the protected PDF at the source page without a browser plugin and paginates', async () => {
  const view = render(<DocumentPreview url="/api/sharing/grants/4/attachments/9?mode=simulation" filename="report.pdf" initialPage={6} />)
  await screen.findByText('Page 6 of 6')
  await waitFor(() => expect(pdf.page.render).toHaveBeenCalled())
  expect(api.get).toHaveBeenCalledWith('/sharing/grants/4/attachments/9?mode=simulation', expect.objectContaining({ responseType: 'arraybuffer' }))
  expect(view.container.querySelector('canvas')).toBeTruthy()
  expect(view.container.querySelector('iframe')).toBeNull()
  expect(screen.queryByRole('link', { name: 'Download original' })).toBeNull()
  expect(screen.getByRole('link', { name: 'Open in a new tab' }).getAttribute('href')).toBe('/api/sharing/grants/4/attachments/9?mode=simulation#page=6')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Previous page' }).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
  await screen.findByText('Page 5 of 6')
  expect(pdf.getPage).toHaveBeenCalledWith(5)
  view.unmount()
  expect(pdf.destroy).toHaveBeenCalled()
})

it('shows permission failure without parsing bytes and only exposes an explicitly granted download', async () => {
  api.get.mockRejectedValueOnce({ response: { status: 403 } })
  render(<DocumentPreview url="/api/sharing/grants/4/attachments/9" filename="report.pdf" downloadUrl="/api/sharing/grants/4/attachments/9?download=1" />)
  await screen.findByText('Access has expired.')
  expect(pdf.getDocument).not.toHaveBeenCalled()
  expect(screen.getByRole('link', { name: 'Download original' }).getAttribute('href')).toBe('/api/sharing/grants/4/attachments/9?download=1')
})
