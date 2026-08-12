import { useEffect, useRef } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'

function isToolObject(obj) {
  let p = obj
  while (p) {
    if (p.userData?.isTool) return true
    p = p.parent
  }
  return false
}

// 수직(CAD Z = Three Y) 기준 표면 각도에 따라 색을 입히는 구배분석 오버레이
// 초록: 수직에 가까움(구배 충분, 안전) / 빨강: 수평에 가까움(구배 부족 - 벤딩/탈형 시 주의)
function angleToColor(angleDeg) {
  const t = THREE.MathUtils.clamp(angleDeg / 90, 0, 1) // 0=수평(위험) 1=수직(안전)
  const hue = t * 0.33 // 0(red) -> 0.33(green)
  const c = new THREE.Color()
  c.setHSL(hue, 0.85, 0.5)
  return c
}

export default function DraftAnalysis({ active }) {
  const { scene } = useThree()
  const patched = useRef([])

  useEffect(() => {
    if (!active) {
      restore()
      return
    }

    const targets = []
    scene.traverse((obj) => {
      if (obj.isMesh && obj.geometry && !isToolObject(obj)) targets.push(obj)
    })

    targets.forEach((mesh) => {
      const geo = mesh.geometry
      if (!geo.attributes.normal) geo.computeVertexNormals()

      const normalAttr = geo.attributes.normal
      const colors = new Float32Array(normalAttr.count * 3)
      const n = new THREE.Vector3()
      const worldQuat = mesh.getWorldQuaternion(new THREE.Quaternion())

      for (let i = 0; i < normalAttr.count; i++) {
        n.fromBufferAttribute(normalAttr, i).applyQuaternion(worldQuat).normalize()
        const angleDeg = THREE.MathUtils.radToDeg(Math.acos(THREE.MathUtils.clamp(Math.abs(n.y), -1, 1)))
        const color = angleToColor(angleDeg)
        colors[i * 3] = color.r
        colors[i * 3 + 1] = color.g
        colors[i * 3 + 2] = color.b
      }

      const originalColorAttr = geo.attributes.color
      geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))

      const originalMaterial = mesh.material
      mesh.material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6, metalness: 0.1 })

      patched.current.push({ mesh, originalMaterial, originalColorAttr })
    })

    return () => restore()
  }, [active, scene])

  function restore() {
    patched.current.forEach(({ mesh, originalMaterial, originalColorAttr }) => {
      mesh.material = originalMaterial
      if (originalColorAttr) {
        mesh.geometry.setAttribute('color', originalColorAttr)
      } else {
        mesh.geometry.deleteAttribute('color')
      }
    })
    patched.current = []
  }

  return null
}
