/**
 * Axios 实例封装
 * JWT Token 自动携带、请求/响应拦截器、统一错误处理
 * Phase 4: 401 自动用 refresh_token 静默续期并重放原请求, 续期失败才登出
 * Phase 8: 全局 Loading 状态接线 (并发计数 + 300ms 延迟防闪烁, 由 AppLayout 顶栏展示)
 */
import axios, {
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import { ElMessage } from "element-plus";
import { storage } from "@/utils/storage";
import { REFRESH_TOKEN_KEY, TOKEN_KEY } from "@/utils/constants";

// ==========================================
// 全局 Loading 计数 (延迟显示, 避免快请求闪烁)
// ==========================================
const LOADING_SHOW_DELAY_MS = 300;
let pendingCount = 0;
let loadingTimer: ReturnType<typeof setTimeout> | null = null;

async function setGlobalLoading(loading: boolean) {
  // 动态 import 避免循环依赖 (stores/auth → api/auth → request)
  const { useAppStore } = await import("@/stores/app");
  useAppStore().setGlobalLoading(loading);
}

function showLoading() {
  pendingCount += 1;
  if (loadingTimer === null) {
    loadingTimer = setTimeout(() => {
      loadingTimer = null;
      if (pendingCount > 0) void setGlobalLoading(true);
    }, LOADING_SHOW_DELAY_MS);
  }
}

function hideLoading() {
  pendingCount = Math.max(0, pendingCount - 1);
  if (pendingCount === 0) {
    if (loadingTimer !== null) {
      clearTimeout(loadingTimer);
      loadingTimer = null;
    }
    void setGlobalLoading(false);
  }
}

// 可重放请求配置 (附加 _retried 标记防止续期后无限重试)
type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

// ==========================================
// 创建 Axios 实例
// ==========================================
const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 60000, // 60s (SSE 流式接口可能较长)
  headers: {
    "Content-Type": "application/json",
  },
});

// ==========================================
// 请求拦截器 — JWT Token 自动携带 + 全局 Loading 计数
// ==========================================
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = storage.get(TOKEN_KEY);
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    showLoading();
    return config;
  },
  (error) => {
    hideLoading();
    return Promise.reject(error);
  }
);

// ==========================================
// 401 静默续期 (refresh_token 换新 access_token)
// ==========================================

/** 并发 401 共享同一次刷新请求 */
let refreshPromise: Promise<string | null> | null = null;

/**
 * 用 refresh_token 换取新 access_token。
 * 裸 axios 直调, 不走本实例拦截器避免递归。
 * 成功返回新 token 并写回存储; 失败返回 null。
 */
function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;

  const refreshToken = storage.get(REFRESH_TOKEN_KEY);
  if (!refreshToken) return Promise.resolve(null);

  refreshPromise = axios
    .post(`${import.meta.env.VITE_API_BASE_URL}/auth/refresh`, {
      refresh_token: refreshToken,
    })
    .then((res) => {
      const data = res.data?.data;
      if (res.data?.code === 200 && data?.access_token) {
        storage.set(TOKEN_KEY, data.access_token);
        if (data.refresh_token) {
          storage.set(REFRESH_TOKEN_KEY, data.refresh_token);
        }
        return data.access_token as string;
      }
      return null;
    })
    .catch(() => null)
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

/** 续期失败: 清除全部登录态并跳转登录页 */
function forceLogout(message: string) {
  ElMessage.error(message);
  // 清空所有 eakb_ 前缀存储 — 含 Pinia 持久化键 eakb-auth。
  // 只删裸 token key 会让页面重载后 isLoggedIn 仍为 true,
  // 登录页被路由守卫弹回看板, 形成"闪一下回看板"的死循环
  storage.clearAll();
  if (window.location.pathname !== "/login") {
    window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`;
  }
}

// ==========================================
// 响应拦截器 — 统一错误处理
// ==========================================
request.interceptors.response.use(
  (response: AxiosResponse) => {
    hideLoading();
    const res = response.data;

    // 标准 API 返回体 { code, msg, data }
    if (res && typeof res.code !== "undefined") {
      if (res.code === 200) {
        return res; // 成功，返回完整响应体
      }

      // --- 业务错误处理 ---
      const errorMsg = res.msg || "请求失败";

      // 40100 Token 无效/过期 → 先尝试静默续期重放
      if (res.code === 40100) {
        const config = response.config as RetriableConfig;
        if (!config._retried) {
          return refreshAccessToken().then((newToken) => {
            if (newToken) {
              config._retried = true;
              config.headers.Authorization = `Bearer ${newToken}`;
              return request(config);
            }
            forceLogout("登录已过期，请重新登录");
            return Promise.reject(new Error(errorMsg));
          });
        }
        forceLogout("登录已过期，请重新登录");
        return Promise.reject(new Error(errorMsg));
      }

      // 403 权限不足
      if (res.code === 40300) {
        ElMessage.error("权限不足");
        return Promise.reject(new Error(errorMsg));
      }

      // 其他业务错误
      ElMessage.error(errorMsg);
      return Promise.reject(new Error(errorMsg));
    }

    // 非标准格式 → 直接返回
    return res;
  },
  async (error) => {
    hideLoading();
    const { response, config } = error;

    // HTTP 401 → 先尝试静默续期, 成功则重放原请求; 失败才登出
    if (response?.status === 401) {
      const retriable = config as RetriableConfig | undefined;
      if (retriable && !retriable._retried) {
        const newToken = await refreshAccessToken();
        if (newToken) {
          retriable._retried = true;
          retriable.headers.Authorization = `Bearer ${newToken}`;
          return request(retriable);
        }
      }
      forceLogout("未登录或登录已过期");
      return Promise.reject(error);
    }

    // 网络错误 / 超时 等
    let message = "网络异常，请稍后重试";

    if (error.code === "ECONNABORTED" && error.message.includes("timeout")) {
      message = "请求超时，请稍后重试";
    } else if (response) {
      const status = response.status;
      switch (status) {
        case 403:
          message = "权限不足";
          break;
        case 404:
          message = "请求的资源不存在";
          break;
        case 500:
          message = "服务器异常";
          break;
        default:
          message = response.data?.msg || `请求错误 (${status})`;
      }
    }

    ElMessage.error(message);
    return Promise.reject(error);
  }
);

export default request;
