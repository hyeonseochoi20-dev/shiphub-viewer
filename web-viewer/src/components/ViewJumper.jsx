import { useEffect, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

// 저장된 뷰로 카메라를 부드럽게 이동시키는 컨트롤러 (VIZZARDX의 SnapshotManager 개념 참고)
export default function ViewJumper({ target, controlsRef, onDone }) {
  const { camera } = useThree()
  const goal = useRef(null)

  useEffect(() => {
    if (target) {
      goal.current = {
        pos: new THREE.Vector3(...target.position),
        tgt: new THREE.Vector3(...target.target),
      }
    }
  }, [target])

  useFrame(() => {
    if (!goal.current || !controlsRef.current) return
    camera.position.lerp(goal.current.pos, 0.12)
    controlsRef.current.target.lerp(goal.current.tgt, 0.12)
    controlsRef.current.update()
    if (camera.position.distanceTo(goal.current.pos) < 0.05) {
      goal.current = null
      onDone?.()
    }
  })

  return null
}
