<script setup lang="ts">
/**
 * 404 页面
 */
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<template>
  <div class="not-found-container flex-center">
    <el-result icon="warning" title="404" sub-title="页面不存在或已被移除">
      <template #extra>
        <el-button type="primary" @click="router.push('/')">返回首页</el-button>
      </template>
    </el-result>
  </div>
</template>

<style lang="less" scoped>
.not-found-container {
  width: 100%;
  height: 100vh;
}
</style>
