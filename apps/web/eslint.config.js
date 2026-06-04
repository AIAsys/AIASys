import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs["recommended-latest"],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      "react-refresh/only-export-components": "off",
      "@typescript-eslint/no-unused-expressions": "off",
      // 禁止显式使用 any 类型，提高类型安全
      "@typescript-eslint/no-explicit-any": "warn",
      // 优先使用 const，避免不必要的 let
      "prefer-const": "error",
      // 禁止未使用的变量（TypeScript 已检查，这里关闭避免重复）
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
]);
