// Keeps a native-messaging connection to the ChatOverlay desktop app, so its
// "Get cookies" button can fetch cookies through this extension's official
// chrome.cookies access, without closing the browser.
importScripts("cookies.js");

const HOST_NAME = "com.chatoverlay.native_host";
let port = null;

function connect() {
  if (port) return;
  try {
    port = chrome.runtime.connectNative(HOST_NAME);
  } catch (e) {
    port = null;
    return;
  }
  port.onMessage.addListener(async (msg) => {
    if (!msg) return;
    if (msg.cmd === "ping") {
      port.postMessage({ ok: true, pong: true });
      return;
    }
    if (msg.cmd === "export") {
      try {
        const { text, count } = await collectCookiesText();
        port.postMessage({ ok: true, cookies: text, count });
      } catch (e) {
        port.postMessage({ ok: false, error: String(e) });
      }
    }
  });
  port.onDisconnect.addListener(() => {
    if (chrome.runtime.lastError) {
      console.log("ChatOverlay native host disconnected:", chrome.runtime.lastError.message);
    }
    port = null;
  });
}

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
chrome.alarms.create("chatoverlay-reconnect", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "chatoverlay-reconnect") connect();
});
connect();
