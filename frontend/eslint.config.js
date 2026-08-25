/**
 * ESLint 9 扁平配置 (Phase 8 补齐 — 此前 package.json 有 lint 脚本但无配置文件)
 * 规则从宽: vue essential + TS 推荐规则中最常用子集, 保持现有代码可 lint 通过
 */
import pluginVue from "eslint-plugin-vue";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import vueParser from "vue-eslint-parser";

export default [
  // 忽略目录 (产物 / 依赖 / 自动生成声明)
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "*.d.ts",
      "src/auto-imports.d.ts",
      "src/components.d.ts",
    ],
  },

  // Vue 文件: vue-eslint-parser + TS 解析器处理 script
  ...pluginVue.configs["flat/essential"],
  {
    files: ["**/*.vue"],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        extraFileExtensions: [".vue"],
        sourceType: "module",
      },
    },
    plugins: { "@typescript-eslint": tsPlugin },
    rules: {
      // 自动 import 的组件 (unplugin) 在模板中直接使用, 关闭未使用组件告警
      "vue/no-unused-components": "off",
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },

  // 纯 TS 文件
  {
    files: ["**/*.ts"],
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaVersion: "latest", sourceType: "module" },
    },
    plugins: { "@typescript-eslint": tsPlugin },
    rules: {
      ...tsPlugin.configs["eslint-recommended"].rules,
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
];
