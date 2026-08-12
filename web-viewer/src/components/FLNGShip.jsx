import React, { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'

// 선체 종방향 프로파일 (선미 x=-45 ~ 선수 x=+45)
const STERN_X = -45
const BOW_X = 45
const KEEL_Y = -8
const WATERLINE_Y = -5.5 // 만재흘수선 근사치 (도장 경계)

function smoothstep(edge0, edge1, x) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)))
  return t * t * (3 - 2 * t)
}

// 갑판 시어라인 (선수/선미 쪽으로 살짝 치솟는 곡선)
function deckY(x) {
  if (x < -30) return 1.5 * (1 - smoothstep(STERN_X, -30, x))
  if (x > 10) return 3 * smoothstep(10, BOW_X, x)
  return 0
}

// 하프빔(폭의 절반) 곡선: 선미 트랜섬 -> 평행 중앙부 -> 선수 뾰족
function halfBeam(x) {
  const MAX_B = 10
  if (x < -30) return MAX_B - 4 * (1 - smoothstep(STERN_X, -30, x))
  if (x > 10) return MAX_B * Math.pow(1 - smoothstep(10, BOW_X, x), 1.4)
  return MAX_B
}

const N_STATIONS = 36
const N_THETA = 6
const SHAPE_P = 0.85

const HULL_ABOVE = new THREE.Color('#1e3c64') // 남색 (흘수선 위)
const HULL_BELOW = new THREE.Color('#7a1f18') // 적색 안티파울링 (흘수선 아래)

function buildHullGeometry() {
  const positions = []
  const colors = []
  const indices = []
  const pointsPerStation = (N_THETA + 1) * 2 - 1

  const xs = []
  for (let i = 0; i < N_STATIONS; i++) {
    const t = i / (N_STATIONS - 1)
    xs.push(STERN_X + t * (BOW_X - STERN_X))
  }

  const pushRing = (x) => {
    const b = halfBeam(x)
    const dTop = deckY(x)
    const depth = dTop - KEEL_Y
    const ring = []
    for (let k = N_THETA; k >= 0; k--) ring.push(k)
    for (let k = 1; k <= N_THETA; k++) ring.push(-k)
    for (const kk of ring) {
      const k = Math.abs(kk)
      const theta = (k / N_THETA) * (Math.PI / 2)
      const y = KEEL_Y + depth * Math.pow(1 - Math.cos(theta), SHAPE_P)
      const z = Math.sign(kk === 0 ? 1 : kk) * b * Math.pow(Math.sin(theta), SHAPE_P)
      positions.push(x, y, z)
      const c = y < WATERLINE_Y ? HULL_BELOW : HULL_ABOVE
      colors.push(c.r, c.g, c.b)
    }
  }

  for (let i = 0; i < N_STATIONS; i++) pushRing(xs[i])

  for (let i = 0; i < N_STATIONS - 1; i++) {
    for (let k = 0; k < pointsPerStation - 1; k++) {
      const a = i * pointsPerStation + k
      const b = i * pointsPerStation + k + 1
      const c = (i + 1) * pointsPerStation + k + 1
      const d = (i + 1) * pointsPerStation + k
      indices.push(a, b, c, a, c, d)
    }
  }

  // 선미 트랜섬 캡
  {
    const base = positions.length / 3
    let cx = 0, cy = 0, cz = 0
    for (let k = 0; k < pointsPerStation; k++) {
      cx += positions[k * 3]; cy += positions[k * 3 + 1]; cz += positions[k * 3 + 2]
    }
    positions.push(cx / pointsPerStation, cy / pointsPerStation, cz / pointsPerStation)
    colors.push(HULL_ABOVE.r, HULL_ABOVE.g, HULL_ABOVE.b)
    for (let k = 0; k < pointsPerStation - 1; k++) indices.push(base, k + 1, k)
  }

  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
  geo.setIndex(indices)
  geo.computeVertexNormals()
  return geo
}

