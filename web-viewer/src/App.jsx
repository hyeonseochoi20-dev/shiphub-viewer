import React, { useEffect, useRef, useState, Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Environment, GizmoHelper, GizmoViewcube } from '@react-three/drei'
import { FiRotateCw, FiChevronLeft, FiChevronRight } from 'react-icons/fi'
import ShipModel from './components/ShipModel'
import FLNGShip from './components/FLNGShip'
import FileTree from './components/FileTree'
import StatusPanel from './components/StatusPanel'
import AIQueryPanel from './components/AIQueryPanel'
import ModelLoader from './components/ModelLoader'
import ViewerErrorBoundary from './components/ViewerErrorBoundary'
import BatchPanel from './components/BatchPanel'
import ModulePanel from './components/ModulePanel'
import ShipGrid from './components/ShipGrid'
import SectionPlane from './components/SectionPlane'
import { STREAMLIT_URL } from './config'
import MeasureTool from './components/MeasureTool'
import ClashDetector from './components/ClashDetector'
import RadiusTool from './components/RadiusTool'
import DraftAnalysis from './components/DraftAnalysis'
import SnapEngine from './components/SnapEngine'
import ErectionSimulation, { erectionStageLabel } from './components/ErectionSimulation'
import ViewJumper from './components/ViewJumper'
import SavedViewsPanel from './components/SavedViewsPanel'
import NoteTool from './components/NoteTool'
import ToolsPanel from './components/ToolsPanel'
import Logo from './components/Logo'

// Sketchfab 샘플 선박 모델 CC-BY 크레딧 (라이선스 요구사항)
const MODEL_CREDITS = {
  'tanker-ship': {
    title: 'Tanker Ship',
    author: 'KoreanNavy',
    href: 'https://sketchfab.com/3d-models/tanker-ship-96ebf61af42b4062ae98a6ad848e1a25',
  },
  'container-ship': {
    title: 'Container Ship',
    author: 'RM02',
    href: 'https://sketchfab.com/3d-models/container-ship-aaa41cca946b4a08bc08cf692b7757be',
  },
}
function modelCreditKey(url) {
  if (!url) return null
  return Object.keys(MODEL_CREDITS).find((key) => url.includes(key)) || null
}

// 선체/거주구 경계(deckFraction)는 선종마다 형상이 달라 하나의 기본값을 공유할 수 없다.
// 탱커선은 Z축 단면 도구로 직접 실측(0.37)했지만, 다른 선종은 아직 미검증 추정치.
const DECK_FRACTION_DEFAULTS = { 'tanker-ship': 0.37, 'container-ship': 0.37 }
const DECK_FRACTION_VERIFIED = { 'tanker-ship': true, 'container-ship': false }
const deckStorageKey = (url) => `shiphub:deckFraction:${modelCreditKey(url) ?? 'default'}`

