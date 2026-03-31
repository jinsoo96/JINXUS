'use client';

import { Component, type ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center p-8 bg-dark-card border border-dark-border rounded-xl text-center">
          <AlertCircle className="w-10 h-10 text-red-400 mb-3" />
          <p className="text-sm text-zinc-300 mb-1" role="alert">
            {this.props.fallbackMessage || '컴포넌트 렌더링 중 오류가 발생했습니다.'}
          </p>
          <p className="text-xs text-zinc-500 mb-2 max-w-md truncate">
            {this.state.error?.message}
          </p>
          <p className="text-xs text-zinc-600 mb-4">
            아래 버튼을 눌러 다시 시도하거나, 문제가 반복되면 페이지를 새로고침해 주세요.
          </p>
          <button
            onClick={this.handleReset}
            className="flex items-center gap-2 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm transition-colors press-feedback focus-ring"
          >
            <RefreshCw size={14} />
            다시 시도
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
