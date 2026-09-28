import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import HealthInsights from './HealthInsights'
import api from './api'
import { setLanguage } from './i18n'

vi.mock('./api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() }, apiMessage: () => '加载失败' }))
vi.mock('./Guidance', () => ({ default: ({ title, children }) => <details><summary>{title}</summary>{children}</details> }))
// Inspect which readings reach the chart; SVG sizing and rendering belong to Recharts.
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => children,
  LineChart: ({ data }) => <div role="img" aria-label="Measurement trend">{data.map((reading) => <span key={reading.id} data-reading-id={reading.id}>{reading.value}</span>)}</div>,
  CartesianGrid: () => null, Legend: () => null, Line: () => null, ReferenceLine: () => null,
  Tooltip: () => null, XAxis: () => null, YAxis: () => null,
}))
const recent = { id: 11, metric_type: 'blood_pressure', value: 120, secondary_value: 80, unit: 'mmHg', measured_at: '2026-09-27T08:00:00Z', status: 'not_assessed', flags: ['not_assessed'], assessment: { reason: 'age_unknown' }, source_name: 'Home monitor', is_editable: true }
const source = { ...recent, id: 5, value: 128, secondary_value: 82, measured_at: '2023-01-02T08:00:00Z', source_name: 'Archived report', report_source: { record_id: 4, attachment_id: 3, filename: 'archived-report.pdf', review_path: '/records/4?extraction=9' } }
function payload() {
  return { readings: [recent], superseded_readings: [], latest: recent, summary: { count: 1, average: 120, secondary_average: 80, minimum: 120, maximum: 120, attention_count: 0, unassessed_count: 1, context_counts: {}, distinct_days: 1 }, data_sufficiency: { status: 'limited' }, reference: { version: '1.2', sources: [] }, profile_points: [], health_focus: [], health_focus_eligibility: { status: 'available' } }
}
beforeEach(() => { vi.clearAllMocks(); setLanguage('zh') })

it('shows the trend and source table together and keeps advice one link away', async () => {
  api.get.mockImplementation(async (path) => ({ data: path.endsWith('/alerts') ? { alerts: [] } : payload() }))
  render(<MemoryRouter initialEntries={['/insights']}><HealthInsights /></MemoryRouter>)
  const chart = await screen.findByRole('img', { name: 'Measurement trend' })
  expect(chart.querySelector('[data-reading-id="11"]')).toBeTruthy()
  expect(within(screen.getByRole('table')).getByText('120/80 mmHg')).toBeTruthy()
  expect(within(screen.getByRole('table')).getByText('Home monitor')).toBeTruthy()
  expect(screen.getByText('测量记录与来源')).toBeTruthy()
  expect(screen.queryAllByRole('tab')).toHaveLength(0)
  expect(screen.getByRole('link', { name: '查看健康建议与日常关注' }).getAttribute('href')).toBe('/advice')
  fireEvent.click(screen.getByText('7 天'))
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/insights/metrics', expect.objectContaining({ params: expect.objectContaining({ days: 7, metric: 'blood_pressure' }) })))
  expect(await screen.findByRole('img', { name: 'Measurement trend' })).toBeTruthy()
  expect(within(screen.getByRole('table')).getByText('120/80 mmHg')).toBeTruthy()
})

it('fetches an old linked reading independently, retains its review and PDF links, and excludes it from the trend', async () => {
  api.get.mockImplementation(async (path) => ({ data: path.endsWith('/alerts') ? { alerts: [] } : { ...payload(), focused_reading: source, focused_reading_outside_period: true } }))
  render(<MemoryRouter initialEntries={['/insights?metric=blood_pressure&reading=5']}><HealthInsights /></MemoryRouter>)
  await screen.findByText('这条来源记录不在所选趋势时间范围内。')
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/insights/metrics', expect.objectContaining({ params: expect.objectContaining({ reading_id: '5', days: 30 }) })))
  const table = screen.getByRole('table')
  const rows = within(table).getAllByRole('row').slice(1)
  expect(within(rows[0]).getByText('128/82 mmHg')).toBeTruthy()
  expect(rows[0].classList.contains('linked-item')).toBe(true)
  expect(within(rows[1]).getByText('120/80 mmHg')).toBeTruthy()
  expect(within(table).getByRole('link', { name: '查看核对记录' }).getAttribute('href')).toBe('/records/4?extraction=9')
  expect(within(table).getByRole('link', { name: '打开 PDF 原件' }).getAttribute('href')).toBe('/records/4?document=3')
  const chart = screen.getByRole('img', { name: 'Measurement trend' })
  expect(chart.querySelector('[data-reading-id="11"]')).toBeTruthy()
  expect(chart.querySelector('[data-reading-id="5"]')).toBeNull()
  expect(screen.queryAllByRole('tab')).toHaveLength(0)
})
