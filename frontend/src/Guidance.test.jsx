import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import Guidance from './Guidance'

let currentUser = {id: 1}
vi.mock('./auth', () => ({useAuth: () => ({user: currentUser})}))
beforeEach(() => {localStorage.clear(); currentUser = {id: 1}})

it('keeps help compact, remembers dismissal per account, and lets it be reopened', () => {
  const view=render(<Guidance id="workflow" title="How reports work">Review before importing.</Guidance>)
  expect(screen.queryByText('Review before importing.')).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:/How reports work 了解更多/}))
  expect(screen.getByText('Review before importing.')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'关闭提示：How reports work'}))
  expect(localStorage.getItem('health-help:1:workflow')).toBe('dismissed')
  view.unmount()
  const next=render(<Guidance id="workflow" title="How reports work">Review before importing.</Guidance>)
  expect(screen.queryByRole('button',{name:'关闭提示：How reports work'})).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:'How reports work'}))
  expect(screen.getByText('Review before importing.')).toBeTruthy()
  currentUser={id:2}
  next.rerender(<Guidance id="workflow" title="How reports work">Review before importing.</Guidance>)
  expect(screen.getByRole('button',{name:'关闭提示：How reports work'})).toBeTruthy()
  expect(screen.queryByText('Review before importing.')).toBeNull()
})

