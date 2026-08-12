import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // 0.0.0.0 + :: 모두 바인드 - 기본값(IPv6 루프백만 바인드)이라 브라우저의 IPv4 localhost 해석과 안 맞았음
    open: true,
    proxy: {
      '/api': 'http://localhost:5000',
      '/models': {
        target: 'http://localhost:5000',
        bypass: (req) => {
          // public/models 정적 파일이 있으면 vite가 직접 서빙, 없으면 컨버터 서버로 프록시
          const filePath = path.join(process.cwd(), 'public', req.url)
          if (fs.existsSync(filePath)) return req.url
        }
      }
    }
  }
})