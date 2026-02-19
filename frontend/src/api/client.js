import axios from 'axios';
import i18n from '../i18n';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Helper to add language parameter
const addLangParam = (params = {}) => {
  return {
    ...params,
    lang: i18n.language || 'en'
  };
};

// API functions with automatic language parameter
export const api = {
  getSignals: (params) => apiClient.get('/signals', { params: addLangParam(params) }).then(res => res.data),
  getSignal: (id) => apiClient.get(`/signals/${id}`, { params: addLangParam() }).then(res => res.data),
  getNews: (params) => apiClient.get('/news', { params: addLangParam(params) }).then(res => res.data),
  getDashboardStats: () => apiClient.get('/dashboard/stats').then(res => res.data),
  triggerScrape: () => apiClient.post('/scrape/trigger').then(res => res.data),
  getTopMovers: (params) => apiClient.get('/top-movers', { params: addLangParam(params) }).then(res => res.data),
  getTodaysIPOs: () => apiClient.get('/ipos/today', { params: addLangParam() }).then(res => res.data),
  getFDACatalysts: (params) => apiClient.get('/catalyst/fda', { params: addLangParam(params) }).then(res => res.data),
  getTechCatalysts: (params) => apiClient.get('/catalyst/tech', { params: addLangParam(params) }).then(res => res.data),
  getTickerCatalyst: (ticker) => apiClient.get(`/catalyst/fda/${ticker}`, { params: addLangParam() }).then(res => res.data),
};
