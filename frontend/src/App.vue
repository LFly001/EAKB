<script setup lang="ts">
/**
 * 根组件
 * Phase 1: 基础布局占位
 * Phase 2+: 替换为 router-view + 全局布局
 */
</script>

<template>
  <router-view />
</template>

<style lang="less">
#app {
  width: 100%;
  height: 100vh;
  font-family: "Helvetica Neue", Helvetica, "PingFang SC", "Microsoft YaHei",
    Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
</style>
