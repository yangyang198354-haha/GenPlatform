/**
 * Axios instance with JWT interceptors and base URL configuration.
 */
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
})

// Request interceptor: attach JWT
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  return config
})

// Response interceptor: handle 401 with token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      try {
        const auth = useAuthStore()
        await auth.refreshToken()
        originalRequest.headers.Authorization = `Bearer ${auth.accessToken}`
        return api(originalRequest)
      } catch {
        const auth = useAuthStore()
        auth.logout()
        router.push('/login')
      }
    }
    return Promise.reject(error)
  }
)

export default api

// ── Auth API ──────────────────────────────────────────────────────────────
export const authAPI = {
  register: (data) => api.post('/auth/register/', data),
  login: (data) => api.post('/auth/login/', data),
  refreshToken: (refresh) => api.post('/auth/token/refresh/', { refresh }),
  getProfile: () => api.get('/auth/profile/'),
}

// ── Knowledge Base API ────────────────────────────────────────────────────
export const kbAPI = {
  list: (params) => api.get('/knowledge/documents/', { params }),
  upload: (formData) => api.post('/knowledge/documents/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  rename: (id, name) => api.patch(`/knowledge/documents/${id}/`, { name }),
  delete: (id) => api.delete(`/knowledge/documents/${id}/`),
}

// ── Content API ────────────────────────────────────────────────────────────
export const contentAPI = {
  list: (params) => api.get('/contents/', { params }),
  create: (data) => api.post('/contents/', data),
  get: (id) => api.get(`/contents/${id}/`),
  update: (id, data) => api.patch(`/contents/${id}/`, data),
  confirm: (id) => api.post(`/contents/${id}/confirm/`),
  delete: (id) => api.delete(`/contents/${id}/`),
}

// ── Publisher API ──────────────────────────────────────────────────────────
export const publisherAPI = {
  listAccounts: () => api.get('/publisher/accounts/'),
  bindAccount: (platform, data) => api.post(`/publisher/accounts/${platform}/bind/`, data),
  deleteAccount: (id) => api.delete(`/publisher/accounts/${id}/`),
  createTask: (data) => api.post('/publisher/tasks/', data),
  listTasks: (params) => api.get('/publisher/tasks/', { params }),
  retryTask: (id) => api.post(`/publisher/tasks/${id}/retry/`),
}

// ── Video Generator API ────────────────────────────────────────────────────
export const videoAPI = {
  createProject: (data) => api.post('/video/projects/', data),
  getProject: (id) => api.get(`/video/projects/${id}/`),
  generate: (id) => api.post(`/video/projects/${id}/generate/`),
  getStatus: (id) => api.get(`/video/projects/${id}/status/`),
  updateScene: (projectId, sceneId, data) =>
    api.patch(`/video/projects/${projectId}/scenes/${sceneId}/`, data),
  deleteScene: (projectId, sceneId) =>
    api.delete(`/video/projects/${projectId}/scenes/${sceneId}/`),
  reorderScenes: (projectId, sceneIds) =>
    api.post(`/video/projects/${projectId}/reorder/`, { scene_ids: sceneIds }),
  exportVideo: (id) => api.post(`/video/projects/${id}/export/`),
}

// ── Settings API ───────────────────────────────────────────────────────────
export const settingsAPI = {
  listServices: () => api.get('/settings/services/'),
  saveService: (serviceType, data) => api.put(`/settings/services/${serviceType}/`, data),
  testService: (serviceType) => api.post(`/settings/services/${serviceType}/test/`),
  deleteService: (serviceType) => api.delete(`/settings/services/${serviceType}/`),
}
