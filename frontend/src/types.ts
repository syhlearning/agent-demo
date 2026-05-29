export interface ToolCall {
  name: string
  args: Record<string, unknown>
}

export interface Message {
  role: 'user' | 'ai' | 'review'
  content: string
  streaming?: boolean
  // human review 相关
  toolCalls?: ToolCall[]
  reviewStatus?: 'pending' | 'approved' | 'rejected'
}

export interface Conversation {
  threadId: string
  title: string
  createdAt: number
}
