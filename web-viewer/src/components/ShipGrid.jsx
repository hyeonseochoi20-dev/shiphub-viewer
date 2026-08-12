import React, { useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { Line, Text } from '@react-three/drei'
import * as THREE from 'three'

function isToolObject(obj) {
  let p = obj
  while (p) {
    if (p.userData?.isTool) return true
    p = p.parent
  }
  return false
}

// 조선 좌표그리드(라인즈 플랜) - 프레임(Fr, 횡단면) + 베이스라인/워터라인(BL·WL, 수평면) + 센터라인/버톡라인(CL·Butt, 종통면)
// 표준 약어: BL=Base Line(기선, 최하단 1개), WL=Waterline(흘수선), CL=Center Line(선체중심선), Butt=Buttock Line(종통선)
// 현재 씬에 로드된 모델의 실제 바운딩박스에 맞춰 자동으로 배치
// 각 라인의 마커를 클릭하면 그 위치에서 바로 단면(클리핑)을 켤 수 있다 (onSelectSection(cadAxis, worldPos))
export default function ShipGrid({ divisions = 10, onSelectSection }) {
  const { scene } = useThree()
  const [bounds, setBounds] = useState(null)
  const lockedRef = useRef(false)

  // 모델은 비동기(useGLTF/Suspense)로 로드되므로, 실제 메시가 씬에 나타날 때까지 매 프레임 재확인
  useFrame(() => {
    if (lockedRef.current) return
    const box = new THREE.Box3()
    let found = false
    scene.traverse((obj) => {
      if (obj.isMesh && obj.geometry && !isToolObject(obj)) {
        box.expandByObject(obj)
        found = true
      }
    })
    if (found) {
      lockedRef.current = true
      setBounds(box)
    }
  })

  if (!bounds) return null

  // 수평 두 축(X, Z) 중 더 긴 쪽을 선체 길이(선수-선미) 방향으로 자동 판단
  const sizeX = bounds.max.x - bounds.min.x
  const sizeZ = bounds.max.z - bounds.min.z
  const lengthAlongX = sizeX >= sizeZ
  const length = Math.max(lengthAlongX ? sizeX : sizeZ, 0.001)
  const halfWidth = (lengthAlongX ? sizeZ : sizeX) / 2 + length * 0.03
  const baseY = bounds.min.y - length * 0.02
  const fontSize = length * 0.018

  const lengthMin = lengthAlongX ? bounds.min.x : bounds.min.z
  const widthCenter = lengthAlongX ? (bounds.min.z + bounds.max.z) / 2 : (bounds.min.x + bounds.max.x) / 2

  // 길이축 위 좌표 -> 3D 포인트 (지정 높이/폭 오프셋)
  const pt = (lengthPos, y, widthOffset) =>
    lengthAlongX ? [lengthPos, y, widthCenter + widthOffset] : [widthCenter + widthOffset, y, lengthPos]

  const spacing = length / divisions
  const stations = Array.from({ length: divisions + 1 }, (_, i) => lengthMin + i * spacing)

  // 프레임 라인 (Fr, 횡단면) - 파랑
  const frameLines = stations.map((pos, i) => ({
    points: [pt(pos, baseY, -halfWidth), pt(pos, baseY, halfWidth)],
    label: `Fr.${i * 10}`,
    labelPos: pt(pos, baseY - fontSize, halfWidth + fontSize),
    markerPos: pt(pos, baseY, halfWidth),
    sectionAxis: 'x',
    sectionValue: pos, // 길이축 상의 실제 월드 좌표
  }))

  // 베이스라인/워터라인 (BL·WL, 수평면) - 노랑: 높이별로 선체 외곽을 둘러싼 사각 링
  // BL(기선)은 선저 기준 최하단 1개, 그 위로 WL1, WL2... 순서로 올라감
  const wlCount = 4
  const wlSpacing = (bounds.max.y - bounds.min.y) / wlCount
  const waterlines = Array.from({ length: wlCount + 1 }, (_, i) => {
    const y = bounds.min.y + i * wlSpacing
    const corners = [
      pt(lengthMin, y, -halfWidth),
      pt(lengthMin + length, y, -halfWidth),
      pt(lengthMin + length, y, halfWidth),
      pt(lengthMin, y, halfWidth),
      pt(lengthMin, y, -halfWidth),
    ]
    return {
      points: corners,
      label: i === 0 ? 'BL' : `WL${i}`,
      labelPos: pt(lengthMin - fontSize * 2, y, -halfWidth),
      markerPos: pt(lengthMin, y, -halfWidth),
      sectionAxis: 'z',
      sectionValue: y, // 수직(Y) 실제 월드 좌표
    }
  })

  // 센터라인/버톡라인 (CL·Butt, 종통면) - 초록: 폭 방향 오프셋별로 길이 전체를 가로지르는 선
  // 정중앙(offset=0)은 CL(센터라인), 나머지는 Butt.±N(버톡라인)으로 표기
  const blCount = 4
  const blSpacing = (halfWidth * 2) / blCount
  const buttocks = Array.from({ length: blCount + 1 }, (_, i) => {
    const offset = -halfWidth + i * blSpacing
    const signedIndex = i - blCount / 2
    return {
      points: [pt(lengthMin, baseY, offset), pt(lengthMin + length, baseY, offset)],
      label: signedIndex === 0 ? 'CL' : `Butt.${signedIndex > 0 ? '+' : ''}${signedIndex}`,
      labelPos: pt(lengthMin - fontSize * 2, baseY, offset),
      markerPos: pt(lengthMin, baseY, offset),
      sectionAxis: 'y',
      sectionValue: widthCenter + offset, // 폭축 실제 월드 좌표
    }
  })

  const marker = (posArr, color, sectionAxis, sectionValue, key) => (
    <mesh
      key={key}
      position={posArr}
      onClick={(e) => {
        e.stopPropagation()
        onSelectSection?.(sectionAxis, sectionValue)
      }}
      onPointerOver={(e) => {
        e.stopPropagation()
        document.body.style.cursor = onSelectSection ? 'pointer' : 'auto'
      }}
      onPointerOut={() => {
        document.body.style.cursor = 'auto'
      }}
    >
      <sphereGeometry args={[fontSize * 0.5, 8, 8]} />
      <meshBasicMaterial color={color} depthTest={false} />
    </mesh>
  )

  return (
    <group userData={{ isTool: true }}>
      {frameLines.map((f, i) => (
        <group key={`fr-${i}`}>
          <Line points={f.points} color="#3ba7ff" transparent opacity={0.45} lineWidth={1} />
          <Text position={f.labelPos} fontSize={fontSize} color="#3ba7ff" anchorX="center" anchorY="middle">
            {f.label}
          </Text>
          {marker(f.markerPos, '#3ba7ff', f.sectionAxis, f.sectionValue, `fr-m-${i}`)}
        </group>
      ))}

      {waterlines.map((w, i) => (
        <group key={`wl-${i}`}>
          <Line points={w.points} color="#facc15" transparent opacity={0.35} lineWidth={1} />
          <Text position={w.labelPos} fontSize={fontSize} color="#facc15" anchorX="right" anchorY="middle">
            {w.label}
          </Text>
          {marker(w.markerPos, '#facc15', w.sectionAxis, w.sectionValue, `wl-m-${i}`)}
        </group>
      ))}

      {buttocks.map((b, i) => {
        const isCenterline = b.label === 'CL'
        const color = isCenterline ? '#f87171' : '#4ade80'
        return (
          <group key={`bl-${i}`}>
            <Line
              points={b.points}
              color={color}
              transparent
              opacity={isCenterline ? 0.6 : 0.4}
              lineWidth={isCenterline ? 1.5 : 1}
              dashed={isCenterline}
              dashSize={isCenterline ? length * 0.02 : undefined}
              gapSize={isCenterline ? length * 0.01 : undefined}
            />
            <Text position={b.labelPos} fontSize={fontSize} color={color} anchorX="right" anchorY="middle">
              {b.label}
            </Text>
            {marker(b.markerPos, color, b.sectionAxis, b.sectionValue, `bl-m-${i}`)}
          </group>
        )
      })}
    </group>
  )
}
