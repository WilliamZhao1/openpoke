import type { ChatBubble } from './types';

export function toBubbles(payload: unknown): ChatBubble[] {
  const messages = (payload as { messages?: unknown } | null)?.messages;
  if (!Array.isArray(messages)) return [];

  return messages
    .filter(message =>
      typeof message?.role === 'string' &&
      typeof message?.content === 'string' &&
      message.content.trim().length > 0,
    )
    .map((message, index) => ({
      id: `history-${index}`,
      role: message.role,
      // JSON parsing already decoded transport escapes. Preserve reviewed text.
      text: message.content,
    }));
}
