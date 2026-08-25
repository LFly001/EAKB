/**
 * SSE 流式请求组合式函数 (fetch + ReadableStream)
 *
 * 为什么不用 EventSource: 不支持自定义 Header, 无法携带 Authorization Bearer。
 * 因此用 fetch 发起 POST, 手动解析 text/event-stream 分片。
 *
 * 断线策略 (Phase 8 完善):
 * - 未收到任何服务端内容前的网络失败 → 自动重连 (最多 2 次, 指数退避)。
 *   此时服务端尚未产生流式内容, 重连不会导致 LLM 重复计费/消息重复。
 * - 已收到部分内容后的断线 → 不自动重发 (避免重复计费), 提示用户手动重试。
 * - 浏览器离线 → 明确提示"网络已断开", 区分于服务端断流。
 *
 * 用法:
 *   const { isStreaming, start, stop } = useSSE();
 *   await start(CHAT_STREAM_PATH, { question: "..." }, {
 *     onMeta, onSources, onDelta, onDone, onError,
 *   });
 */
import { ref } from "vue";
import { storage } from "@/utils/storage";
import { TOKEN_KEY } from "@/utils/constants";
import type {
  ChatDoneEvent,
  ChatMetaEvent,
  ChatSourcesEvent,
} from "@/types/chat";

/** 未收到内容前的自动重连次数上限与退避间隔 (ms) */
const MAX_AUTO_RETRIES = 2;
const RETRY_DELAYS_MS = [1000, 2000];

// ==========================================
// 事件回调
// ==========================================

export interface SSEHandlers {
  /** meta 事件 — 流开始, 携带会话/消息标识 */
  onMeta?: (data: ChatMetaEvent) => void;
  /** sources 事件 — 检索来源 (delta 之前到达) */
  onSources?: (data: ChatSourcesEvent) => void;
  /** delta 事件 — 文本增量 (可能多次) */
  onDelta?: (content: string) => void;
  /** done 事件 — 生成完成 */
  onDone?: (data: ChatDoneEvent) => void;
  /** error 事件 / 网络断线 / 非 200 响应 */
  onError?: (message: string) => void;
}

// ==========================================
// 组合式函数
// ==========================================

/** 断流看门狗阈值 (ms): 连续无数据超过该时长判定连接挂起。
 * 注意首次请求的 Embedding 冷加载最长可达约 60s (启动预热已加载则不存在),
 * 取 90s 留足余量; 生成期间 delta 持续到达会不断重置计时 */
const SSE_STALL_TIMEOUT_MS = 90_000;

