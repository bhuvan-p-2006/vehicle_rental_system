import type { User, Vehicle, RentalRequest, RentalDetail, RentalListResponse, Token } from '../types';

export interface ProofMeta {
  kind: 'aadhaar' | 'licence';
  object_key: string;
  content_type: string;
  size: number;
}

export interface UploadUrlResponse {
  upload_url: string;
  object_key: string;
  expires_in_seconds: number;
}

export interface RentalCreateBody {
  vehicle_id: string;
  start_date: string;
  end_date: string;
  contact_name: string;
  contact_phone: string;
  contact_email: string;
  proofs: ProofMeta[];
}

/** Stable error codes from SPEC §3.3. */
export const RULE_MESSAGES: Record<string, string> = {
  START_TOO_SOON: 'Start date must be at least 14 days from today',
  DURATION_TOO_LONG: 'Rental duration cannot exceed 14 days',
  ACTIVE_RENTAL_EXISTS: 'You already have a pending, approved, or active rental.',
  VEHICLE_UNAVAILABLE: 'That vehicle is not available for those dates.',
  VEHICLE_NOT_FOUND: 'That vehicle no longer exists.',
  PROOFS_MISSING: 'Please upload your Aadhaar and driving licence.',
  CANNOT_CANCEL: 'Only a pending request can be cancelled.',
  ROLE_REQUIRED: 'You do not have permission to do that.',
  FORBIDDEN: 'You do not have permission to do that.',
  NOT_YOUR_RENTAL: 'You do not have access to that request.',
  INVALID_TRANSITION: 'That action is not valid for the current status.',
};

/** Pull a human-readable message out of a backend error envelope. */
export function extractErrorMessage(err: unknown): string {
  const anyErr = err as {
    response?: { data?: { detail?: unknown } };
    message?: string;
  };
  const detail = anyErr?.response?.data?.detail;

  if (typeof detail === 'string') return detail;

  if (detail && typeof detail === 'object') {
    const d = detail as { code?: string; message?: string; errors?: { msg?: string }[] };
    if (d.code && RULE_MESSAGES[d.code]) return RULE_MESSAGES[d.code];
    if (d.code && d.message) return d.message;
    if (d.message) return d.message;
    if (d.errors?.length) return d.errors.map((e) => e.msg).filter(Boolean).join('; ');
  }

  return anyErr?.message ?? 'Something went wrong. Please try again.';
}