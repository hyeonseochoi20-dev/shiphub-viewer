// FLNG(부유식 LNG 생산설비) 형상 샘플 모델 생성 - gltf + bin 동시 생성
import { writeFileSync } from 'fs';
import { Buffer } from 'buffer';

// ---- 파츠 지오메트리 빌더 ----
// 박스: 중심(cx,cy,cz) 기준 half-extent(hx,hy,hz), 로컬 8정점 [FBL,FBR,FTR,FTL,BBL,BBR,BTR,BTL]
function box(hx, hy, hz) {
  const positions = [
    -hx, -hy, -hz,  hx, -hy, -hz,  hx, hy, -hz,  -hx, hy, -hz,
    -hx, -hy,  hz,  hx, -hy,  hz,  hx, hy,  hz,  -hx, hy,  hz,
  ];
  const indices = [
    0, 1, 2, 0, 2, 3, // front
    4, 5, 6, 4, 6, 7, // back
    0, 1, 4, 1, 5, 4, // bottom
    2, 3, 6, 3, 7, 6, // top
    0, 3, 4, 3, 7, 4, // left
    1, 2, 5, 2, 6, 5, // right
  ];
  return { positions, indices };
}

// 선수(뱃머리) 쐐기: base(x=0, 사각형) -> apex(x=length, 중심축 뾰족점)
function wedge(length, halfWidth, halfHeight) {
  const positions = [
    0, -halfHeight, -halfWidth, // 0 base bottom-left
    0, -halfHeight,  halfWidth, // 1 base bottom-right
    0,  halfHeight,  halfWidth, // 2 base top-right
    0,  halfHeight, -halfWidth, // 3 base top-left
    length, 0, 0,               // 4 apex
  ];
  const indices = [
    0, 1, 2, 0, 2, 3,       // base (stern-facing)
    0, 1, 4,                // bottom
    1, 2, 4,                // right
    2, 3, 4,                // top
    3, 0, 4,                // left
  ];
  return { positions, indices };
}

function rgba(r, g, b, a = 255) { return [r, g, b, a]; }

// ---- FLNG 파츠 구성 ----
const NAVY = rgba(30, 60, 100);
const GREY = rgba(140, 140, 148);
const PROCESS = rgba(214, 148, 40);   // LNG 상부 처리설비(주황)
const WHITE = rgba(230, 230, 235);    // 거주구
const RED = rgba(180, 40, 30);        // 플레어 타워

const parts = [
  { name: 'hull_main', geo: box(35, 3, 10), translation: [-10, -3, 0], color: NAVY },
  { name: 'hull_bow', geo: wedge(20, 10, 3), translation: [25, -3, 0], color: NAVY },
  { name: 'deck', geo: box(45.5, 0.3, 10.3), translation: [-9.5, 0.3, 0], color: GREY },
  { name: 'topside_module_1', geo: box(6, 3, 6), translation: [-18, 3.6, 0], color: PROCESS },
  { name: 'topside_module_2', geo: box(6, 3, 6), translation: [-1, 3.6, 0], color: PROCESS },
  { name: 'topside_module_3', geo: box(6, 3, 6), translation: [16, 3.6, 0], color: PROCESS },
  { name: 'accommodation', geo: box(5, 10, 6), translation: [-38, 10.6, 0], color: WHITE },
  { name: 'flare_tower', geo: box(1, 15, 1), translation: [30, 15.6, 8], color: RED },
];

// ---- 버퍼/버퍼뷰/접근자 조립 (오프셋은 전부 계산으로 산출) ----
const nodes = [];
const meshes = [];
const accessors = [];
const bufferViews = [];

const posChunks = [];
const colorChunks = [];
const idxChunks = [];
let posOffset = 0, colorOffset = 0, idxOffset = 0;

parts.forEach((part, i) => {
  const { positions, indices } = part.geo;
  const vertCount = positions.length / 3;

  const posArr = new Float32Array(positions);
  const colorArr = new Uint8Array(new Array(vertCount).fill(part.color).flat());
  const idxArr = new Uint16Array(indices);

  posChunks.push(Buffer.from(posArr.buffer));
  colorChunks.push(Buffer.from(colorArr.buffer));
  idxChunks.push(Buffer.from(idxArr.buffer));

  const xs = positions.filter((_, idx) => idx % 3 === 0);
  const ys = positions.filter((_, idx) => idx % 3 === 1);
  const zs = positions.filter((_, idx) => idx % 3 === 2);

  const posAccessorIdx = accessors.length;
  accessors.push({
    bufferView: i * 3 + 0, componentType: 5126, count: vertCount, type: 'VEC3',
    max: [Math.max(...xs), Math.max(...ys), Math.max(...zs)],
    min: [Math.min(...xs), Math.min(...ys), Math.min(...zs)],
  });
  const colorAccessorIdx = accessors.length;
  accessors.push({ bufferView: i * 3 + 1, componentType: 5121, normalized: true, count: vertCount, type: 'VEC4' });
  const idxAccessorIdx = accessors.length;
  accessors.push({ bufferView: i * 3 + 2, componentType: 5123, count: idxArr.length, type: 'SCALAR' });

  bufferViews.push({ buffer: 0, byteOffset: posOffset, byteLength: posArr.byteLength });
  bufferViews.push({ buffer: 0, byteOffset: colorOffset, byteLength: colorArr.byteLength });
  bufferViews.push({ buffer: 0, byteOffset: idxOffset, byteLength: idxArr.byteLength });

  posOffset += posArr.byteLength;
  colorOffset += colorArr.byteLength;
  idxOffset += idxArr.byteLength;

  meshes.push({
    name: part.name + '_mesh',
    primitives: [{ attributes: { POSITION: posAccessorIdx, COLOR_0: colorAccessorIdx }, indices: idxAccessorIdx, mode: 4 }],
  });
  nodes.push({ name: part.name, mesh: i, translation: part.translation });
});

// 최종 바이너리: positions 전체 -> colors 전체 -> indices 전체 (부위별로 연속 배치, 각 블록 시작점만 재계산)
const totalPosBytes = posChunks.reduce((s, b) => s + b.length, 0);
const totalColorBytes = colorChunks.reduce((s, b) => s + b.length, 0);

bufferViews.forEach((bv, i) => {
  const kind = i % 3;
  if (kind === 1) bv.byteOffset += totalPosBytes;
  else if (kind === 2) bv.byteOffset += totalPosBytes + totalColorBytes;
});

const buffer = Buffer.concat([...posChunks, ...colorChunks, ...idxChunks]);

const gltf = {
  asset: { version: '2.0', generator: 'ShipHub FLNG Sample' },
  scene: 0,
  scenes: [{ nodes: nodes.map((_, i) => i) }],
  nodes,
  meshes,
  accessors,
  bufferViews,
  buffers: [{ uri: 'ship_sample.bin', byteLength: buffer.length }],
};

writeFileSync('./public/models/ship_sample.gltf', JSON.stringify(gltf));
writeFileSync('./public/models/ship_sample.bin', buffer);
console.log(`FLNG sample generated: ship_sample.gltf + ship_sample.bin (${buffer.length} bytes, ${parts.length} parts)`);
