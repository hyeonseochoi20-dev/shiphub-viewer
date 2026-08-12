import { useEffect, useMemo, useRef, useState } from 'react'
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

// CAD 라벨(X=길이,Y=폭,Z=수직) -> 실제 Three.js 축 매핑 (lengthAxis: 씬에서 실제 길이인 Three 축, 'x' 또는 'z')
function resolveAxis(cadAxis, lengthAxis) {
  const widthAxis = lengthAxis === 'x' ? 'z' : 'x'
  if (cadAxis === 'x') return lengthAxis // 길이
  if (cadAxis === 'y') return widthAxis // 폭
  return 'y' // 수직 (항상 Three Y)
}

function normalForAxis(threeAxisKey, flip = false) {
  const n = new THREE.Vector3()
  n[threeAxisKey] = flip ? 1 : -1
  return n
}

// 단면(클리핑 플레인) 도구
// 주의: 렌더러 전역(gl.clippingPlanes)이 아니라 모델 메시의 머티리얼에만 개별 적용해서
// ShipGrid/측정마커/축헬퍼 등 도구성 오브젝트는 잘리지 않도록 한다.
// 뷰포트 안에 반투명 절단면 + 드래그 핸들을 표시해서 슬라이더 없이도 배 위에서 직접 밀고 당길 수 있게 한다.
export default function SectionPlane({ enabled, axis = 'x', position = 0, flipped = false, onPositionChange, onDraggingChange }) {
  const { gl, scene, camera } = useThree()
  const [lengthAxis, setLengthAxis] = useState('x')
  const [bounds, setBounds] = useState(null)
  const lockedRef = useRef(false)
  const patchedRef = useRef([])
  const draggingRef = useRef(false)

  useEffect(() => {
    gl.localClippingEnabled = true
  }, [gl])

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
      const sizeX = box.max.x - box.min.x
      const sizeZ = box.max.z - box.min.z
      setLengthAxis(sizeX >= sizeZ ? 'x' : 'z')
      setBounds(box)
    }
  })

  const threeAxisKey = resolveAxis(axis, lengthAxis)

  // 클리핑 적용 (모델 메시에만)
  useEffect(() => {
    const clear = () => {
      patchedRef.current.forEach(({ material }) => {
        material.clippingPlanes = null
      })
      patchedRef.current = []
    }
    clear()

    if (!enabled) return undefined

    // 법선을 반전하면 같은 위치를 지나는 평면을 유지하기 위해 constant 부호도 함께 뒤집어야 한다
    // (THREE.Plane: normal·point + constant = 0 위에 놓인 평면).
    const plane = new THREE.Plane(normalForAxis(threeAxisKey, flipped), flipped ? -position : position)

    scene.traverse((obj) => {
      if (obj.isMesh && obj.material && !isToolObject(obj)) {
        const materials = Array.isArray(obj.material) ? obj.material : [obj.material]
        materials.forEach((m) => {
          m.clippingPlanes = [plane]
          patchedRef.current.push({ material: m })
        })
      }
    })

    return clear
  }, [enabled, threeAxisKey, position, flipped, scene])

  // 드래그: 핸들을 잡으면 축을 포함하고 카메라를 향하는 가상 평면에 레이캐스트해서 새 위치 계산
  useEffect(() => {
    if (!enabled) return undefined

    const raycaster = new THREE.Raycaster()
    const axisDir = new THREE.Vector3()
    axisDir[threeAxisKey] = 1

    const onMove = (e) => {
      if (!draggingRef.current) return
      const rect = gl.domElement.getBoundingClientRect()
      const ndc = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1
      )
      raycaster.setFromCamera(ndc, camera)

      const camDir = camera.getWorldDirection(new THREE.Vector3())
      const right = new THREE.Vector3().crossVectors(axisDir, camDir)
      if (right.lengthSq() < 1e-6) return
      right.normalize()
      const planeNormal = new THREE.Vector3().crossVectors(right, axisDir).normalize()

      const anchor = new THREE.Vector3()
      anchor[threeAxisKey] = position
      const dragPlane = new THREE.Plane().setFromNormalAndCoplanarPoint(planeNormal, anchor)

      const hit = new THREE.Vector3()
      if (raycaster.ray.intersectPlane(dragPlane, hit)) {
        onPositionChange?.(Math.round(hit[threeAxisKey] * 10) / 10)
      }
    }
    const onUp = () => {
      if (draggingRef.current) {
        draggingRef.current = false
        onDraggingChange?.(false)
      }
    }

    gl.domElement.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      gl.domElement.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [enabled, threeAxisKey, position, gl, camera, onPositionChange, onDraggingChange])

  const { planeSize, planeCenter, planeQuat } = useMemo(() => {
    if (!bounds) return {}
    const center = bounds.getCenter(new THREE.Vector3())
    center[threeAxisKey] = position

    const dims = { x: bounds.max.x - bounds.min.x, y: bounds.max.y - bounds.min.y, z: bounds.max.z - bounds.min.z }
    const otherKeys = ['x', 'y', 'z'].filter((k) => k !== threeAxisKey)
    const size = [dims[otherKeys[0]] * 1.15, dims[otherKeys[1]] * 1.15]

    const normal = normalForAxis(threeAxisKey).multiplyScalar(-1)
    const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal)

    return { planeSize: size, planeCenter: center, planeQuat: quat }
  }, [bounds, threeAxisKey, position])

  if (!enabled || !bounds) return null

  return (
    <group userData={{ isTool: true }}>
      {/* 반투명 절단면 시각화 */}
      <mesh position={planeCenter} quaternion={planeQuat}>
        <planeGeometry args={planeSize} />
        <meshBasicMaterial color={flipped ? '#f472b6' : '#22d3ee'} transparent opacity={0.12} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>

      {/* 드래그 핸들 - 단방향 화살표 (작고 얇게) */}
      {(() => {
        const scale = Math.max(planeSize?.[0], planeSize?.[1]) * 0.032 || 1
        const axisDir = new THREE.Vector3()
        axisDir[threeAxisKey] = 1
        const coneQuat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), axisDir)

        const coneHeight = scale * 0.8
        const shaftLen = scale * 2.2
        const shaftCenter = axisDir.clone().multiplyScalar(shaftLen / 2)
        const coneTip = axisDir.clone().multiplyScalar(shaftLen + coneHeight / 2)

        return (
          <group
            position={planeCenter}
            onPointerDown={(e) => {
              e.stopPropagation()
              draggingRef.current = true
              onDraggingChange?.(true)
            }}
            onPointerOver={(e) => {
              e.stopPropagation()
              document.body.style.cursor = 'grab'
            }}
            onPointerOut={() => {
              document.body.style.cursor = 'auto'
            }}
          >
            {/* 투명 히트박스 - 화살표는 작아도 클릭/드래그는 넉넉하게 잡히도록 */}
            <mesh visible={false} position={shaftCenter}>
              <sphereGeometry args={[scale * 1.6, 8, 8]} />
              <meshBasicMaterial transparent opacity={0} depthTest={false} />
            </mesh>
            {/* 축 샤프트 */}
            <mesh position={shaftCenter} quaternion={coneQuat}>
              <cylinderGeometry args={[scale * 0.08, scale * 0.08, shaftLen, 8]} />
              <meshBasicMaterial color="#fbbf24" depthTest={false} />
            </mesh>
            {/* 화살촉 */}
            <mesh position={coneTip} quaternion={coneQuat}>
              <coneGeometry args={[scale * 0.32, coneHeight, 10]} />
              <meshBasicMaterial color="#fde68a" depthTest={false} />
            </mesh>
          </group>
        )
      })()}
      <Html position={planeCenter} center>
        <div className={`px-1.5 py-0.5 rounded text-[10px] font-semibold bg-black/80 pointer-events-none whitespace-nowrap -translate-y-6 ${flipped ? 'text-pink-300' : 'text-cyan-300'}`}>
          드래그해서 이동 · {position.toFixed(1)}{flipped ? ' · 반전됨' : ''}
        </div>
      </Html>
    </group>
  )
}
