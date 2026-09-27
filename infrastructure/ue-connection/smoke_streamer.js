const httpPort = Number(process.argv[2] || 8080);
const timeoutMs = Number(process.argv[3] || 10000);
const websocketModule = process.argv[4] || "ws";
const WebSocket = require(websocketModule);
const socket = new WebSocket(`ws://127.0.0.1:${httpPort}`);
let pollTimer;

const timeout = setTimeout(() => {
  console.error(`Timed out waiting for streamerList on port ${httpPort}.`);
  clearInterval(pollTimer);
  socket.close();
  process.exit(2);
}, timeoutMs);

socket.on("open", () => {
  const requestStreamers = () => {
    socket.send(JSON.stringify({ type: "listStreamers" }));
  };
  requestStreamers();
  pollTimer = setInterval(requestStreamers, 1000);
});

socket.on("message", (data) => {
  const message = JSON.parse(data.toString());
  if (message.type !== "streamerList") return;

  const ids = Array.isArray(message.ids) ? message.ids : [];
  if (ids.length === 0) return;

  clearTimeout(timeout);
  clearInterval(pollTimer);
  console.log(JSON.stringify({ ok: true, streamer_ids: ids }));
  socket.close();
  process.exit(0);
});

socket.on("error", (error) => {
  clearTimeout(timeout);
  clearInterval(pollTimer);
  console.error(error.message);
  process.exit(4);
});
