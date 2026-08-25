/**
 * Vue Router 路由配置
 * 全局守卫: JWT 登录校验 + 角色权限拦截
 */
import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { useAuthStore } from "@/stores/auth";

// ==========================================
// 公开路由 (不需要登录)
// ==========================================
const publicRoutes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "Login",
    component: () => import("@/views/login/LoginView.vue"),
    meta: { title: "登录", requiresAuth: false },
  },
  {
    path: "/register",
    name: "Register",
    component: () => import("@/views/register/RegisterView.vue"),
    meta: { title: "注册", requiresAuth: false },
  },
];

// ==========================================
// 受保护路由 (需要登录) — 全部挂在主布局 AppLayout 下
// ==========================================
const protectedRoutes: RouteRecordRaw = {
  path: "/",
  component: () => import("@/components/layout/AppLayout.vue"),
  meta: { requiresAuth: true },
  children: [
    {
      path: "",
      redirect: "/dashboard",
    },
    {
      path: "dashboard",
      name: "Dashboard",
      component: () => import("@/views/dashboard/DashboardView.vue"),
      // Phase 7: 看板为管理后台功能, 仅 admin 可见
      meta: { title: "数据看板", requiresAuth: true, requiresAdmin: true },
    },
    {
      path: "profile",
      name: "Profile",
      component: () => import("@/views/profile/ProfileView.vue"),
      meta: { title: "个人信息", requiresAuth: true },
    },
    // ==========================================
    // 知识库路由 (Phase 3)
    // ==========================================
    {
      path: "knowledge/categories",
      name: "KnowledgeCategories",
      component: () => import("@/views/knowledge/CategoryManage.vue"),
      meta: { title: "知识库分类", requiresAuth: true },
    },
    {
      path: "knowledge/documents",
      name: "KnowledgeDocuments",
      component: () => import("@/views/knowledge/DocumentList.vue"),
      meta: { title: "文档管理", requiresAuth: true },
    },
    {
      path: "knowledge/documents/upload",
      name: "DocumentUpload",
      component: () => import("@/views/knowledge/DocumentUpload.vue"),
      meta: { title: "上传文档", requiresAuth: true },
    },
    {
      path: "knowledge/documents/:id",
      name: "DocumentDetail",
      component: () => import("@/views/knowledge/DocumentDetail.vue"),
      meta: { title: "文档详情", requiresAuth: true },
    },
    // ==========================================
    // 提示词模板路由 (Phase 4)
    // ==========================================
    {
      path: "templates",
      name: "Templates",
      component: () => import("@/views/template/TemplateList.vue"),
      meta: { title: "提示词模板", requiresAuth: true },
    },
    {
      path: "templates/create",
      name: "TemplateCreate",
      component: () => import("@/views/template/TemplateForm.vue"),
      meta: { title: "新建模板", requiresAuth: true },
    },
    {
      path: "templates/:id/edit",
      name: "TemplateEdit",
      component: () => import("@/views/template/TemplateForm.vue"),
      meta: { title: "编辑模板", requiresAuth: true },
    },
    // ==========================================
    // 智能问答路由 (Phase 5)
    // ==========================================
    {
      path: "chat",
      name: "Chat",
      component: () => import("@/views/chat/ChatView.vue"),
      meta: { title: "智能问答", requiresAuth: true },
    },
    {
      path: "chat/:conversationId",
      name: "ChatConversation",
      component: () => import("@/views/chat/ChatView.vue"),
      meta: { title: "智能问答", requiresAuth: true },
    },
    // ==========================================
    // 管理员路由 (admin only)
    // ==========================================
    {
      path: "admin/users",
      name: "AdminUsers",
      component: () => import("@/views/admin/UserManage.vue"),
      meta: { title: "用户管理", requiresAuth: true, requiresAdmin: true },
    },
    {
      path: "admin/logs",
      name: "AdminLogs",
      component: () => import("@/views/admin/LogList.vue"),
      meta: { title: "操作日志", requiresAuth: true, requiresAdmin: true },
    },
    {
      path: "admin/config",
      name: "AdminConfig",
      component: () => import("@/views/admin/SystemConfig.vue"),
      meta: { title: "系统配置", requiresAuth: true, requiresAdmin: true },
    },
    // ==========================================
    // 知识图谱路由 (Phase 6)
    // ==========================================
    {
      path: "graph",
      name: "Graph",
      component: () => import("@/views/graph/GraphView.vue"),
      meta: { title: "知识图谱", requiresAuth: true },
    },
  ],
};

// ==========================================
// 通配路由 (404)
// ==========================================
const catchRoute: RouteRecordRaw = {
  path: "/:pathMatch(.*)*",
  name: "NotFound",
  component: () => import("@/views/NotFound.vue"),
  meta: { title: "页面不存在", requiresAuth: false },
};

// ==========================================
// 创建路由实例
// ==========================================
const router = createRouter({
  history: createWebHistory(),
  routes: [...publicRoutes, protectedRoutes, catchRoute],
  scrollBehavior: () => ({ top: 0 }),
});

// ==========================================
// 全局路由守卫
// ==========================================
router.beforeEach((to, _from, next) => {
  document.title = `${to.meta.title || "EAKB"} — 企业知识库智能助手`;

  const authStore = useAuthStore();

  // --- 1. 不需要鉴权的页面直接放行 ---
  if (to.meta.requiresAuth === false) {
    // 已登录用户访问登录/注册页 → 管理员回看板, 员工回问答页
    if (authStore.isLoggedIn && (to.path === "/login" || to.path === "/register")) {
      next(authStore.isAdmin ? "/dashboard" : "/chat");
      return;
    }
    next();
    return;
  }

  // --- 2. 需要鉴权的页面 → 校验登录 ---
  if (!authStore.isLoggedIn) {
    next({ path: "/login", query: { redirect: to.fullPath } });
    return;
  }

  // --- 3. 管理员路由 → 附加角色校验 (越权访问 → 问答页) ---
  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    next("/chat");
    return;
  }

  next();
});

export default router;
