import React from 'react'

// glTF 로드 실패(404/손상된 파일 등) 시 Suspense 내부에서 던져지는 에러를 잡아서
// 앱 전체가 흰 화면으로 죽는 대신 3D 뷰어 영역에만 안내 메시지를 보여준다.
export default class ViewerErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('3D 모델 로드 실패:', error, info)
  }

  componentDidUpdate(prevProps) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900">
          <div className="text-center max-w-xs">
            <p className="text-red-400 text-sm font-medium mb-1.5">모델을 불러오지 못했습니다</p>
            <p className="text-gray-500 text-xs leading-relaxed">
              파일이 없거나 손상됐을 수 있습니다. 왼쪽 목록에서 다른 모델을 선택해보세요.
            </p>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
