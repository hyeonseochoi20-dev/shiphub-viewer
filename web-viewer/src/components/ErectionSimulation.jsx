import React, { useEffect, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'

function isToolObject(obj) {
  let p = obj
  while (p) {
    if (p.userData?.isTool) return true
    p = p.parent
  }
  return false
}

const RING_COUNT = 10

// 정점 Y좌표 분포로 "데크(상갑판)" 높이를 추정한다.
// 선체(바닥~옆판~갑판)는 정점이 촘촘하게 이어지다가, 갑판보다 위(배관/의장/거주구)로 가면
// 정점 밀도가 급격히 옅어지는 지점이 생긴다 - 그 첫 급락 지점을 데크 상단으로 판정.
// 단순 비율(예: 상부 40%) 대신 이 방식을 쓰는 이유: 데크는 보여야 하고 그 위 배관만 숨겨야 하기 때문.
function estimateDeckY(yValues, yMin, yMax, bins = 48) {
  const range = yMax - yMin || 1
  const hist = new Array(bins).fill(0)
  yValues.forEach((y) => {
    const idx = Math.min(bins - 1, Math.max(0, Math.floor(((y - yMin) / range) * bins)))
    hist[idx]++
  })
  const skip = Math.floor(bins * 0.12) // 선저 초반부는 건너뜀
  let bestIdx = Math.floor(bins * 0.45) // 못 찾으면 기본값
  for (let i = skip + 1; i < bins - 2; i++) {
    const cur = hist[i]
    const next = hist[i + 1]
    if (cur > 2 && next < cur * 0.4) {
      bestIdx = i
      break
    }
  }
  return yMin + ((bestIdx + 1) / bins) * range
}

export function erectionStageLabel(progress) {
  if (progress < 15) return '1단계: 선행의장 · 턴오버 (중조립 → 대조립)'
  if (progress < 25) return '2단계: P.E(Pre-Erection) - 크레인 가반하중 내 대블록 결합'
  if (progress < 85) return '3단계: 도크 탑재 - 선체 링블록 (미드쉽 → 선수/선미 확장)'
  return '4단계: 거주구/선원구·의장 블록 탑재 (선체 완성 후 별도 탑재)'
}

function buildRingOrder() {
  const midRing = Math.floor((RING_COUNT - 1) / 2)
  const order = []
  for (let ring = 0; ring < RING_COUNT; ring++) {
    const dist = Math.abs(ring - midRing)
    const isAftFirst = ring <= midRing
    order.push({ ring, rank: dist * 2 + (isAftFirst ? 0 : 1) })
  }
  order.sort((a, b) => a.rank - b.rank)
  return order.map((o) => o.ring)
}
const RING_ORDER = buildRingOrder()

export default function ErectionSimulation({ active, progress, deckFraction }) {
  const { gl, scene } = useThree()
  const [lengthKey, setLengthKey] = useState('x')
  const [bounds, setBounds] = useState(null)
  const [deckY, setDeckY] = useState(null)
  const lockedRef = useRef(false)
  const patchedRef = useRef([])

  useEffect(() => {
    gl.localClippingEnabled = true
  }, [gl])

  useFrame(() => {
    if (!active || lockedRef.current) return
    const box = new THREE.Box3()
    const yValues = []
    let found = false
    scene.traverse((obj) => {
      if (obj.isMesh && obj.geometry && !isToolObject(obj)) {
        box.expandByObject(obj)
        found = true
        const posAttr = obj.geometry.attributes.position
        if (posAttr) {
          const step = Math.max(1, Math.floor(posAttr.count / 2000))
          const v = new THREE.Vector3()
          for (let i = 0; i < posAttr.count; i += step) {
            v.fromBufferAttribute(posAttr, i).applyMatrix4(obj.matrixWorld)
            yValues.push(v.y)
          }
        }
      }
    })
    if (found) {
      lockedRef.current = true
      const sizeX = box.max.x - box.min.x
      const sizeZ = box.max.z - box.min.z
      setLengthKey(sizeX >= sizeZ ? 'x' : 'z')
      setBounds(box)
      setDeckY(estimateDeckY(yValues, box.min.y, box.max.y))
    }
  })

  // 3단계(25~85%): 선체 링블록 순차 탑재 / 4단계(85~100%): 거주구·의장 블록 탑재
  const dockT = THREE.MathUtils.clamp((progress - 25) / 60, 0, 1)
  const supT = THREE.MathUtils.clamp((progress - 85) / 15, 0, 1)
  const rawIdx = dockT * RING_COUNT
  const completedCount = Math.min(RING_COUNT, Math.floor(rawIdx))
  const currentSeqIdx = Math.min(RING_COUNT - 1, completedCount)
  const withinRingT = active && dockT < 1 ? rawIdx - completedCount : 1

  // 수동 슬라이더(deckFraction, 0~1)가 있으면 그걸 우선 사용 - 자동판별이 부정확할 수 있어 눈으로 직접 맞출 수 있게 함
  const thresholdY = bounds
    ? deckFraction != null
      ? bounds.min.y + (bounds.max.y - bounds.min.y) * deckFraction
      : deckY ?? bounds.min.y + (bounds.max.y - bounds.min.y) * 0.45
    : 0

  // 클리핑: 선체(하부)는 완료된 링 구간만, 상부(거주구·의장)는 4단계에서 착지 전까지 항상 숨김
  useEffect(() => {
    const clear = () => {
      patchedRef.current.forEach(({ material }) => {
        material.clippingPlanes = null
      })
      patchedRef.current = []
    }
    clear()

    if (!active || !bounds) return undefined

    const completedRings = RING_ORDER.slice(0, completedCount)
    const lengthMin = bounds.min[lengthKey]
    const lengthMax = bounds.max[lengthKey]
    const lengthRange = lengthMax - lengthMin
    const ringBounds = (ringIdx) => [
      lengthMin + (ringIdx / RING_COUNT) * lengthRange,
      lengthMin + ((ringIdx + 1) / RING_COUNT) * lengthRange,
    ]

    let lo = lengthMin + lengthRange / 2 - 0.001
    let hi = lengthMin + lengthRange / 2 + 0.001
    completedRings.forEach((r) => {
      const [a, b] = ringBounds(r)
      lo = Math.min(lo, a)
      hi = Math.max(hi, b)
    })

    const aftNormal = new THREE.Vector3()
    aftNormal[lengthKey] = 1
    const fwdNormal = new THREE.Vector3()
    fwdNormal[lengthKey] = -1
    const planes = [new THREE.Plane(aftNormal, -lo), new THREE.Plane(fwdNormal, hi)]

    if (supT < 1) {
      // 거주구/의장 착지 전에는 상부(threshold 위)를 항상 클리핑해서 숨김
      planes.push(new THREE.Plane(new THREE.Vector3(0, -1, 0), thresholdY))
    }

    scene.traverse((obj) => {
      if (obj.isMesh && obj.material && !isToolObject(obj)) {
        const materials = Array.isArray(obj.material) ? obj.material : [obj.material]
        materials.forEach((m) => {
          m.clippingPlanes = planes
          patchedRef.current.push({ material: m })
        })
      }
    })

    return clear
  }, [active, bounds, lengthKey, completedCount, supT, thresholdY, scene])

  if (!active || !bounds) return null

  const otherKey = lengthKey === 'x' ? 'z' : 'x'
  const otherSize = bounds.max[otherKey] - bounds.min[otherKey]
  const otherCenter = (bounds.max[otherKey] + bounds.min[otherKey]) / 2
  const lengthMin = bounds.min[lengthKey]
  const lengthMax = bounds.max[lengthKey]
  const lengthRange = lengthMax - lengthMin
  const fullYSize = bounds.max.y - bounds.min.y

  // 3단계: 현재 링블록이 하늘에서 내려오는 애니메이션
  if (dockT > 0 && dockT < 1) {
    const spatialRing = RING_ORDER[currentSeqIdx]
    const ringLo = lengthMin + (spatialRing / RING_COUNT) * lengthRange
    const ringHi = lengthMin + ((spatialRing + 1) / RING_COUNT) * lengthRange
    const ringCenterLen = (ringLo + ringHi) / 2
    const ringLenSize = ringHi - ringLo

    const hullYSize = thresholdY - bounds.min.y
    const restY = bounds.min.y + hullYSize / 2
    const skyY = thresholdY + fullYSize * 1.5

    const easeOut = 1 - Math.pow(1 - withinRingT, 3)
    const currentY = skyY + (restY - skyY) * easeOut

    const boxPos = { x: 0, y: currentY, z: 0 }
    boxPos[lengthKey] = ringCenterLen
    boxPos[otherKey] = otherCenter

    const boxArgs =
      lengthKey === 'x'
        ? [ringLenSize * 0.92, hullYSize * 0.92, otherSize * 0.92]
        : [otherSize * 0.92, hullYSize * 0.92, ringLenSize * 0.92]

    return (
      <group userData={{ isTool: true }}>
        <mesh position={[boxPos.x, boxPos.y, boxPos.z]}>
          <boxGeometry args={boxArgs} />
          <meshStandardMaterial color="#facc15" transparent opacity={0.45} depthWrite={false} />
        </mesh>
        <mesh position={[boxPos.x, (boxPos.y + skyY + fullYSize) / 2, boxPos.z]}>
          <cylinderGeometry args={[0.15, 0.15, Math.max(skyY + fullYSize - boxPos.y, 0.1), 6]} />
          <meshBasicMaterial color="#facc15" transparent opacity={0.5} />
        </mesh>
        <Html position={[boxPos.x, boxPos.y + boxArgs[1] / 2 + 1, boxPos.z]} center>
          <div className="px-1.5 py-0.5 rounded text-[10px] font-semibold text-yellow-300 bg-black/80 pointer-events-none whitespace-nowrap">
            선체 Ring #{spatialRing} 탑재 중 ({Math.round(withinRingT * 100)}%)
          </div>
        </Html>
      </group>
    )
  }

  // 4단계: 거주구/선원구·의장 블록이 통째로 하늘에서 내려와 완성된 선체 위에 안착
  if (dockT >= 1 && supT > 0 && supT < 1) {
    const supYSize = bounds.max.y - thresholdY
    const restY = thresholdY + supYSize / 2
    const skyY = bounds.max.y + fullYSize * 1.8

    const easeOut = 1 - Math.pow(1 - supT, 3)
    const currentY = skyY + (restY - skyY) * easeOut

    const boxPos = { x: 0, y: currentY, z: 0 }
    boxPos[lengthKey] = (lengthMin + lengthMax) / 2
    boxPos[otherKey] = otherCenter

    const boxArgs =
      lengthKey === 'x'
        ? [lengthRange * 0.5, supYSize * 0.92, otherSize * 0.85]
        : [otherSize * 0.85, supYSize * 0.92, lengthRange * 0.5]

    return (
      <group userData={{ isTool: true }}>
        <mesh position={[boxPos.x, boxPos.y, boxPos.z]}>
          <boxGeometry args={boxArgs} />
          <meshStandardMaterial color="#f472b6" transparent opacity={0.45} depthWrite={false} />
        </mesh>
        <mesh position={[boxPos.x, (boxPos.y + skyY + fullYSize) / 2, boxPos.z]}>
          <cylinderGeometry args={[0.15, 0.15, Math.max(skyY + fullYSize - boxPos.y, 0.1), 6]} />
          <meshBasicMaterial color="#f472b6" transparent opacity={0.5} />
        </mesh>
        <Html position={[boxPos.x, boxPos.y + boxArgs[1] / 2 + 1, boxPos.z]} center>
          <div className="px-1.5 py-0.5 rounded text-[10px] font-semibold text-pink-300 bg-black/80 pointer-events-none whitespace-nowrap">
            거주구/의장 블록 탑재 중 ({Math.round(supT * 100)}%)
          </div>
        </Html>
      </group>
    )
  }

  return null
}
