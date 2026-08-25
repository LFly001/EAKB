/**
 * 用户认证状态管理 — Pinia
 * 管理: Token 存储、用户信息、登录/登出操作
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { UserInfo } from "@/types/user";
import { loginApi, logoutApi } from "@/api/auth";
import { storage } from "@/utils/storage";
import { REFRESH_TOKEN_KEY, TOKEN_KEY, USER_INFO_KEY } from "@/utils/constants";

export const useAuthStore = defineStore(
  "auth",
  () => {
    // ==========================================
    // State
    // ==========================================
    const accessToken = ref<string>(storage.get(TOKEN_KEY) || "");
    const refreshToken = ref<string>(storage.get(REFRESH_TOKEN_KEY) || "");
    const userInfo = ref<UserInfo | null>(
      storage.get(USER_INFO_KEY) ? JSON.parse(storage.get(USER_INFO_KEY)!) : null
    );

    // ==========================================
    // Getters
    // ==========================================
    const isLoggedIn = computed(() => !!accessToken.value);
    const isAdmin = computed(() => userInfo.value?.role === "admin");
    const username = computed(() => userInfo.value?.username || "");

    // ==========================================
    // Actions
    // ==========================================
    function setTokens(access: string, refresh: string) {
      accessToken.value = access;
      refreshToken.value = refresh;
      storage.set(TOKEN_KEY, access);
      storage.set(REFRESH_TOKEN_KEY, refresh);
    }

    function setUserInfo(info: UserInfo) {
      userInfo.value = info;
      storage.set(USER_INFO_KEY, JSON.stringify(info));
    }

    function clearAuth() {
      accessToken.value = "";
      refreshToken.value = "";
      userInfo.value = null;
      storage.remove(TOKEN_KEY);
      storage.remove(REFRESH_TOKEN_KEY);
      storage.remove(USER_INFO_KEY);
    }

    /**
     * 登录操作
     */
    async function login(username: string, password: string): Promise<void> {
      const res = await loginApi({ username, password });
      if (res.code === 200) {
        const { access_token, refresh_token, user } = res.data;
        setTokens(access_token, refresh_token);
        setUserInfo(user);
      }
    }

    /**
     * 登出操作
     */
    async function logout(): Promise<void> {
      try {
        await logoutApi();
      } catch {
        // 忽略接口错误，本地仍清除
      } finally {
        clearAuth();
      }
    }

    return {
      accessToken,
      refreshToken,
      userInfo,
      isLoggedIn,
      isAdmin,
      username,
      setTokens,
      setUserInfo,
      clearAuth,
      login,
      logout,
    };
  },
  {
    // 持久化配置
    persist: {
      key: "eakb-auth",
      storage: localStorage,
      paths: ["accessToken", "refreshToken", "userInfo"],
    },
  }
);
