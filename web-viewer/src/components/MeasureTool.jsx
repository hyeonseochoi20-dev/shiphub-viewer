import React, { useEffect, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { Line, Html } from '@react-three/drei'
import * as THREE from 'three'

function isAncestorTool(obj) {
  let p = obj
  while (p) {
    if (p.userData?.isTool) return true
    p = p.parent
  }
  return false
}

// 측정 도구 - 클릭 두 번으로 두 점 사이 거리를 축별(길이/폭/수직)로 분해해서 표시
// snapRef가 있으면 SnapEngine이 실시간으로 판정한 꼭지점/모서리/면 스냅 좌표를 우선 사용
export default function MeasureTool({ active, snapRef }) {
  const { gl, camera, scene } = useThree()
  const [points, setPoints] = useState([])
  const [lengthAxis, setLengthAxis] = useState('x') // 씬의 실제 길이축(x 또는 z) 자동 판별
  const downPos = useRef(null)
  const raycaster = useRef(new THREE.Raycaster())
  const axisLockedRef = useRef(false)

  // 로드된 모델의 바운딩박스를 보고 어느 축이 선체 길이 방향인지 자동 판별 (SectionPlane/ShipGrid와 동일 규칙)
  useFrame(() => {
    if (axisLockedRef.current) return
    const box = new THREE.Box3()
    let found = false
    scene.traverse((obj) => {
      if (obj.isMesh && obj.geometry && !isAncestorTool(obj)) {
        box.expandByObject(obj)
        found = true
      }
    })
    if (found) {
      axisLockedRef.current = true
      setLengthAxis(box.max.x - box.min.x >= box.max.z - box.min.z ? 'x' : 'z')
    }
  })

  useEffect(() => {
    if (!active) {
      setPoints([])
      return
    }

    const onDown = (e) => {
      downPos.current = { x: e.clientX, y: e.clientY }
    }
    const onUp = (e) => {
      if (!downPos.current) return
      const dx = e.clientX - downPos.current.x
      const dy = e.clientY - downPos.current.y
      downPos.current = null
      if (Math.hypot(dx, dy) > 4) return // 드래그(궤도회전)는 무시

      // SnapEngine이 실시간으로 판정해둔 꼭지점/모서리/면 스냅 좌표를 우선 사용 (정밀 클릭)
      let hitPoint = snapRef?.current?.point
      if (!hitPoint) {
        const rect = gl.domElement.getBoundingClientRect()
        const ndc = new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1
        )
        raycaster.current.setFromCamera(ndc, camera)
        const hits = raycaster.current.intersectObjects(scene.children, true)
        const hit = hits.find((h) => !isAncestorTool(h.object))
        hitPoint = hit?.point
      }
      if (hitPoint) {
        setPoints((prev) => {
          const next = [...prev, hitPoint.clone()]
          return next.length > 2 ? [hitPoint.clone()] : next
        })
      }
    }

    gl.domElement.addEventListener('pointerdown', onDown)
    gl.domElement.addEventListener('pointerup', onUp)
    return () => {
      gl.domElement.removeEventListener('pointerdown', onDown)
      gl.domElement.removeEventListener('pointerup', onUp)
    }
  }, [active, gl, camera, scene, snapRef])

  if (!active || points.length < 1) return null

  const hasPair = points.length === 2
  const dist = hasPair ? points[0].distanceTo(points[1]) : null
  const mid = hasPair ? points[0].clone().lerp(points[1], 0.5) : null

  let breakdown = null
  if (hasPair) {
    const d = new THREE.Vector3().subVectors(points[1], points[0])
    const widthAxis = lengthAxis === 'x' ? 'z' : 'x'
    breakdown = {
      length: Math.abs(d[lengthAxis]), // CAD X: 선수-선미 방향
      width: Math.abs(d[widthAxis]), // CAD Y: 폭 방향
      vertical: Math.abs(d.y), // CAD Z: 수직 방향 (glTF Y-up 고정)
      radiusIfDiameter: dist / 2,
    }
  }

  return (
    <group userData={{ isTool: true }}>
      {points.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.35, 8, 8]} />
          <meshBasicMaterial color="#ffcc00" depthTest={false} />
        </mesh>
      ))}
      {hasPair && (
        <>
          <Line points={[points[0], points[1]]} color="#ffcc00" lineWidth={2} depthTest={false} />
          <Html position={mid} center>
            <div className="bg-black/85 text-yellow-300 text-xs px-2.5 py-2 rounded whitespace-nowrap pointer-events-none space-y-0.5">
              <p className="font-semibold text-sm">직선거리: {dist.toFixed(2)} m</p>
              <p className="text-gray-300">X(길이): {breakdown.length.toFixed(2)} m</p>
              <p className="text-gray-300">Y(폭): {breakdown.width.toFixed(2)} m</p>
              <p className="text-gray-300">Z(수직): {breakdown.vertical.toFixed(2)} m</p>
              <p className="text-gray-500 border-t border-gray-600 mt-1 pt-1">
                지름 가정 시 반지름: {breakdown.radiusIfDiameter.toFixed(2)} m
              </p>
            </div>
          </Html>
        </>
      )}
    </group>
  )
}
