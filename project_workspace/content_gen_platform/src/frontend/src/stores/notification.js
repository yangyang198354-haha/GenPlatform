import { defineStore } from "pinia";
import { ref } from "vue";
import { useAuthStore } from "./auth";

export const useNotificationStore = defineStore("notification", () => {
  const notifications = ref([]);
  const connected = ref(false);
  let ws = null;
  let retryCount = 0;
  const MAX_RETRIES = 5;

  function connect() {
    const auth = useAuthStore();
    if (!auth.accessToken || ws?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/notifications/?token=${auth.accessToken}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      connected.value = true;
      retryCount = 0;
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      notifications.value.unshift({ ...data, id: Date.now(), read: false });
    };

    ws.onclose = () => {
      connected.value = false;
      if (retryCount < MAX_RETRIES) {
        retryCount++;
        setTimeout(connect, Math.min(1000 * 2 ** retryCount, 30000));
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  function disconnect() {
    ws?.close();
    ws = null;
    connected.value = false;
    retryCount = MAX_RETRIES; // prevent auto-reconnect
  }

  function markRead(id) {
    const n = notifications.value.find((n) => n.id === id);
    if (n) n.read = true;
  }

  const unreadCount = () => notifications.value.filter((n) => !n.read).length;

  return { notifications, connected, connect, disconnect, markRead, unreadCount };
});
