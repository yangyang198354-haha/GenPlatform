import { defineStore } from 'pinia'
import { llmAPI } from '@/api'

/**
 * Pinia store for LLM provider selection.
 *
 * State shape mirrors GET /api/v1/llm/providers/ response:
 *   providers[]       – all provider entries returned by backend
 *   userPreference    – { service_type, model } | null
 *   systemDefault     – { service_type, model } | null
 *   warnings[]        – advisory strings shown as orange banners
 *   isLoading         – true while fetch is in flight
 *   error             – last fetch error | null
 *   lastFetchedAt     – timestamp (ms) of last successful fetch; null = never
 */
export const useLlmStore = defineStore('llm', {
  state: () => ({
    providers: [],
    userPreference: null,
    systemDefault: null,
    warnings: [],
    isLoading: false,
    error: null,
    lastFetchedAt: null,
  }),

  getters: {
    /**
     * True when there is no provider that is both configured AND passed its
     * last connection test.  Used to disable the generate button and show the
     * empty-state UI inside LlmSelector.
     */
    noAvailableProviders: (state) =>
      state.providers.filter((p) => p.configured && p.last_test_ok).length === 0,
  },

  actions: {
    /**
     * Fetch the providers list from the backend.
     *
     * @param {boolean} force – when true, skip the 60-second de-bounce and
     *   always hit the network.  Default false.
     */
    async fetchProviders(force = false) {
      const CACHE_TTL_MS = 60_000
      const now = Date.now()
      if (
        !force &&
        this.lastFetchedAt !== null &&
        now - this.lastFetchedAt < CACHE_TTL_MS
      ) {
        return // still fresh, skip
      }

      this.isLoading = true
      this.error = null
      try {
        const data = await llmAPI.getProviders()
        this.providers = data.providers ?? []
        this.userPreference = data.user_preference ?? null
        this.systemDefault = data.default ?? null
        this.warnings = data.warnings ?? []
        this.lastFetchedAt = Date.now()
      } catch (e) {
        this.error = e
      } finally {
        this.isLoading = false
      }
    },

    /**
     * Optimistically update userPreference after a successful generation.
     * No network request is made – the backend already persisted the preference.
     *
     * @param {string} serviceType
     * @param {string} model
     */
    updatePreferenceLocally(serviceType, model) {
      this.userPreference = { service_type: serviceType, model }
    },
  },
})
