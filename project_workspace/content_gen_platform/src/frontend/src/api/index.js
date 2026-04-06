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
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const auth = useAuthStore();
        await auth.refreshToken();
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
  login: (email, password) => api.post("/auth/login/", { email, password }),
  refreshToken: (refresh) => api.post("/auth/token/refresh/", { refresh }),
  getProfile: () => api.get("/auth/profile/"),
};

// ── Knowledge Base API ─────────────────────────────────────────────────────
export const kbAPI = {
  list: (params) => api.get("/knowledge-base/documents/", { params }),
  upload: (formData) =>
    api.post("/knowledge-base/documents/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  search: (query) => api.get("/knowledge-base/documents/", { params: { search: query } }),
  delete: (id) => api.delete(`/knowledge-base/documents/${id}/`),
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
  generate: (id) => api.post(`/video/projects/${id}/generate/`),
  updateScene: (projectId, sceneId, data) =>
    api.patch(`/video/projects/${projectId}/scenes/${sceneId}/`, data),
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
