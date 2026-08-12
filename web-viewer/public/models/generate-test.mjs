// 테스트용 간단 배 모델 생성 (hull/deck/superstructure = 각 8정점 박스)
import { writeFileSync } from 'fs';
import { Buffer } from 'buffer';

// 8정점 박스: [FBL, FBR, FTR, FTL, BBL, BBR, BTR, BTL]
function box(hx, hy, hz) {
  return new Float32Array([
    -hx, -hy, -hz,  hx, -hy, -hz,  hx, hy, -hz,  -hx, hy, -hz,
    -hx, -hy,  hz,  hx, -hy,  hz,  hx, hy,  hz,  -hx, hy,  hz,
  ]);
}

const hullVertices = box(20, 2, 5);
const deckVertices = box(25, 0.5, 8);
const superVertices = box(8, 7, 3);

const vertices = new Float32Array([...hullVertices, ...deckVertices, ...superVertices]);

// 색상 (Unsigned Byte VEC4, gltf accessor와 일치)
function fillColor(r, g, b, a) {
  return Array(8).fill([r, g, b, a]).flat();
}
const colors = new Uint8Array([
  ...fillColor(51, 153, 204, 255),  // 청색 - Hull
  ...fillColor(128, 128, 128, 255), // 회색 - Deck
  ...fillColor(26, 26, 26, 255),    // 검정 - Superstructure
]);

// 박스 표준 인덱스 (6면 x 2삼각형 x 3 = 36), 메시마다 로컬 0~7 기준이라 동일 패턴 재사용
const boxIndices = [
  0, 1, 2, 0, 2, 3, // front
  4, 5, 6, 4, 6, 7, // back
  0, 1, 4, 1, 5, 4, // bottom
  2, 3, 6, 3, 7, 6, // top
  0, 3, 4, 3, 7, 4, // left
  1, 2, 5, 2, 6, 5, // right
];
const indices = new Uint16Array([...boxIndices, ...boxIndices, ...boxIndices]);

const buffer = Buffer.concat([
  Buffer.from(vertices.buffer),
  Buffer.from(colors.buffer),
  Buffer.from(indices.buffer),
]);

writeFileSync('./public/models/ship_sample.bin', buffer);
console.log(`Test model generated: ship_sample.bin (${buffer.length} bytes)`);
