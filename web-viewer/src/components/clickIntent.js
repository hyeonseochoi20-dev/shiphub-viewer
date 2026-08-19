/**
 * 클릭인지 드래그인지 판정한다.
 *
 * 왜 따로 뺐나
 *   측정·주석·반지름 세 도구가 각각 "4픽셀 이상 움직였으면 드래그"라고 판정하고 있었다.
 *   그런데 이 4는 CSS 픽셀 기준이라, 2560x1600을 150%로 쓰는 화면에서는 손끝의 미세한
 *   떨림만으로도 넘어간다. 실제로 "백 번 눌러야 한 번 찍힌다"는 증상이 여기서 나왔다.
 *
 * 어떻게 고쳤나
 *   - 임계값을 화면 배율(devicePixelRatio)에 비례시킨다. 고DPI일수록 같은 손떨림이
 *     더 큰 CSS 픽셀 변위로 잡히므로 허용치도 같이 커져야 한다.
 *   - 포인터 종류를 본다. 마우스보다 터치/펜이 훨씬 많이 흔들린다.
 *   - 시간도 함께 본다. 궤도 회전은 보통 길게 끌기 때문에, 짧게 눌렀다 뗐으면
 *     조금 움직였어도 클릭으로 본다. 반대로 오래 눌렀으면 거리와 무관하게 드래그다.
 */

const BASE_PX = 4          // 마우스 기준 기본 허용 변위(CSS 픽셀)
const TOUCH_MULT = 2.5     // 터치/펜은 접촉면이 넓어 더 많이 흔들린다
const QUICK_MS = 250       // 이 시간 안에 뗐으면 짧은 클릭으로 본다
const QUICK_MULT = 2.0     // 짧은 클릭에는 변위를 더 너그럽게 본다
const HOLD_MS = 600        // 이보다 오래 눌렀으면 움직임이 적어도 드래그로 본다

export function dragThresholdPx(pointerType = 'mouse', quick = false) {
  const dpr = Math.min(Math.max(window.devicePixelRatio || 1, 1), 3)
  let px = BASE_PX * dpr
  if (pointerType === 'touch' || pointerType === 'pen') px *= TOUCH_MULT
  if (quick) px *= QUICK_MULT
  return px
}

/** 눌렀다 뗀 한 쌍이 '클릭'으로 볼 만한가 */
export function isClick(down, up) {
  if (!down) return false
  const dt = (up.timeStamp ?? performance.now()) - (down.timeStamp ?? 0)
  if (dt > HOLD_MS) return false                       // 오래 끌었으면 궤도 회전
  const dx = up.clientX - down.clientX
  const dy = up.clientY - down.clientY
  return Math.hypot(dx, dy) <= dragThresholdPx(up.pointerType || down.pointerType, dt <= QUICK_MS)
}