function buildDeckGeometry() {
  const positions = []
  const indices = []
  const N = 60
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1)
    const x = STERN_X + t * (BOW_X - STERN_X)
    const b = halfBeam(x)
    const y = deckY(x)
    positions.push(x, y, -b, x, y, b)
  }
  for (let i = 0; i < N - 1; i++) {
    const a = i * 2, bI = i * 2 + 1, c = (i + 1) * 2 + 1, d = (i + 1) * 2
    indices.push(a, bI, c, a, c, d)
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geo.setIndex(indices)
  geo.computeVertexNormals()
  return geo
}

// ---- 상부 구조물 서브 컴포넌트 ----

function PipeRack({ x1, x2, y, z = 0 }) {
  const midX = (x1 + x2) / 2
  const len = Math.abs(x2 - x1)
  return (
    <group>
      <mesh position={[midX, y, z]} castShadow>
        <boxGeometry args={[len, 0.8, 6]} />
        <meshStandardMaterial color="#5a5f66" roughness={0.6} metalness={0.4} />
      </mesh>
      {[x1, x2].map((x, i) => (
        <mesh key={i} position={[x, y - 2, z]} castShadow>
          <cylinderGeometry args={[0.4, 0.4, 4, 6]} />
          <meshStandardMaterial color="#5a5f66" roughness={0.6} metalness={0.4} />
        </mesh>
      ))}
    </group>
  )
}

function ProcessModule({ x, y, w, d, h }) {
  return (
    <group position={[x, y + h / 2, 0]}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color="#d6942a" roughness={0.6} metalness={0.3} />
      </mesh>
      {/* 배관/철골 디테일 */}
      <mesh position={[0, h / 2 + 0.6, 0]} castShadow>
        <boxGeometry args={[w * 0.9, 0.6, d * 0.5]} />
        <meshStandardMaterial color="#8a8f96" roughness={0.5} metalness={0.5} />
      </mesh>
    </group>
  )
}

