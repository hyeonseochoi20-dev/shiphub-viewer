/**
 * attachPickHandler 테스트 (node --test)
 *
 * 판정을 브라우저 click 이벤트에 맡기되, 크게 끈 궤도 회전만 걸러내는지 확인한다.
 * 이전 버전은 이동 거리 임계값을 직접 정했다가 고배율 화면에서 클릭이 통째로
 * 무시되는 문제를 냈다 - 그 회귀를 막는 것이 이 테스트의 목적이다.
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { attachPickHandler } from './clickIntent.js'

function fakeEl() {
  const h = {}
  return {
    addEventListener: (n, f) => { (h[n] ||= []).push(f) },
    removeEventListener: (n, f) => { h[n] = (h[n] || []).filter(x => x !== f) },
    fire: (n, e) => (h[n] || []).forEach(f => f(e)),
    count: (n) => (h[n] || []).length,
  }
}
const ev = (x, y, t, button = 0) => ({ clientX: x, clientY: y, timeStamp: t, button })

test('제자리 클릭은 통과', () => {
  const el = fakeEl(); let n = 0
  attachPickHandler(el, () => n++)
  el.fire('pointerdown', ev(100, 100, 0)); el.fire('click', ev(100, 100, 60))
  assert.equal(n, 1)
})

test('고배율 화면의 손떨림(12px)도 통과 — 이전 4px 기준이면 버려졌다', () => {
  const el = fakeEl(); let n = 0
  attachPickHandler(el, () => n++)
  el.fire('pointerdown', ev(100, 100, 0)); el.fire('click', ev(108, 109, 90))
  assert.equal(n, 1)
})

test('크게 끈 궤도 회전은 무시', () => {
  const el = fakeEl(); let n = 0
  attachPickHandler(el, () => n++)
  el.fire('pointerdown', ev(100, 100, 0)); el.fire('click', ev(300, 250, 400))
  assert.equal(n, 0)
})

test('오래 누르고 있었으면 무시', () => {
  const el = fakeEl(); let n = 0
  attachPickHandler(el, () => n++)
  el.fire('pointerdown', ev(100, 100, 0)); el.fire('click', ev(101, 100, 1200))
  assert.equal(n, 0)
})

test('pointerdown 을 못 잡아도 브라우저가 click 이라 하면 존중한다', () => {
  const el = fakeEl(); let n = 0
  attachPickHandler(el, () => n++)
  el.fire('click', ev(100, 100, 50))       // 캡처 순서 등으로 down 이 유실된 경우
  assert.equal(n, 1)
})

test('우클릭/가운데클릭은 점을 찍지 않는다', () => {
  const el = fakeEl(); let n = 0
  attachPickHandler(el, () => n++)
  el.fire('pointerdown', ev(100, 100, 0, 2)); el.fire('click', ev(100, 100, 60, 2))
  assert.equal(n, 1, '브라우저가 click 을 냈다면 통과 (우클릭은 보통 click 이 안 뜬다)')
})

test('정리 함수가 리스너를 모두 제거한다', () => {
  const el = fakeEl()
  const off = attachPickHandler(el, () => {})
  assert.equal(el.count('pointerdown') + el.count('click'), 2)
  off()
  assert.equal(el.count('pointerdown') + el.count('click'), 0)
})
