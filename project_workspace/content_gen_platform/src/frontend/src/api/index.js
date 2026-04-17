/**
 * Axios instance with JWT interceptors and base URL configuration.
 */
import axios from "axios";
import { useAuthStore } from "@/stores/auth";
import router from "@/router";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 30000,
});

// Request interceptor: attach JWT
api.interceptors.request.use((config) => {
  const auth = useAuthStore();
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`;
  }
  return config;
});

// Response interceptor: handle 401 with token refresh
//
// Problem: when multiple requests fire concurrently and the access token has
// just expired, all of them receive 401 simultaneously.  Without a lock each
// request would independently call refreshToken(), but because the backend
// uses ROTATE_REFRESH_TOKENS=True the first successful refresh invalidates the
// refresh token — every subsequent refresh attempt fails with 401 and the user
// is logged out unexpectedly.
//
// Solution: a single shared Promise (_refreshPromise) acts as a mutex.
// While a refresh is in flight every waiting request queues itself; once the
// new token arrives they all replay their original requests.
let _refreshPromise = null;

/**
 * Shared token-refresh mutex.
 * Call this instead of auth.refreshToken() directly so that concurrent callers
 * (response interceptor AND App.vue onMounted proactive refresh) never race.
 */
export function ensureTokenRefreshed(auth) {
  if (!_refreshPromise) {
    _refreshPromise = auth.refreshToken().finally(() => {
      _refreshPromise = null;
    });
  }
  return _refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const auth = useAuthStore();
        await ensureTokenRefreshed(auth);
        originalRequest.headers.Authorization = `Bearer ${auth.accessToken}`;
        return api(originalRequest);
      } catch {
        const auth = useAuthStore();
        auth.logout();
        router.push("/login");
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// ── Auth API ───────────────────────────────────────────────────────────────
export const authAPI = {
  register: (data) => api.post("/auth/register/", data),
  login: ({ email, password }) => api.post("/auth/login/", { email, password }),
  refreshToken: (refresh) => api.post("/auth/token/refresh/", { refresh }),
  getProfile: () => api.get("/auth/profile/"),
};

// ── Knowledge Base API ─────────────────────────────────────────────────────
export const kbAPI = {
  list: (params) => api.get("/knowledge/documents/", { params }),
  get: (id) => api.get(`/knowledge/documents/${id}/`),
  upload: (formData) =>
    api.post("/knowledge/documents/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  batchUpload: (formData) =>
    api.post("/knowledge/documents/batch-upload/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  search: (query) => api.get("/knowledge/documents/", { params: { search: query } }),
  rename: (id, name) => api.patch(`/knowledge/documents/${id}/`, { name }),
  delete: (id) => api.delete(`/knowledge/documents/${id}/`),
};

// ── Content API ────────────────────────────────────────────────────────────
export const contentAPI = {
  list: (params) => api.get("/contents/", { params }),
  create: (data) => api.post("/contents/", data),
  get: (id) => api.get(`/contents/${id}/`),
  update: (id, data) => api.patch(`/contents/${id}/`, data),
  confirm: (id) => api.post(`/contents/${id}/confirm/`),
  delete: (id) => api.delete(`/contents/${id}/`),
};

// ── Publisher API ──────────────────────────────────────────────────────────
export const publisherAPI = {
  // Platform accounts
  listAccounts: () => api.get("/publisher/accounts/"),
  createAccount: (data) => api.post("/publisher/accounts/", data),
  deleteAccount: (id) => api.delete(`/publisher/accounts/${id}/`),
  // Publish tasks
  listTasks: (params) => api.get("/publisher/tasks/", { params }),
  create: (data) => api.post("/publisher/tasks/", data),
  retryTask: (id) => api.post(`/publisher/tasks/${id}/retry/`),
};

// ── Video Generator API ────────────────────────────────────────────────────
export const videoAPI = {
  listProjects: (params) => api.get("/video/projects/", { params }),
  createProject: (data) => api.post("/video/projects/", data),
  getProject: (id) => api.get(`/video/projects/${id}/`),
  getStatus: (id) => api.get(`/video/projects/${id}/status/`),
  generate: (id) => api.post(`/video/projects/${id}/generate/`),
  updateScene: (projectId, sceneId, data) =>
    api.patch(`/video/projects/${projectId}/scenes/${sceneId}/`, data),
  deleteScene: (projectId, sceneId) =>
    api.delete(`/video/projects/${projectId}/scenes/${sceneId}/`),
  reorderScenes: (projectId, sceneIds) =>
    api.post(`/video/projects/${projectId}/reorder/`, { scene_ids: sceneIds }),
  exportVideo: (id) => api.post(`/video/projects/${id}/export/`),
};

// ── Settings API ───────────────────────────────────────────────────────────
export const settingsAPI = {
  get: (serviceType) => api.get(`/settings/services/${serviceType}/`),
  save: (serviceType, data) => api.put(`/settings/services/${serviceType}/`, data),
  test: (serviceType) => api.post(`/settings/services/${serviceType}/test/`),
  list: () => api.get("/settings/services/"),
};

// ── Image Generator API ────────────────────────────────────────────────────
export const imageAPI = {
  generate: (formData) =>
    api.post("/image/generate/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  getStatus: (id) => api.get(`/image/generate/${id}/status/`),
  getHistory: () => api.get("/image/history/"),
};

// ── Media Library API ──────────────────────────────────────────────────────
export const mediaAPI = {
  list: (params) => api.get("/media/", { params }),
  upload: (formData) =>
    api.post("/media/upload/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  delete: (id) => api.delete(`/media/${id}/`),
  download: (id) => api.get(`/media/${id}/download/`),
};