function Turret({ x, y }) {
  return (
    <group position={[x, y, 0]}>
      <mesh position={[0, 2, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[5, 5.5, 4, 16]} />
        <meshStandardMaterial color="#2a2c30" roughness={0.5} metalness={0.6} />
      </mesh>
      <mesh position={[0, 6, 0]} castShadow>
        <cylinderGeometry args={[2.6, 3.2, 5, 16]} />
        <meshStandardMaterial color="#3a3d42" roughness={0.5} metalness={0.6} />
      </mesh>
      <mesh position={[0, 10.5, 0]} castShadow>
        <cylinderGeometry args={[1, 1, 5, 8]} />
        <meshStandardMaterial color="#3a3d42" roughness={0.5} metalness={0.6} />
      </mesh>
    </group>
  )
}

function FlareTower({ x, y, z }) {
  return (
    <group position={[x, y, z]}>
      <mesh position={[0, 15, 0]} castShadow>
        <cylinderGeometry args={[1, 1.2, 30, 8]} />
        <meshStandardMaterial color="#b4281e" roughness={0.5} metalness={0.4} />
      </mesh>
      <mesh position={[0, 31, 0]} castShadow>
        <coneGeometry args={[1.3, 2, 8]} />
        <meshStandardMaterial color="#2a2c30" roughness={0.4} metalness={0.5} />
      </mesh>
      {/* 지지 가대 (경사 브레이스) */}
      {[[-1, 1], [1, -1]].map(([sx, sz], i) => (
        <mesh
          key={i}
          position={[-4 * sx, 7.5, -3 * sz]}
          rotation={[0, 0, Math.atan2(4, 15) * sx]}
          castShadow
        >
          <cylinderGeometry args={[0.35, 0.35, 16, 6]} />
          <meshStandardMaterial color="#5a5f66" roughness={0.6} metalness={0.5} />
        </mesh>
      ))}
    </group>
  )
}

function Accommodation({ x, y }) {
  const tiers = [
    { w: 11, h: 8, d: 13, dy: 4 },
    { w: 9, h: 6, d: 11, dy: 3 },
    { w: 7, h: 4, d: 9, dy: 2 },
  ]
  let curY = y
  return (
    <group position={[x, 0, 0]}>
      {tiers.map((t, i) => {
        const cy = curY + t.h / 2
        curY += t.h
        return (
          <group key={i}>
            <mesh position={[0, cy, 0]} castShadow receiveShadow>
              <boxGeometry args={[t.w, t.h, t.d]} />
              <meshStandardMaterial color="#e6e6eb" roughness={0.5} metalness={0.1} />
            </mesh>
            {/* 창문 밴드 */}
            <mesh position={[0, cy, t.d / 2 + 0.05]} castShadow>
              <boxGeometry args={[t.w * 0.85, t.h * 0.25, 0.1]} />
              <meshStandardMaterial color="#1a2430" roughness={0.3} metalness={0.2} />
            </mesh>
          </group>
        )
      })}
      {/* 헬리데크 */}
      <group position={[0, curY + 0.3, 0]}>
        <mesh castShadow receiveShadow>
          <cylinderGeometry args={[6.2, 6.2, 0.6, 24]} />
          <meshStandardMaterial color="#3a3d42" roughness={0.7} metalness={0.2} />
        </mesh>
        <mesh position={[0, 0.35, 0]}>
          <torusGeometry args={[5.3, 0.18, 8, 24]} />
          <meshStandardMaterial color="#d6b52a" roughness={0.5} metalness={0.2} />
        </mesh>
      </group>
    </group>
  )
}

function Crane({ x, z, side }) {
  return (
    <group position={[x, deckY(x), z]}>
      <mesh position={[0, 4, 0]} castShadow>
        <cylinderGeometry args={[1.1, 1.3, 8, 10]} />
        <meshStandardMaterial color="#d6942a" roughness={0.5} metalness={0.4} />
      </mesh>
      <mesh position={[side * 5, 8.5, 0]} rotation={[0, 0, side * -0.5]} castShadow>
        <boxGeometry args={[11, 1, 1]} />
        <meshStandardMaterial color="#d6942a" roughness={0.5} metalness={0.4} />
      </mesh>
    </group>
  )
}

export default function FLNGShip() {
  const groupRef = useRef()
  const hullGeo = useMemo(() => buildHullGeometry(), [])
  const deckGeo = useMemo(() => buildDeckGeometry(), [])

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.08) * 0.15
    }
  })

  const modules = [
    { x: -26, w: 9, d: 14, h: 6 },
    { x: -15, w: 10, d: 15, h: 7 },
    { x: -3, w: 10, d: 15, h: 7 },
    { x: 9, w: 9, d: 14, h: 6.5 },
  ]
  const railY = (x) => deckY(x) + modules[0].h + 4

  return (
    <group ref={groupRef}>
      <mesh geometry={hullGeo} castShadow receiveShadow>
        <meshStandardMaterial vertexColors roughness={0.4} metalness={0.55} />
      </mesh>
      <mesh geometry={deckGeo} castShadow receiveShadow>
        <meshStandardMaterial color="#8c8c94" roughness={0.7} metalness={0.2} side={THREE.DoubleSide} />
      </mesh>

      {/* 벌브 바우 */}
      <mesh position={[BOW_X - 1.5, KEEL_Y + 2, 0]} castShadow>
        <sphereGeometry args={[2.4, 12, 10]} />
        <meshStandardMaterial color={HULL_BELOW.getStyle()} roughness={0.4} metalness={0.55} />
      </mesh>

      {/* LNG 공정 모듈 트레인 */}
      {modules.map((m, i) => (
        <ProcessModule key={i} x={m.x} y={deckY(m.x)} w={m.w} d={m.d} h={m.h} />
      ))}
      {modules.slice(0, -1).map((m, i) => (
        <PipeRack key={i} x1={m.x + m.w / 2} x2={modules[i + 1].x - modules[i + 1].w / 2} y={railY(m.x)} />
      ))}

      {/* 터렛 계류장치 (선수측, 선폭이 충분히 남아있는 지점) */}
      <Turret x={15} y={deckY(15)} />

      {/* 플레어 타워 (선수, 선체 폭 안쪽으로 오프셋) */}
      <FlareTower x={25} y={deckY(25)} z={3} />

      {/* 거주구 + 헬리데크 (선미측) */}
      <Accommodation x={-38} y={deckY(-38)} />

      {/* 크레인 2기 (좌/우현) */}
      <Crane x={-4} z={-9.5} side={-1} />
      <Crane x={-4} z={9.5} side={1} />
    </group>
  )
}
