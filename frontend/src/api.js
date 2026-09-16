import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use((response) => response, (error) => {
  if (error.response?.status === 401 && !error.config?.url?.includes('/auth/login')) window.dispatchEvent(new Event('auth:ended'))
  return Promise.reject(error)
})

export function apiMessage(error) {
  return error.response?.data?.message || 'Something went wrong. Please try again.'
}

export default api

