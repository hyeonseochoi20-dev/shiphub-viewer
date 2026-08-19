/**
 * clickIntent 판정 테스트 (node --test)
 *
 * "백 번 눌러야 한 번 찍힌다"는 증상은 화면 배율과 손떨림이 겹쳐서 나온 것이라
 * 눈으로 재현·확인하기 어렵다. 조건을 숫자로 고정해 둔다.
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'

const load = async (dpr) => {
  global.window = { devicePixelRatio: dpr }
  global.performance = { now: () => 0 }
  const m = await import(`./clickIntent.js?dpr=${dpr}`)
  return m
}
const ev = (x, y, t, type = 'mouse') => ({ clientX: x, clientY: y, timeStamp: t, pointerType: type })

test('배율 100%: 제자리 클릭은 통과', async () => {
  const { isClick } = await load(1)
  assert.equal(isClick(ev(100, 100, 0), ev(100, 100, 80)), true)
})

test('배율 150%: 5px 떨림도 클릭으로 인정 (기존 4px 기준이면 버려졌다)', async () => {
  const { isClick } = await load(1.5)
  assert.equal(isClick(ev(100, 100, 0), ev(104, 103, 90)), true)
})

test('배율 200%: 8px 떨림까지 견딘다', async () => {
  const { isClick } = await load(2)
  assert.equal(isClick(ev(100, 100, 0), ev(106, 105, 100)), true)
})

test('명확한 드래그(60px)는 어떤 배율에서도 무시', async () => {
  for (const dpr of [1, 1.5, 2, 3]) {
    const { isClick } = await load(dpr)
    assert.equal(isClick(ev(100, 100, 0), ev(160, 140, 300)), false, `dpr=${dpr}`)
  }
})

test('오래 누르고 있었으면 거의 안 움직였어도 드래그로 본다', async () => {
  const { isClick } = await load(1.5)
  assert.equal(isClick(ev(100, 100, 0), ev(101, 100, 900)), false)
})

test('터치는 더 너그럽게 - 접촉면이 넓어 마우스보다 흔들린다', async () => {
  const { isClick } = await load(1.5)
  const p = [ev(100, 100, 0, 'touch'), ev(110, 108, 120, 'touch')]
  assert.equal(isClick(...p), true)
  const m = [ev(100, 100, 0, 'mouse'), ev(110, 108, 120, 'mouse')]
  assert.equal(isClick(...m), false)
})

test('down 이벤트가 없으면 클릭이 아니다', async () => {
  const { isClick } = await load(1)
  assert.equal(isClick(null, ev(100, 100, 50)), false)
})
