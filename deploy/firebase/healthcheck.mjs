import net from 'node:net';

await Promise.all([9099, 9000].map(port => new Promise((resolve, reject) => {
  const socket = net.createConnection({ host: '127.0.0.1', port });
  socket.setTimeout(1500);
  socket.once('connect', () => { socket.destroy(); resolve(); });
  socket.once('error', reject);
  socket.once('timeout', () => { socket.destroy(); reject(new Error('Emulator not listening')); });
})));
