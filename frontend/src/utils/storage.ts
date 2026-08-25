/**
 * localStorage / sessionStorage 封装
 * 统一处理 JSON 序列化、异常保护
 */

const PREFIX = "eakb_";

export const storage = {
  /** 写入 localStorage */
  set(key: string, value: string) {
    try {
      localStorage.setItem(PREFIX + key, value);
    } catch (e) {
      console.error("[Storage] 写入失败:", e);
    }
  },

  /** 读取 localStorage */
  get(key: string): string | null {
    try {
      return localStorage.getItem(PREFIX + key);
    } catch (e) {
      console.error("[Storage] 读取失败:", e);
      return null;
    }
  },

  /** 写入 JSON 对象 */
  setJSON(key: string, value: unknown) {
    try {
      localStorage.setItem(PREFIX + key, JSON.stringify(value));
    } catch (e) {
      console.error("[Storage] JSON 写入失败:", e);
    }
  },

  /** 读取 JSON 对象 */
  getJSON<T = unknown>(key: string): T | null {
    try {
      const raw = localStorage.getItem(PREFIX + key);
      return raw ? (JSON.parse(raw) as T) : null;
    } catch (e) {
      console.error("[Storage] JSON 解析失败:", e);
      return null;
    }
  },

  /** 删除 */
  remove(key: string) {
    try {
      localStorage.removeItem(PREFIX + key);
    } catch (e) {
      console.error("[Storage] 删除失败:", e);
    }
  },

  /** 清空所有 eakb 前缀的存储 */
  clearAll() {
    try {
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith(PREFIX)) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach((k) => localStorage.removeItem(k));
    } catch (e) {
      console.error("[Storage] 批量清除失败:", e);
    }
  },
};
