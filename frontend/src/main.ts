/**
 * EAKB 前端入口
 * Vue3 + ElementPlus + Pinia + VueRouter 初始化
 */
import { createApp } from "vue";
import { createPinia } from "pinia";
import piniaPluginPersistedstate from "pinia-plugin-persistedstate";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import * as ElementPlusIconsVue from "@element-plus/icons-vue";

import App from "./App.vue";
import router from "./router";
import "@/styles/index.less";

// ==========================================
// 创建应用实例
// ==========================================
const app = createApp(App);

// Pinia 状态管理 — 持久化插件
const pinia = createPinia();
pinia.use(piniaPluginPersistedstate);
app.use(pinia);

// Vue Router
app.use(router);

// Element Plus — 中文国际化
app.use(ElementPlus, { locale: zhCn });

// 全局注册 Element Plus Icons
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

// ==========================================
// 挂载
// ==========================================
app.mount("#app");