export function useSSE() {
  /** 当前是否正在流式生成 */
  const isStreaming = ref(false);

  let controller: AbortController | null = null;
  let watchdog: ReturnType<typeof setTimeout> | null = null;
  let watchdogFired = false;
  let stoppedByUser = false;

  /** 重新武装看门狗: 每收到一个事件帧重置计时 */
  function armWatchdog() {
    disarmWatchdog();
    watchdogFired = false;
    watchdog = setTimeout(() => {
      watchdogFired = true;
      controller?.abort(); // 触发 AbortError 分支, 按超时上报
    }, SSE_STALL_TIMEOUT_MS);
  }

  function disarmWatchdog() {
    if (watchdog) {
      clearTimeout(watchdog);
      watchdog = null;
    }
  }

  /** 单次请求: 成功(流正常终结/服务端 error 事件)返回 null, 否则返回失败原因 */
  async function runOnce(
    url: string,
    body: Record<string, unknown>,
    handlers: SSEHandlers
  ): Promise<{ reason: "network" | "aborted" | "timeout" } | null> {
    controller = new AbortController();

    const token = storage.get(TOKEN_KEY);

    try {
      const res = await fetch(`${import.meta.env.VITE_SSE_BASE_URL}${url}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      // 非 200: 流未建立, 解析统一 JSON 错误体 (业务错误直接透传, 不重试)
      if (!res.ok || !res.body) {
        let message = `请求失败 (${res.status})`;
        try {
          const err = await res.json();
          message = err.msg || err.detail || message;
        } catch {
          // 非 JSON 响应, 保留默认提示
        }
        handlers.onError?.(message);
        return null;
      }

      // 追踪流是否以 done/error 正常终结: 服务端崩溃/网关切断时 reader
      // 可能不抛异常而是直接返回 done=true, 需主动判定为断线
      let completed = false;
      armWatchdog();
      await parseStream(res.body, {
        onMeta: (data) => {
          armWatchdog();
          handlers.onMeta?.(data);
        },
        onSources: (data) => {
          armWatchdog();
          handlers.onSources?.(data);
        },
        onDelta: (content) => {
          armWatchdog();
          handlers.onDelta?.(content);
        },
        onDone: (data) => {
          disarmWatchdog();
          completed = true;
          handlers.onDone?.(data);
        },
        onError: (message) => {
          disarmWatchdog();
          completed = true;
          handlers.onError?.(message);
        },
      });
      disarmWatchdog();
      if (!completed) {
        return { reason: "network" };
      }
      return null;
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        // 用户主动停止不算错误; 看门狗触发的中止按超时上报
        return watchdogFired ? { reason: "timeout" } : { reason: "aborted" };
      }
      // 网络断线 / 服务端中断
      return { reason: "network" };
    } finally {
      disarmWatchdog();
      controller = null;
    }
  }

  /**
   * 发起流式请求并解析事件流, 直到 done/error/断线。
   * 重复调用会先中止上一次请求 (同一时间仅一条流)。
   */
  async function start(
    url: string,
    body: Record<string, unknown>,
    handlers: SSEHandlers
  ): Promise<void> {
    stop();
    stoppedByUser = false;
    isStreaming.value = true;

    // 已收到任何服务端内容? (判定重连是否会重复计费的依据)
    let receivedAny = false;
    // 包一层在首次内容到达时置位
    const trackHandlers: SSEHandlers = {
      ...handlers,
      onMeta: (data) => {
        receivedAny = true;
        handlers.onMeta?.(data);
      },
      onSources: (data) => {
        receivedAny = true;
        handlers.onSources?.(data);
      },
      onDelta: (content) => {
        receivedAny = true;
        handlers.onDelta?.(content);
      },
    };

    let retryCount = 0;
    try {
      while (true) {
        const failure = await runOnce(url, body, trackHandlers);

        if (failure === null) return; // 正常完成 (含服务端 error 事件)
        if (failure.reason === "aborted") return; // 用户主动停止
        if (failure.reason === "timeout") {
          handlers.onError?.("连接超时，请点击重试");
          return;
        }
        // network 失败:
        // 未收到任何内容且未超重试上限 → 自动重连 (服务端无内容产生, 不重复计费)
        if (!receivedAny && retryCount < MAX_AUTO_RETRIES) {
          retryCount += 1;
          isStreaming.value = true;
          await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[retryCount - 1]));
          if (stoppedByUser) return; // 退避等待期间用户点了停止
          continue;
        }
        // 浏览器离线 → 明确提示网络断开; 否则按断线提示手动重试
        if (!navigator.onLine) {
          handlers.onError?.("网络已断开，请恢复网络后重试");
        } else {
          handlers.onError?.("连接已中断，请点击重试");
        }
        return;
      }
    } finally {
      isStreaming.value = false;
    }
  }

  /** 中止当前流式请求 */
  function stop() {
    stoppedByUser = true;
    if (controller) {
      controller.abort();
      controller = null;
    }
    isStreaming.value = false;
  }

  return { isStreaming, start, stop };
}

// ==========================================
// SSE 帧解析 (内部)
// ==========================================

/**
 * 读取响应体流并逐帧分发事件。
 * SSE 帧格式: "event: xxx\ndata: {...}\n\n" (sse-starlette 输出格式)
 * 兼容 \r\n / \r 行尾与帧分隔 (部分代理/网关会改写换行符)。
 */
async function parseStream(
  body: ReadableStream<Uint8Array>,
  handlers: SSEHandlers
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  // 处理残留缓冲: 流结束仍未出现空行分隔符时按完整帧分发
  const flush = () => {
    if (buffer.trim()) {
      dispatchEvent(buffer, handlers);
      buffer = "";
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      flush();
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    // 分隔符兼容: 先统一 \r\n → \n (块边界跨 \r\n 时留到下一块再归一),
    // 再按空行切帧; \r 单行尾在切帧后逐帧清理
    buffer = buffer.replace(/\r\n/g, "\n");
    let sepIndex: number;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);
      dispatchEvent(raw, handlers);
    }
  }
}

/** 尝试解析 JSON, 失败返回 undefined (静默跳过非法帧) */
function tryParse(data: string): Record<string, unknown> | undefined {
  try {
    return JSON.parse(data) as Record<string, unknown>;
  } catch {
    return undefined;
  }
}

/** 按事件类型分发负载 */
function dispatchPayload(
  event: string,
  payload: Record<string, unknown>,
  handlers: SSEHandlers
): void {
  switch (event) {
    case "meta":
      handlers.onMeta?.(payload as unknown as ChatMetaEvent);
      break;
    case "sources":
      handlers.onSources?.(payload as unknown as ChatSourcesEvent);
      break;
    case "delta":
      handlers.onDelta?.((payload.content as string) ?? "");
      break;
    case "done":
      handlers.onDone?.(payload as unknown as ChatDoneEvent);
      break;
    case "error":
      handlers.onError?.((payload.message as string) || "生成失败");
      break;
    default:
      break;
  }
}

/** 解析单个 SSE 帧并分发到对应回调 */
function dispatchEvent(rawFrame: string, handlers: SSEHandlers): void {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of rawFrame.split("\n")) {
    const normalized = line.replace(/\r$/, "");
    if (normalized.startsWith("event:")) {
      event = normalized.slice(6).trim();
    } else if (normalized.startsWith("data:")) {
      dataLines.push(normalized.slice(5).trim());
    }
  }

  if (dataLines.length === 0) return;

  // 标准情况: 单 JSON data → 直接分发
  const payload = tryParse(dataLines.join(""));
  if (payload !== undefined) {
    dispatchPayload(event, payload, handlers);
    return;
  }
  // 异常兜底: data 内粘有多段 JSON → 逐行拆分分发 (帧粘连的降级处理)
  for (const line of dataLines) {
    const p = tryParse(line);
    if (p !== undefined) {
      dispatchPayload(event, p, handlers);
    }
  }
}
