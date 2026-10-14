import { useEffect, useRef } from "react";
import { liveUrl } from "./api";

export interface LiveMessage {
  type: "trust" | "decision";
  data: Record<string, unknown> & { session_id: string };
}

const RECONNECT_MS = 3000;

/** Calls ``onMessage`` for every trust update and decision the server pushes; reconnects after drops. */
export function useLiveFeed(token: string | null, onMessage: (message: LiveMessage) => void) {
  const handler = useRef(onMessage);
  handler.current = onMessage;

  useEffect(() => {
    if (!token) return;
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let stopped = false;

    const connect = () => {
      socket = new WebSocket(liveUrl(token));
      socket.onmessage = (event: MessageEvent<string> | { data: string }) => {
        try {
          handler.current(JSON.parse(event.data) as LiveMessage);
        } catch {
          // Ignore anything that is not a feed message.
        }
      };
      socket.onclose = () => {
        if (!stopped) timer = window.setTimeout(connect, RECONNECT_MS);
      };
    };
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, [token]);
}
