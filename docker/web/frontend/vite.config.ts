// 로컬 프런트 개발 서버에서 Spring Boot API를 프록시한다.
// 실제 배포의 프록시는 Nginx가 맡는다 (ADR-0006).
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins: [react()], server: { host:'127.0.0.1', port:5173, proxy: { '/api': { target:'http://127.0.0.1:8080', changeOrigin:false } } } });
