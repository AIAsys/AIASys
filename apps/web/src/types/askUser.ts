/**
 * AskUser 工具类型定义
 */

export type AskUserType = 'confirm' | 'input' | 'select' | 'multi_select' | 'checkpoint_review';
export type AskUserValue =
  | string
  | string[]
  | number
  | boolean
  | Record<string, unknown>
  | null;

// 检查点评审相关类型
export interface CheckpointDeliverable {
  item: string;
  exists: boolean;
  path?: string;
  size?: string;
  status: 'PASS' | 'FAIL' | 'PENDING';
}

export interface CheckpointCustomCheck {
  item: string;
  status: 'PASS' | 'FAIL' | 'PENDING';
  note?: string;
}

export interface CheckpointReviewData {
  checkpoint_id: string;
  title: string;
  description: string;
  phase_name: string;
  phase_id: string;
  deliverables: CheckpointDeliverable[];
  custom_checks: CheckpointCustomCheck[];
  auto_check_passed: boolean;
}

export interface AskUserRequest {
  request_id: string;
  type: AskUserType;
  title: string;
  message: string;
  placeholder?: string;
  options?: Array<{ label: string; value: string }>;
  default_value?: AskUserValue;
  timeout: number;
  tool_call_id?: string;
  created_at?: string;
  // 检查点评审专用数据
  checkpoint_data?: CheckpointReviewData;
}

export interface AskUserResponse {
  request_id: string;
  approved: boolean;
  value?: AskUserValue;
}

export interface AskUserResolveRequest {
  request_id: string;
  approved: boolean;
  value?: AskUserValue;
}

export interface AskUserResolveResponse {
  success: boolean;
  message: string;
}