export default function App() {
  const [view, setView] = useState('viewer') // 'viewer' | 'dashboard' | 'dossier'
  const [selectedModel, setSelectedModel] = useState({
    type: 'gltf',
    url: '/models/tanker-ship/scene.gltf',
    name: 'Tanker Ship (Suezmax, 322m)',
    lod: 1
  })

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [showGrid, setShowGrid] = useState(false)
  const [activeTool, setActiveTool] = useState(null) // 'measure' | 'section' | 'clash' | null
  const [sectionAxis, setSectionAxis] = useState('x')
  const [sectionPos, setSectionPos] = useState(0)
  const [clashResults, setClashResults] = useState([])
  const [autoRotate, setAutoRotate] = useState(false)
  const snapRef = useRef(null)
  const snapActive = activeTool === 'measure' || activeTool === 'radius' || activeTool === 'note'

  const [erectionProgress, setErectionProgress] = useState(0)
  const [erectionPlaying, setErectionPlaying] = useState(false)
  const [sectionDragging, setSectionDragging] = useState(false)
  const [sectionFlipped, setSectionFlipped] = useState(false)
  // 실측 확인값: 탱커선 Z축 단면 5.0 지점에서 데크가 보임 -> (5.0-(-5.04))/(22.13-(-5.04)) ≈ 0.37을 기본값으로 사용.
  // 선종별로 값이 다르므로 모델 전환 시 아래 useEffect가 모델별 저장값/기본값으로 재설정한다.
  const [deckFraction, setDeckFraction] = useState(0.37)

  useEffect(() => {
    const key = deckStorageKey(selectedModel?.url)
    const stored = parseFloat(localStorage.getItem(key))
    const fallback = DECK_FRACTION_DEFAULTS[modelCreditKey(selectedModel?.url)] ?? 0.37
    setDeckFraction(Number.isFinite(stored) ? stored : fallback)
  }, [selectedModel?.url])

  const handleDeckFractionChange = (v) => {
    setDeckFraction(v)
    localStorage.setItem(deckStorageKey(selectedModel?.url), String(v))
  }

  const controlsRef = useRef(null)
  const [savedViews, setSavedViews] = useState([])
  const [jumpTarget, setJumpTarget] = useState(null)
  const saveCurrentView = (name) => {
    if (!controlsRef.current) return
    const cam = controlsRef.current.object
    setSavedViews((v) => [
      ...v,
      { id: Date.now(), name, position: cam.position.toArray(), target: controlsRef.current.target.toArray() },
    ])
  }

  const [notes, setNotes] = useState([])

  const toggleErectionPlaying = () => {
    if (erectionProgress >= 100) {
      finalePlayedRef.current = false
      setErectionProgress(0)
      setErectionPlaying(true)
    } else {
      setErectionPlaying((v) => !v)
    }
  }

  useEffect(() => {
    if (activeTool !== 'erection' || !erectionPlaying) return
    const id = setInterval(() => {
      setErectionProgress((p) => {
        if (p >= 100) {
          setErectionPlaying(false)
          return 100
        }
        return Math.min(100, p + 0.6)
      })
    }, 40)
    return () => clearInterval(id)
  }, [activeTool, erectionPlaying])

  // 탑재 완료 엔딩: 100%에 도달하면 3초간 한 바퀴 천천히 회전
  const [autoRotateSpeed, setAutoRotateSpeed] = useState(1.5)
  const finalePlayedRef = useRef(false)
  useEffect(() => {
    if (activeTool === 'erection' && erectionProgress >= 100 && !finalePlayedRef.current) {
      finalePlayedRef.current = true
      setAutoRotateSpeed(20) // 60/speed 초당 한 바퀴 -> speed 20이면 3초에 한 바퀴
      setAutoRotate(true)
      const t = setTimeout(() => {
        setAutoRotate(false)
        setAutoRotateSpeed(1.5)
      }, 3000)
      return () => clearTimeout(t)
    }
    if (erectionProgress < 100) {
      finalePlayedRef.current = false
    }
  }, [erectionProgress, activeTool])

  return (
    <div className="h-screen flex flex-col bg-gray-900 text-white">
      {/* 헤더 */}
      <header className="h-16 bg-gray-800 border-b border-gray-700 flex items-center px-4 gap-4">
        <Logo />
        <nav className="ml-auto flex gap-1">
          <button
            onClick={() => setView('viewer')}
            className={`px-3 py-1.5 rounded text-sm font-medium ${view === 'viewer' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
          >
            3D 뷰어
          </button>
          <button
            onClick={() => setView('dashboard')}
            className={`px-3 py-1.5 rounded text-sm font-medium ${view === 'dashboard' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
          >
            생산관리 대시보드
          </button>
          <button
            onClick={() => setView('dossier')}
            className={`px-3 py-1.5 rounded text-sm font-medium ${view === 'dossier' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-700'}`}
          >
            프로젝트 소개
          </button>
        </nav>
      </header>

      {view === 'dashboard' && (
        <iframe
          src={STREAMLIT_URL}
          title="생산관리 대시보드"
          className="flex-1 w-full border-0"
        />
      )}

      {view === 'dossier' && (
        <iframe
          src="/dossier.html"
          title="프로젝트 소개"
          className="flex-1 w-full border-0"
        />
      )}

      <div className={`flex-1 overflow-hidden relative ${view === 'viewer' ? 'flex' : 'hidden'}`}>
          {/* 사이드바 - 파일 트리 (접기/펼치기) */}
          <aside
            className={`bg-gray-800 border-r border-gray-700 overflow-y-auto transition-all duration-200 ${
              sidebarOpen ? 'w-80' : 'w-0 border-r-0'
            }`}
          >
            <div className="w-80">
              <FileTree onSelect={setSelectedModel} />
            </div>
          </aside>
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="self-start mt-3 -ml-px z-10 flex items-center justify-center w-5 h-10 bg-gray-800 border border-gray-700 rounded-r-md text-gray-400 hover:text-white hover:bg-gray-700"
            title={sidebarOpen ? '사이드바 접기' : '사이드바 펼치기'}
          >
            {sidebarOpen ? <FiChevronLeft className="w-3.5 h-3.5" /> : <FiChevronRight className="w-3.5 h-3.5" />}
          </button>

          {/* 3D 뷰어 영역 */}
          <main className="flex-1 relative">
            <ViewerErrorBoundary resetKey={selectedModel?.url}>
            <Canvas camera={{ position: [10, 10, 10], fov: 60 }} gl={{ localClippingEnabled: true }}>
              <ambientLight intensity={0.5} />
              <directionalLight position={[10, 10, 5]} intensity={1} />
                <Suspense fallback={<ModelLoader />}>
                  {selectedModel?.type === 'procedural' && <FLNGShip />}
                  {selectedModel?.type !== 'procedural' && selectedModel && <ShipModel url={selectedModel.url} />}
                  <Environment preset="warehouse" />
                </Suspense>
              <OrbitControls
                ref={controlsRef}
                enabled={!sectionDragging}
                enablePan={true}
                enableZoom={true}
                enableRotate={true}
                autoRotate={autoRotate}
                autoRotateSpeed={autoRotateSpeed}
              />
              <ViewJumper target={jumpTarget} controlsRef={controlsRef} onDone={() => setJumpTarget(null)} />

              {/* key={selectedModel?.url} - 모델을 바꾸면 이 도구들이 캐시해둔 바운딩박스/길이축을 버리고 새로 계산하도록 강제 리마운트 */}
              {showGrid && (
                <ShipGrid
                  key={`grid-${selectedModel?.url}`}
                  onSelectSection={(axis, value) => {
                    setActiveTool('section')
                    setSectionAxis(axis)
                    setSectionPos(Math.round(value * 10) / 10)
                  }}
                />
              )}
              <SectionPlane
                key={`section-${selectedModel?.url}`}
                enabled={activeTool === 'section'}
                axis={sectionAxis}
                position={sectionPos}
                flipped={sectionFlipped}
                onPositionChange={setSectionPos}
                onDraggingChange={setSectionDragging}
              />
              <SnapEngine key={`snap-${selectedModel?.url}`} active={snapActive} snapRef={snapRef} />
              <MeasureTool key={`measure-${selectedModel?.url}`} active={activeTool === 'measure'} snapRef={snapRef} />
              <RadiusTool key={`radius-${selectedModel?.url}`} active={activeTool === 'radius'} snapRef={snapRef} />
              <ClashDetector key={`clash-${selectedModel?.url}`} active={activeTool === 'clash'} onResults={setClashResults} />
              <DraftAnalysis key={`draft-${selectedModel?.url}`} active={activeTool === 'draft'} />
              <ErectionSimulation
                key={`erection-${selectedModel?.url}`}
                active={activeTool === 'erection'}
                progress={erectionProgress}
                deckFraction={deckFraction}
              />
              <NoteTool
                key={`note-${selectedModel?.url}`}
                active={activeTool === 'note'}
                snapRef={snapRef}
                notes={notes}
                onAddNote={(n) => setNotes((prev) => [...prev, n])}
                onDeleteNote={(id) => setNotes((prev) => prev.filter((n) => n.id !== id))}
              />

              <GizmoHelper alignment="bottom-right" margin={[70, 70]}>
                <GizmoViewcube />
              </GizmoHelper>
            </Canvas>
            </ViewerErrorBoundary>

            {/* 상태 패널 */}
            <div className="absolute top-4 right-4 space-y-3">
              <AIQueryPanel />
              <StatusPanel />
              <ModulePanel />
              <SavedViewsPanel
                views={savedViews}
                onSave={saveCurrentView}
                onJump={(v) => setJumpTarget(v)}
                onDelete={(id) => setSavedViews((prev) => prev.filter((v) => v.id !== id))}
              />
            </div>

            {/* 조선 검토 도구 */}
            <div className="absolute top-4 left-4">
              <ToolsPanel
                showGrid={showGrid}
                onToggleGrid={() => setShowGrid((v) => !v)}
                activeTool={activeTool}
                onSetTool={setActiveTool}
                sectionAxis={sectionAxis}
                onSectionAxisChange={setSectionAxis}
                sectionPos={sectionPos}
                onSectionPosChange={setSectionPos}
                sectionFlipped={sectionFlipped}
                onSectionFlipToggle={() => setSectionFlipped((v) => !v)}
                clashResults={clashResults}
                erectionProgress={erectionProgress}
                onErectionProgressChange={setErectionProgress}
                erectionPlaying={erectionPlaying}
                onToggleErectionPlaying={toggleErectionPlaying}
                erectionStage={erectionStageLabel(erectionProgress)}
                deckFraction={deckFraction}
                onDeckFractionChange={handleDeckFractionChange}
                deckFractionDefault={DECK_FRACTION_DEFAULTS[modelCreditKey(selectedModel?.url)] ?? 0.37}
                deckFractionVerified={DECK_FRACTION_VERIFIED[modelCreditKey(selectedModel?.url)] ?? false}
              />
            </div>

            {/* 배치 패널 */}
            <div className="absolute bottom-4 right-4">
              <BatchPanel />
            </div>

            {/* 자동 회전 토글 */}
            <button
              onClick={() => setAutoRotate((v) => !v)}
              className={`absolute bottom-16 left-4 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                autoRotate
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-gray-800/90 border-gray-700 text-gray-300 hover:bg-gray-700'
              }`}
            >
              <FiRotateCw className={`w-3.5 h-3.5 ${autoRotate ? 'animate-spin' : ''}`} />
              자동 회전 {autoRotate ? 'ON' : 'OFF'}
            </button>

            {/* CC-BY 크레딧 (Sketchfab 샘플 선박 모델) */}
            {selectedModel?.type === 'gltf' && MODEL_CREDITS[modelCreditKey(selectedModel?.url)] && (
              <div className="absolute bottom-4 left-4 text-[11px] text-gray-500 bg-gray-900/60 px-2 py-1 rounded">
                {(() => {
                  const c = MODEL_CREDITS[modelCreditKey(selectedModel.url)]
                  return (
                    <>
                      "{c.title}" by {c.author} on{' '}
                      <a href={c.href} target="_blank" rel="noreferrer" className="underline hover:text-gray-300">
                        Sketchfab
                      </a>{' '}
                      — CC BY 4.0
                    </>
                  )
                })()}
              </div>
            )}
          </main>
      </div>
    </div>
  )
}