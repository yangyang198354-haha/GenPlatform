import { defineStore } from 'pinia'
import { authAPI } from '@/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    accessToken: localStorage.getItem('access_token') || null,
    refreshTokenVal: localStorage.getItem('refresh_token') || null,
    user: JSON.parse(localStorage.getItem('user') || 'null'),
  }),

  getters: {
    isAuthenticated: (state) => !!state.accessToken,
  },

  actions: {
    async login(email, password) {
      const { data } = await authAPI.login({ email, password })
      this.accessToken = data.access
      this.refreshTokenVal = data.refresh
      localStorage.setItem('access_token', data.access)
      localStorage.setItem('refresh_token', data.refresh)
      await this.fetchProfile()
    },

    async refreshToken() {
      const { data } = await authAPI.refreshToken(this.refreshTokenVal)
      this.accessToken = data.access
      localStorage.setItem('access_token', data.access)
    },

    async fetchProfile() {
      const { data } = await authAPI.getProfile()
      this.user = data
      localStorage.setItem('user', JSON.stringify(data))
    },

    logout() {
      this.accessToken = null
      this.refreshTokenVal = null
      this.user = null
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
    },
  },
})
