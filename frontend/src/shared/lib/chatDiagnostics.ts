const CHAT_DIAGNOSTIC_EVENT = "krip:chat-network-error";

export interface ChatDiagnosticPayload {
  action: string;
  detail?: string;
  roomId?: string;
  extra?: unknown;
}

export function reportChatNetworkError(payload: ChatDiagnosticPayload): void {
  const entry = {
    ...payload,
    occurredAt: new Date().toISOString(),
  };

  console.error("[chat-network]", entry);
  window.dispatchEvent(new CustomEvent(CHAT_DIAGNOSTIC_EVENT, { detail: entry }));
}
