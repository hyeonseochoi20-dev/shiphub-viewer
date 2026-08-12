import React, { useEffect, useRef, useState } from 'react'
import { useThree } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'

function isAncestorTool(obj) {
  let p = obj
  while (p) {
    if (p.userData?.isTool) return true
    p = p.parent
  }
  return false
}

const SNAP_COLOR = { vertex: '#ff3355', edge: '#ffaa00', arc: '#33ccff', face: '#88ff66' }
const SNAP_LABEL = { vertex: '꼭지점', edge: '모서리', arc: '곡면 (아크)', face: '면' }

// 인접 정점 노멀 차이로 평면(edge/face) vs 곡면(arc)을 판별 (B-rep 없이 삼각형 메시만으로 근사)
function isCurvedAt(geometry, face) {
  const normalAttr = geometry.attributes.normal
  if (!normalAttr) return false
  const na = new THREE.Vector3().fromBufferAttribute(normalAttr, face.a)
  const nb = new THREE.Vector3().fromBufferAttribute(normalAttr, face.b)
  const nc = new THREE.Vector3().fromBufferAttribute(normalAttr, face.c)
  const maxDiff = Math.max(na.angleTo(nb), nb.angleTo(nc), nc.angleTo(na))
  return maxDiff > THREE.MathUtils.degToRad(8)
}

function computeSnap(hit, camera) {
  const { object, point, face } = hit
  if (!face) return { type: 'face', point: point.clone(), object }

  const posAttr = object.geometry.attributes.position
  const va = new THREE.Vector3().fromBufferAttribute(posAttr, face.a).applyMatrix4(object.matrixWorld)
  const vb = new THREE.Vector3().fromBufferAttribute(posAttr, face.b).applyMatrix4(object.matrixWorld)
  const vc = new THREE.Vector3().fromBufferAttribute(posAttr, face.c).applyMatrix4(object.matrixWorld)

  const distToCam = camera.position.distanceTo(point)
  const vertexThreshold = distToCam * 0.02
  const edgeThreshold = distToCam * 0.012

  let closestVertex = va
  let closestVertexDist = va.distanceTo(point)
  ;[vb, vc].forEach((v) => {
    const d = v.distanceTo(point)
    if (d < closestVertexDist) {
      closestVertexDist = d
      closestVertex = v
    }
  })

  if (closestVertexDist < vertexThreshold) {
    return { type: 'vertex', point: closestVertex.clone(), object }
  }

  const edges = [
    [va, vb],
    [vb, vc],
    [vc, va],
  ]
  let closestEdgePoint = null
  let closestEdgeDist = Infinity
  edges.forEach(([p1, p2]) => {
    const line = new THREE.Line3(p1, p2)
    const closest = new THREE.Vector3()
    line.closestPointToPoint(point, true, closest)
    const d = closest.distanceTo(point)
    if (d < closestEdgeDist) {
      closestEdgeDist = d
      closestEdgePoint = closest
    }
  })

  const curved = isCurvedAt(object.geometry, face)

  if (closestEdgeDist < edgeThreshold) {
    return { type: curved ? 'arc' : 'edge', point: closestEdgePoint.clone(), object }
  }
  return { type: curved ? 'arc' : 'face', point: point.clone(), object }
}

// 마우스 오버 위치의 형상 요소(꼭지점/모서리/면/곡면)를 실시간 스냅 판정해서 표시
// snapRef.current에 최신 스냅 결과를 저장 -> 측정/반경 도구가 클릭 시 이 값을 정밀 좌표로 사용
export default function SnapEngine({ active, snapRef }) {
  const { gl, camera, scene } = useThree()
  const [snap, setSnap] = useState(null)
  const raycaster = useRef(new THREE.Raycaster())

  useEffect(() => {
    if (!active) {
      setSnap(null)
      if (snapRef) snapRef.current = null
      return
    }

    const onMove = (e) => {
      const rect = gl.domElement.getBoundingClientRect()
      const ndc = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1
      )
      raycaster.current.setFromCamera(ndc, camera)
      const hits = raycaster.current.intersectObjects(scene.children, true)
      const hit = hits.find((h) => !isAncestorTool(h.object))
      const result = hit ? computeSnap(hit, camera) : null
      setSnap(result)
      if (snapRef) snapRef.current = result
    }

    gl.domElement.addEventListener('pointermove', onMove)
    return () => gl.domElement.removeEventListener('pointermove', onMove)
  }, [active, gl, camera, scene, snapRef])

  if (!active || !snap) return null

  return (
    <group userData={{ isTool: true }}>
      <mesh position={snap.point}>
        <sphereGeometry args={[snap.type === 'vertex' ? 0.3 : 0.2, 10, 10]} />
        <meshBasicMaterial color={SNAP_COLOR[snap.type]} depthTest={false} transparent opacity={0.9} />
      </mesh>
      <Html position={snap.point} center>
        <div
          className="px-1.5 py-0.5 rounded text-[10px] font-semibold pointer-events-none whitespace-nowrap"
          style={{ background: 'rgba(0,0,0,0.85)', color: SNAP_COLOR[snap.type], transform: 'translateY(-18px)' }}
        >
          {SNAP_LABEL[snap.type]}
        </div>
      </Html>
    </group>
  )
}
