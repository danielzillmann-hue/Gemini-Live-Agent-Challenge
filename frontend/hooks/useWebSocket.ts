import { useEffect, useRef, useCallback } from "react";
import { useGameStore } from "./useGameStore";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8080";
const MAX_RECONNECT_DELAY = 30000; // 30 seconds max

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const reconnectAttempts = useRef(0);
  const { setConnected, handleWSMessage } = useGameStore();

  const connect = useCallback(() => {
    if (!sessionId) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_URL}/ws/${sessionId}`);

    ws.onopen = () => {
      const wasReconnect = reconnectAttempts.current > 0;
      setConnected(true);
      reconnectAttempts.current = 0;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      // Notify user of reconnection (session may have been restored from Firestore)
      if (wasReconnect) {
        handleWSMessage({
          type: "system_notice",
          data: { message: "Reconnected to server. Session restored." },
        });
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleWSMessage(msg);
      } catch {
        console.error("Failed to parse WebSocket message");
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s max
      const delay = Math.min(
        1000 * Math.pow(2, reconnectAttempts.current),
        MAX_RECONNECT_DELAY
      );
      reconnectAttempts.current += 1;
      reconnectTimer.current = setTimeout(() => {
        connect();
      }, delay);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [sessionId, setConnected, handleWSMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback(
    (type: string, data: Record<string, unknown> = {}) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type, data }));
      }
    },
    []
  );

  return { send, isConnected: wsRef.current?.readyState === WebSocket.OPEN };
}
