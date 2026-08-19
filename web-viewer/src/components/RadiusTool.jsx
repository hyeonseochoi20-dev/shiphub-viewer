import React, { useEffect, useRef, useState } from 'react'
import { attachPickHandler } from './clickIntent'
import { useThree } from '@react-three/fiber'
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

// 3점을 지나는 원의 중심/반지름/법선을 계산 (외접원, 3D 공간)
function circumcircle3D(p0, p1, p2) {
  const a = new THREE.Vector3().subVectors(p1, p0)
  const b = new THREE.Vector3().subVectors(p2, p0)
  const axb = new THREE.Vector3().crossVectors(a, b)
  const axbLenSq = axb.lengthSq()
  if (axbLenSq < 1e-8) return null // 세 점이 거의 일직선

  const term1 = new THREE.Vector3().crossVectors(axb, a).multiplyScalar(b.lengthSq())
  const term2 = new THREE.Vector3().crossVectors(b, axb).multiplyScalar(a.lengthSq())
  const center = new THREE.Vector3().addVectors(term1, term2).divideScalar(2 * axbLenSq).add(p0)
  const radius = center.distanceTo(p0)
  const normal = axb.clone().normalize()
  return { center, radius, normal }
}

function buildCirclePoints(center, radius, normal, refPoint, segments = 64) {
  const u = new THREE.Vector3().subVectors(refPoint, center).normalize()
  const v = new THREE.Vector3().crossVectors(normal, u).normalize()
  const pts = []
  for (let i = 0; i <= segments; i++) {
    const theta = (i / segments) * Math.PI * 2
    const p = new THREE.Vector3()
      .addScaledVector(u, radius * Math.cos(theta))
      .addScaledVector(v, radius * Math.sin(theta))
      .add(center)
    pts.push(p)
  }
  return pts
}

// 원통/반경 측정 도구 - 원주 위 3점 클릭 -> 외접원 계산 -> 중심/반지름/지름/원주 표시
// snapRef가 있으면 SnapEngine이 실시간으로 판정한 꼭지점/모서리/곡면 스냅 좌표를 우선 사용
export default function RadiusTool({ active, snapRef }) {
  const { gl, camera, scene } = useThree()
  const [points, setPoints] = useState([])
  const raycaster = useRef(new THREE.Raycaster())

  useEffect(() => {
    if (!active) {
      setPoints([])
      return
    }
    const onPick = (e) => {

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
          return next.length > 3 ? [hitPoint.clone()] : next
        })
      }
    }
    return attachPickHandler(gl.domElement, onPick)
  }, [active, gl, camera, scene, snapRef])

  if (!active || points.length < 1) return null

  const circle = points.length === 3 ? circumcircle3D(points[0], points[1], points[2]) : null
  const circlePts = circle ? buildCirclePoints(circle.center, circle.radius, circle.normal, points[0]) : null

  return (
    <group userData={{ isTool: true }}>
      {points.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.35, 8, 8]} />
          <meshBasicMaterial color="#37e0c4" depthTest={false} />
        </mesh>
      ))}
      {circle && (
        <>
          <Line points={circlePts} color="#37e0c4" lineWidth={2} depthTest={false} />
          <mesh position={circle.center}>
            <sphereGeometry args={[0.25, 8, 8]} />
            <meshBasicMaterial color="#ffffff" depthTest={false} />
          </mesh>
          <Html position={circle.center} center>
            <div className="bg-black/85 text-cyan-300 text-xs px-2.5 py-2 rounded whitespace-nowrap pointer-events-none space-y-0.5">
              <p className="font-semibold text-sm">반지름: {circle.radius.toFixed(2)} m</p>
              <p className="text-gray-300">지름: {(circle.radius * 2).toFixed(2)} m</p>
              <p className="text-gray-300">원주: {(2 * Math.PI * circle.radius).toFixed(2)} m</p>
            </div>
          </Html>
        </>
      )}
    </group>
  )
}
