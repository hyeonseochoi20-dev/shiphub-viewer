/**
 * 3D 캔버스에서 '점 찍기'로 볼 클릭을 판정한다.
 *
 * 왜 이렇게 바뀌었나
 *   처음에는 pointerdown/up 사이의 이동 거리를 직접 재서 "4픽셀 넘으면 드래그"로 판정했다.
 *   그런데 그 4는 CSS 픽셀이라 고배율 화면에서 손떨림만으로 넘어갔고, 배율에 비례시켜
 *   키워봐도 환경에 따라 여전히 안 찍히는 경우가 남았다. 임계값을 계속 조정하는 접근
 *   자체가 틀렸다 - 브라우저는 이미 플랫폼별로 이 판정을 하고 있고, 그 결과가 click 이벤트다.
 *
 *   그래서 click 이벤트를 그대로 쓴다. 브라우저가 클릭이라고 하면 클릭이다.
 *   다만 궤도 회전을 크게 돌린 뒤에도 click 이 뜨는 브라우저가 있어, 그것만 걸러낸다.
 *   기준은 아주 느슨하게(25px) 둔다 - 실수로 점을 하나 더 찍는 것이,
 *   눌러도 아무 반응이 없는 것보다 낫다.
 */

const DRAG_PX = 25      // 이만큼 넘게 끌었으면 궤도 회전으로 본다
const DRAG_MS = 800     // 이보다 오래 눌렀으면 회전으로 본다

/**
 * 캔버스에 클릭 처리기를 붙인다. 정리 함수를 돌려준다.
 * @param {HTMLElement} el 대상 캔버스
 * @param {(e: PointerEvent|MouseEvent) => void} onPick 클릭으로 판정됐을 때 호출
 */
export function attachPickHandler(el, onPick) {
  let down = null

  const handleDown = (e) => {
    if (e.button !== undefined && e.button !== 0) { down = null; return }  // 좌클릭만
    down = { x: e.clientX, y: e.clientY, t: e.timeStamp }
  }

  const handleClick = (e) => {
    const d = down
    down = null
    // down 을 못 잡았어도(캡처 순서 등) 브라우저가 click 이라 했으면 존중한다
    if (d) {
      const moved = Math.hypot(e.clientX - d.x, e.clientY - d.y)
      const held = e.timeStamp - d.t
      if (moved > DRAG_PX || held > DRAG_MS) return
    }
    onPick(e)
  }

  el.addEventListener('pointerdown', handleDown)
  el.addEventListener('click', handleClick)
  return () => {
    el.removeEventListener('pointerdown', handleDown)
    el.removeEventListener('click', handleClick)
  }
}
