<script setup lang="ts">
/**
 * 主布局 — 左侧菜单栏 + 顶部导航 + 内容区
 * Phase 3: 侧边栏扩展 (知识库模块菜单 + 管理员菜单权限过滤)
 */
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { useAppStore } from "@/stores/app";

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();
const appStore = useAppStore();

// 侧边栏折叠状态
const collapsed = ref(false);

/** 当前激活菜单 (详情/编辑等子页面高亮父级菜单) */
const activeMenu = computed(() => {
  const path = route.path;
  if (/^\/knowledge\/documents\/\d+$/.test(path)) {
    return "/knowledge/documents";
  }
  if (/^\/templates(\/|$)/.test(path)) {
    return "/templates";
  }
  if (/^\/chat/.test(path)) {
    return "/chat";
  }
  return path;
});

async function handleCommand(command: string) {
  if (command === "profile") {
    router.push("/profile");
    return;
  }

  if (command === "logout") {
    try {
      await ElMessageBox.confirm("确定要退出登录吗？", "退出确认", {
        type: "warning",
        confirmButtonText: "退出",
        cancelButtonText: "取消",
      });
    } catch {
      return; // 用户取消
    }

    await authStore.logout();
    ElMessage.success("已退出登录");
    router.push("/login");
  }
}
</script>

<template>
  <div class="app-layout">
    <!-- 左侧菜单栏 -->
    <aside class="layout-sidebar" :class="{ collapsed }">
      <div class="sidebar-logo">
        <span class="logo-text">EAKB</span>
        <span v-if="!collapsed" class="logo-sub">企业知识库智能助手</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        router
        class="sidebar-menu"
      >
        <el-sub-menu index="knowledge">
          <template #title>
            <el-icon><Collection /></el-icon>
            <span>知识库</span>
          </template>
          <el-menu-item index="/knowledge/categories">
            <el-icon><Folder /></el-icon>
            <template #title>分类管理</template>
          </el-menu-item>
          <el-menu-item index="/knowledge/documents">
            <el-icon><Document /></el-icon>
            <template #title>文档管理</template>
          </el-menu-item>
          <el-menu-item index="/knowledge/documents/upload">
            <el-icon><Upload /></el-icon>
            <template #title>上传文档</template>
          </el-menu-item>
        </el-sub-menu>

        <el-menu-item index="/templates">
          <el-icon><Tickets /></el-icon>
          <template #title>提示词模板</template>
        </el-menu-item>

        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <template #title>智能问答</template>
        </el-menu-item>

        <el-menu-item index="/graph">
          <el-icon><Connection /></el-icon>
          <template #title>知识图谱</template>
        </el-menu-item>

        <el-sub-menu v-if="authStore.isAdmin" index="admin">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>管理后台</span>
          </template>
          <el-menu-item index="/dashboard">
            <el-icon><Odometer /></el-icon>
            <template #title>数据看板</template>
          </el-menu-item>
          <el-menu-item index="/admin/users">
            <el-icon><User /></el-icon>
            <template #title>用户管理</template>
          </el-menu-item>
          <el-menu-item index="/admin/logs">
            <el-icon><List /></el-icon>
            <template #title>操作日志</template>
          </el-menu-item>
          <el-menu-item index="/admin/config">
            <el-icon><Tools /></el-icon>
            <template #title>系统配置</template>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
    </aside>

    <!-- 右侧主区域 -->
    <div class="layout-main">
      <!-- 全局请求进度条 (Phase 8: axios 拦截器计数驱动, 300ms 延迟防闪烁) -->
      <div v-show="appStore.globalLoading" class="global-loading-bar" />

      <!-- 顶部导航栏 -->
      <header class="layout-header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="collapsed = !collapsed">
            <Expand v-if="collapsed" />
            <Fold v-else />
          </el-icon>
        </div>

        <div class="header-right">
          <el-dropdown trigger="click" @command="handleCommand">
            <span class="user-trigger">
              <el-avatar :size="28" class="user-avatar">
                {{ (authStore.userInfo?.real_name || authStore.username || "?").charAt(0) }}
              </el-avatar>
              <span class="user-name">
                {{ authStore.userInfo?.real_name || authStore.username }}
              </span>
              <el-icon class="arrow-icon"><ArrowDown /></el-icon>
            </span>

            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>个人信息
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- 内容区 -->
      <main class="layout-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style lang="less" scoped>
.app-layout {
  width: 100%;
  height: 100vh;
  display: flex;
}

// ---- 侧边栏 ----
.layout-sidebar {
  width: @sidebar-width;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: @bg-white;
  border-right: 1px solid @border-light;
  transition: width 0.25s;

  &.collapsed {
    width: @sidebar-collapsed-width;
  }

  .sidebar-logo {
    height: @header-height;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    border-bottom: 1px solid @border-light;
    overflow: hidden;

    .logo-text {
      font-size: 18px;
      font-weight: 700;
      color: @primary-color;
      letter-spacing: 2px;
    }

    .logo-sub {
      font-size: 12px;
      color: @text-secondary;
      white-space: nowrap;
    }
  }

  .sidebar-menu {
    flex: 1;
    overflow-y: auto;
    border-right: none;
  }
}

// ---- 右侧主区域 ----
.layout-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

// ---- 全局加载进度条 (顶部细线) ----
.global-loading-bar {
  position: relative;
  height: 2px;
  flex-shrink: 0;
  background: transparent;
  overflow: hidden;

  &::after {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    width: 40%;
    background: @primary-color;
    animation: global-loading-slide 1.2s ease-in-out infinite;
  }
}

@keyframes global-loading-slide {
  0% {
    left: -40%;
  }
  100% {
    left: 100%;
  }
}

.layout-header {
  height: @header-height;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: @bg-white;
  border-bottom: 1px solid @border-light;
  box-shadow: @shadow-light;
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;

  .collapse-btn {
    font-size: 18px;
    color: @text-regular;
    cursor: pointer;

    &:hover {
      color: @primary-color;
    }
  }
}

.header-right {
  .user-trigger {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: @radius-small;
    transition: background-color 0.2s;

    &:hover {
      background-color: @bg-hover;
    }
  }

  .user-avatar {
    background-color: @primary-color;
    color: #fff;
    font-size: 13px;
  }

  .user-name {
    font-size: 14px;
    color: @text-primary;
  }

  .arrow-icon {
    font-size: 12px;
    color: @text-secondary;
  }
}

.layout-content {
  flex: 1;
  overflow-y: auto;
  background-color: @bg-page;
}
</style>
