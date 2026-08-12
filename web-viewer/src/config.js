// 배포 환경(Vercel)에서는 프론트/백엔드가 서로 다른 도메인에 떠있으므로,
// 빌드 시점 환경변수로 실제 백엔드 URL을 주입한다. 로컬 개발(vite dev)에서는
// 비워두면 기존처럼 상대경로("/api/...")로 동작하고 vite.config.js의 프록시가 처리한다.
export const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
export const STREAMLIT_URL = import.meta.env.VITE_STREAMLIT_URL || 'http://localhost:8501'
