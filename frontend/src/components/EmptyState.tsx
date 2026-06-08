interface EmptyStateProps {
  message: string
}

export function EmptyState({ message }: EmptyStateProps) {
  return <div className="state-box empty-state">{message}</div>
}
