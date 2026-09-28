import axios from 'axios'
import { t } from './i18n'

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use((response) => {
  if (['post', 'put', 'patch', 'delete'].includes(response.config?.method) && !response.config.url?.startsWith('/notifications')) {
    window.dispatchEvent(new Event('notifications:changed'))
  }
  return response
}, (error) => {
  if (error.response?.status === 401 && !error.config?.url?.includes('/auth/login')) window.dispatchEvent(new Event('auth:ended'))
  return Promise.reject(error)
})

export function apiMessage(error) {
  return t(error.response?.data?.message || 'Something went wrong. Please try again.')
}

export default api

