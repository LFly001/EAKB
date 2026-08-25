/**
 * 全局应用状态管理 — Pinia
 * 管理: 侧边栏折叠、主题设置、全局 Loading
 */
import { defineStore } from "pinia";
import { ref } from "vue";

export const useAppStore = defineStore("app", () => {
  // ==========================================
  // State
  // ==========================================
  /** 侧边栏折叠状态 */
  const sidebarCollapsed = ref<boolean>(false);

  /** 全局加载状态 */
  const globalLoading = ref<boolean>(false);

  /** 暗黑模式 (Phase 2+ 实现) */
  const darkMode = ref<boolean>(false);

  // ==========================================
  // Actions
  // ==========================================
  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value;
  }

  function setSidebarCollapsed(collapsed: boolean) {
    sidebarCollapsed.value = collapsed;
  }

  function setGlobalLoading(loading: boolean) {
    globalLoading.value = loading;
  }

  function toggleDarkMode() {
    darkMode.value = !darkMode.value;
    // TODO: 切换 ElementPlus 主题
  }

  return {
    sidebarCollapsed,
    globalLoading,
    darkMode,
    toggleSidebar,
    setSidebarCollapsed,
    setGlobalLoading,
    toggleDarkMode,
  };
});
