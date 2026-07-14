/** Axios 实例 + 拦截器 + Token 刷新 — 所有 API 领域模块的共享基础。 */
import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// ---- Token 刷新锁 ----
let isRefreshing = false
let refreshSubscribers = []

function onTokenRefreshed(newToken) {
  refreshSubscribers.forEach(cb => cb(newToken))
  refreshSubscribers = []
}

function addRefreshSubscriber(cb) {
  refreshSubscribers.push(cb)
}

function clearAuthAndRedirect() {
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
  localStorage.removeItem('spaces')
  localStorage.removeItem('active_space')
  localStorage.removeItem('context_token')
  window.location.href = '/login'
}

/** context_token 过期 → 回 Space 选择页重新签发 */
function expireContextAndRedirect() {
  localStorage.removeItem('context_token')
  localStorage.removeItem('active_space')
  window.location.href = '/spaces'
}

// 请求拦截器 — 自动附加正确的 Token
api.interceptors.request.use(config => {
  if (config.headers.Authorization) {
    return config
  }

  if (config.url === '/auth/login' || config.url === '/auth/register' || config.url === '/auth/refresh') {
    return config
  }

  if (config.url === '/auth/switch-space' || config.url === '/auth/spaces') {
    const rtoken = localStorage.getItem('refresh_token')
    if (rtoken) {
      config.headers.Authorization = `Bearer ${rtoken}`
    }
    return config
  }

  if (config.url.startsWith('/auth/') || config.url.startsWith('/')) {
    const ctoken = localStorage.getItem('context_token')
    if (ctoken) {
      config.headers.Authorization = `Bearer ${ctoken}`
    } else {
      const rtoken = localStorage.getItem('refresh_token')
      if (rtoken) {
        config.headers.Authorization = `Bearer ${rtoken}`
      }
    }
  }
  return config
})

// 错误码 → 中文消息映射
const ERROR_CODE_MESSAGES = {
  AUTH_TOKEN_EXPIRED: '登录已过期，请重新登录',
  AUTH_NOT_LOGGED_IN: '未登录或 Token 已过期',
  AUTH_BAD_CREDENTIALS: '用户名或密码错误',
  SPACE_ACCESS_DENIED: '无权访问该空间',
  KB_ACCESS_DENIED: '无权访问该知识库',
  DOC_NOT_FOUND: '文档不存在',
  PARAM_MISSING: '缺少必填参数',
  PARAM_INVALID: '参数无效',
  INTERNAL_ERROR: '服务器内部错误',
}

// 响应拦截器
api.interceptors.response.use(
  response => {
    const body = response.data
    if ((body.code !== 0 && body.code !== undefined) || body.error_code) {
      const msg = body.message || ERROR_CODE_MESSAGES[body.error_code] || '请求失败'
      ElMessage.error(msg)
      return Promise.reject(new Error(msg))
    }
    return response
  },
  async error => {
    const { config, response } = error
    const status = response?.status
    const errorCode = response?.data?.error_code

    if (errorCode === 'AUTH_TOKEN_EXPIRED' || errorCode === 'AUTH_NOT_LOGGED_IN') {
      if (errorCode !== 'AUTH_TOKEN_EXPIRED') {
        expireContextAndRedirect()
      } else {
        clearAuthAndRedirect()
      }
      return Promise.reject(error)
    }

    if (status === 401 && config) {
      const ctoken = localStorage.getItem('context_token')
      if (ctoken && config.headers?.Authorization === `Bearer ${ctoken}`) {
        expireContextAndRedirect()
        return Promise.reject(error)
      }

      if (isRefreshing) {
        return new Promise((resolve) => {
          addRefreshSubscriber(() => resolve(api(config)))
        })
      }

      if (config.url === '/auth/refresh') {
        clearAuthAndRedirect()
        return Promise.reject(error)
      }

      isRefreshing = true
      const rt = localStorage.getItem('refresh_token')
      if (!rt) {
        clearAuthAndRedirect()
        return Promise.reject(error)
      }

      try {
        const res = await axios.post('/api/auth/refresh', { refresh_token: rt })
        if (res.data?.code === 0) {
          const { refresh_token } = res.data.data
          localStorage.setItem('refresh_token', refresh_token)
          onTokenRefreshed(refresh_token)
          return api(config)
        }
        clearAuthAndRedirect()
        return Promise.reject(error)
      } catch {
        clearAuthAndRedirect()
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }

    if (errorCode === 'SPACE_ACCESS_DENIED' || errorCode === 'KB_ACCESS_DENIED') {
      ElMessage.warning(response?.data?.message || ERROR_CODE_MESSAGES[errorCode])
    } else if (status === 403) {
      ElMessage.warning(response?.data?.message || '权限不足')
    } else if (status === 401) {
      clearAuthAndRedirect()
    } else {
      const msg = response?.data?.message || ERROR_CODE_MESSAGES[errorCode] || '网络错误'
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

export default api
