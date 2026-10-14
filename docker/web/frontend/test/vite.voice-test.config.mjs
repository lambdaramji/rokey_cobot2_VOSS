import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// 격리 시험에서 실제 SSE 소켓을 종료한다. 브라우저 이벤트를 모의 발행하지 않는다.
const disconnectProbe = {
 name:'voice-sse-disconnect-probe',
 configureServer(server){
  const streams=new Set();
  server.middlewares.use((request,response,next)=>{
   if(request.url==='/__voice_test/drop-sse'){
    for(const stream of streams)stream.destroy();
    response.end('closed');return;
   }
   if(request.url==='/api/stream'){
    streams.add(response);response.on('close',()=>streams.delete(response));
   }
   next();
  });
 },
};
// 운영 프록시 설정은 바꾸지 않는다.
export default defineConfig({ plugins:[react(),disconnectProbe], server:{host:'127.0.0.1',strictPort:true,
  proxy:{'/api':{target:process.env.VOSS_TEST_BACKEND_URL,changeOrigin:false}}} });
