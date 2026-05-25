export interface Message {
  role: 'user' | 'ai'
  content: string
  streaming?: boolean
}
