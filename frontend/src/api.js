import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export function apiMessage(error) {
  return error.response?.data?.message || 'Something went wrong. Please try again.'
}

export default api

