/**
 * AskUser 全局响应桥接
 *
 * AskUserInlineCard 在聊天流深层渲染，响应回调通过此桥接
 * 避免长链条 props drilling。当前同时只有一个活跃 AskUser 请求。
 */

import type { AskUserValue } from "@/types/askUser";

export const askUserBridge = {
  resolve: null as
    | ((
        requestId: string,
        approved: boolean,
        value?: AskUserValue,
      ) => Promise<boolean>)
    | null,
};
