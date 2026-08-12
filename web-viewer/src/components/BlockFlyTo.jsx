import { useEffect, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

function isToolObject(obj) {
  let p = obj
  while (p) {
    if (p.userData?.isTool) return true
    p = p.parent
  }
  return false
}

// dim_process_stage 순서 (schema.sql 기준) - 공정이 진행될수록 선체 내 위치가 대략 이동한다는
// 가정의 휴리스틱. 실제 블록 좌표가 DB에 없으므로(메타데이터만 있음) 이 순서를 뷰어 안에서
// "그럴싸한 위치"로 매핑하는 용도로만 쓴다 - 실측 좌표가 아님을 명시.
const STAGE_ORDER = { '절단': 0, '조립': 1, '탑재': 2, '의장': 3, '도장': 4, '시운전': 5 }

function hash01(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0
  return (h % 9973) / 9973
}

// AI 쿼리 패널에서 블록을 고르면, 그 블록의 메타데이터(공정단계 등)를 현재 로드된 모델의
// 실제 바운딩박스 안 위치로 휴리스틱 매핑해서 카메라를 부드럽게 이동시킨다.
// (ViewJumper와 동일한 lerp 메커니즘을 재사용 - onResolve로 target을 넘기면 App.jsx가 jumpTarget에 세팅)
export default function BlockFlyTo({ requestBlock, onResolve }) {
  const { scene } = useThree()
  const boundsRef = useRef(null)

  useFrame(() => {
    if (boundsRef.current) return
    const box = new THREE.Box3()
    let found = false
    scene.traverse((obj) => {
      if (obj.isMesh && obj.geometry && !isToolObject(obj)) {
        box.expandByObject(obj)
        found = true
      }
    })
    if (found) boundsRef.current = box
  })

  useEffect(() => {
    if (!requestBlock || !boundsRef.current) return
    const bounds = boundsRef.current
    const sizeX = bounds.max.x - bounds.min.x
    const sizeZ = bounds.max.z - bounds.min.z
    const lengthAxis = sizeX >= sizeZ ? 'x' : 'z'
    const widthAxis = lengthAxis === 'x' ? 'z' : 'x'

    const key = String(requestBlock.block_name ?? requestBlock.block_id ?? '')
    const stageIdx = STAGE_ORDER[requestBlock.process_stage]
    const tLength = stageIdx !== undefined ? (stageIdx + 0.5) / 6 : hash01(key + 'l')
    const tWidth = hash01(key + 'w')
    const tHeight = 0.3 + hash01(key + 'h') * 0.6 // 바닥/천장 끝단은 피해서 시야가 잘 나오는 구간만 사용

    const point = new THREE.Vector3()
    point[lengthAxis] = bounds.min[lengthAxis] + tLength * (bounds.max[lengthAxis] - bounds.min[lengthAxis])
    point[widthAxis] = bounds.min[widthAxis] + tWidth * (bounds.max[widthAxis] - bounds.min[widthAxis])
    point.y = bounds.min.y + tHeight * (bounds.max.y - bounds.min.y)

    const modelDiag = bounds.getSize(new THREE.Vector3()).length()
    const viewDist = Math.max(modelDiag * 0.12, 4)
    const camPos = point.clone().add(new THREE.Vector3(viewDist * 0.7, viewDist * 0.55, viewDist * 0.7))

    onResolve({ position: camPos.toArray(), target: point.toArray() })
  }, [requestBlock, onResolve])

  return null
}
