/**
 * 全局交互反馈封装 (Phase 8)
 * 统一二次确认弹窗 — 多个页面重复的 ElMessageBox.confirm 样板收敛到一处;
 * 业务错误提示已由 axios 拦截器统一处理, 组件内不要重复 toast 后端 msg。
 */
import { ElMessageBox } from "element-plus";

/**
 * 删除/危险操作二次确认。
 * 用户点击确认返回 true, 取消/关闭返回 false。
 *
 * 用法:
 *   if (!(await confirmDanger(`确定删除文档 '${doc.title}' 吗？`))) return;
 */
export async function confirmDanger(
  message: string,
  options: {
    title?: string;
    confirmText?: string;
    cancelText?: string;
  } = {}
): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, options.title ?? "删除确认", {
      type: "warning",
      confirmButtonText: options.confirmText ?? "删除",
      cancelButtonText: options.cancelText ?? "取消",
    });
    return true;
  } catch {
    // 用户取消 / 关闭弹窗
    return false;
  }
}
