/**
 * 格式化工具函数
 */

/**
 * 格式化文件大小
 * @param bytes 字节数
 * @returns 可读的文件大小 (如 "2.5 MB")
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const size = parseFloat((bytes / Math.pow(k, i)).toFixed(2));
  return `${size} ${units[i]}`;
}

/**
 * 格式化日期时间
 * @param dateStr ISO 日期字符串
 * @param format 格式类型
 */
export function formatDate(
  dateStr: string | null | undefined,
  format: "full" | "date" | "time" | "relative" = "full"
): string {
  if (!dateStr) return "-";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "-";

  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const h = String(date.getHours()).padStart(2, "0");
  const min = String(date.getMinutes()).padStart(2, "0");
  const s = String(date.getSeconds()).padStart(2, "0");

  switch (format) {
    case "date":
      return `${y}-${m}-${d}`;
    case "time":
      return `${h}:${min}:${s}`;
    case "relative":
      return getRelativeTime(date);
    case "full":
    default:
      return `${y}-${m}-${d} ${h}:${min}:${s}`;
  }
}

/**
 * 计算相对时间 (如 "3分钟前", "2小时前")
 */
function getRelativeTime(date: Date): string {
  const now = Date.now();
  const diff = now - date.getTime();
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return "刚刚";
  if (minutes < 60) return `${minutes}分钟前`;
  if (hours < 24) return `${hours}小时前`;
  if (days < 30) return `${days}天前`;
  return formatDate(date.toISOString(), "date");
}
