// 배포 환경(Vercel)에서는 프론트/백엔드가 서로 다른 도메인에 떠있으므로,
// 빌드 시점 환경변수로 실제 백엔드 URL을 주입한다. 로컬 개발(vite dev)에서는
// 비워두면 기존처럼 상대경로("/api/...")로 동작하고 vite.config.js의 프록시가 처리한다.
export const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

// 'http://localhost:8501'로 고정해두면 다른 기기(휴대폰 등)에서 LAN IP로 접속했을 때
// "localhost"가 그 기기 자신을 가리키게 되어 연결이 거부된다 - 현재 페이지를 연 호스트를
// 그대로 재사용해서(PC에서 열면 localhost, 폰에서 10.0.0.16으로 열면 10.0.0.16) 항상 맞는
// 주소를 가리키게 한다. 배포 환경에서는 VITE_STREAMLIT_URL이 우선한다.
export const STREAMLIT_URL =
  import.meta.env.VITE_STREAMLIT_URL || `http://${window.location.hostname}:8501`
