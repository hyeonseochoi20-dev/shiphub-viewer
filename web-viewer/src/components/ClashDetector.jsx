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

// 간섭검사 - 씬 내 메시들의 바운딩박스 교차 여부를 검사하고 충돌 부위를 강조
export default function ClashDetector({ active, onResults }) {
  const { scene } = useThree()
  const highlighted = useRef([])

  useEffect(() => {
    if (!active) {
      restore()
      onResults?.([])
      return
    }

    const meshes = []
    scene.traverse((obj) => {
      if (obj.isMesh && obj.geometry && !isToolObject(obj)) meshes.push(obj)
    })

    const boxes = meshes.map((m) => new THREE.Box3().setFromObject(m))
    const clashes = []
    const clashMeshes = new Set()

    for (let i = 0; i < meshes.length; i++) {
      for (let j = i + 1; j < meshes.length; j++) {
        if (boxes[i].intersectsBox(boxes[j])) {
          clashes.push({
            a: meshes[i].name || `part_${i}`,
            b: meshes[j].name || `part_${j}`,
          })
          clashMeshes.add(meshes[i])
          clashMeshes.add(meshes[j])
        }
      }
    }

    highlighted.current = [...clashMeshes].map((mesh) => ({
      mesh,
      original: mesh.material?.emissive ? mesh.material.emissive.clone() : null,
    }))
    highlighted.current.forEach(({ mesh }) => {
      if (mesh.material?.emissive) mesh.material.emissive.set('#ff2222')
    })

    onResults?.(clashes)

    return () => restore()
  }, [active, scene])

  function restore() {
    highlighted.current.forEach(({ mesh, original }) => {
      if (original && mesh.material?.emissive) mesh.material.emissive.copy(original)
    })
    highlighted.current = []
  }

  return null
}
