import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Isolated T14 preview. The React application itself is unchanged.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 18000,
    strictPort: true,
    watch: { usePolling: true, interval: 1000 },
    proxy: {
      '/camera/gripper': { target: 'http://127.0.0.1:8091', rewrite: path => path.replace(/^\/camera\/gripper/, '') },
      '/api': {
        target: 'http://127.0.0.1:18080',
        changeOrigin: false,
        configure(proxy) {
          proxy.on('proxyReq', (proxyReq, request) => {
            const address = request.socket.remoteAddress;

            // 브라우저가 보낸 IP 헤더는 신뢰하지 않는다.
            proxyReq.removeHeader('X-Real-IP');

            // 실제 로컬 접속일 때만 운영자 IP를 전달한다.
            if (
              address === '127.0.0.1' ||
              address === '::1' ||
              address === '::ffff:127.0.0.1'
            ) {
              proxyReq.setHeader('X-Real-IP', '127.0.0.1');
            }
          });
        },
      },
    },
  },
});
