import React, { useRef, useState } from 'react'
import { useGLTF, useAnimations } from '@react-three/drei'

export default function ShipModel({ url }) {
  const meshRef = useRef()
  const [loaded, setLoaded] = useState(false)

  // glTF 로드
  const { scene, animations } = useGLTF(url)
  useAnimations(animations, meshRef)

  return (
    <group ref={meshRef}>
      <primitive
        object={scene}
        onAfterRender={() => setLoaded(true)}
      />

      {/* 로딩 인디케이터 */}
      {!loaded && (
        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="gray" wireframe />
        </mesh>
      )}
    </group>
  )
}