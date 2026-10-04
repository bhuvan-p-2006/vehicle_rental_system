import { z } from 'zod';

/**
 * Client-side mirrors of the backend Pydantic contracts (SPEC §3.6).
 *
 * These exist for UX only — the server re-validates everything. Messages are
 * deliberately worded to match the backend so a user sees the same text whether
 * the failure is caught here or on submit.
 */

// Mirrors app/schemas/auth.py
export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 72;

export const registerSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255, 'Name is too long'),
  email: z.string().email('Invalid email address'),
  password: z
    .string()
    .min(MIN_PASSWORD_LENGTH, `Password must be at least ${MIN_PASSWORD_LENGTH} characters`)
    .max(MAX_PASSWORD_LENGTH, `Password must be at most ${MAX_PASSWORD_LENGTH} characters`)
    .refine((v) => /[A-Z]/.test(v), 'Password must contain at least one uppercase letter')
    .refine((v) => /[0-9]/.test(v), 'Password must contain at least one digit'),
});

export const loginSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(1, 'Password is required'),
});

// Mirrors app/schemas/vehicle.py
export const VEHICLE_TYPES = ['car', 'suv', 'van', 'truck', 'bike'] as const;
export const VEHICLE_STATUSES = ['available', 'maintenance', 'retired'] as const;

export const vehicleCreateSchema = z.object({
  type: z.enum(VEHICLE_TYPES, { errorMap: () => ({ message: 'Select a vehicle type' }) }),
  make: z.string().min(1, 'Make is required').max(100, 'Make is too long'),
  model: z.string().min(1, 'Model is required').max(100, 'Model is too long'),
  year: z.coerce
    .number({ invalid_type_error: 'Year must be a number' })
    .int('Year must be a whole number')
    .min(1900, 'Year looks too early')
    .max(2100, 'Year looks too late'),
  registration_no: z.string().min(3, 'Registration number is required').max(50, 'Too long'),
  seats: z.coerce
    .number({ invalid_type_error: 'Seats must be a number' })
    .int('Seats must be a whole number')
    .min(1, 'At least 1 seat')
    .max(50, 'At most 50 seats'),
  price_per_day: z.coerce
    .number({ invalid_type_error: 'Price must be a number' })
    .positive('Price must be greater than 0')
    .max(10000, 'Price looks too high'),
  image_url: z.string().url('Must be a valid URL').max(500).optional().or(z.literal('')),
});

export const vehicleStatusSchema = z.object({
  status: z.enum(VEHICLE_STATUSES),
});

// Mirrors app/schemas/proof.py
export const ALLOWED_CONTENT_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'] as const;
export const MAX_PROOF_BYTES = 5 * 1024 * 1024;

export const proofKindSchema = z.enum(['aadhaar', 'licence']);

/** Browser-side file gate; the server enforces the same limits on the metadata. */
export const proofFileSchema = z.custom<File>((val) => val instanceof File, 'Select a file').refine(
  (file) => file.size <= MAX_PROOF_BYTES,
  `File must be ${MAX_PROOF_BYTES / 1024 / 1024}MB or smaller`
);

export const uploadUrlRequestSchema = z.object({
  kind: proofKindSchema,
  filename: z.string().min(1).max(255),
  content_type: z.enum(ALLOWED_CONTENT_TYPES, {
    errorMap: () => ({ message: 'Upload a JPEG, PNG, WebP or PDF' }),
  }),
  size: z.number().int().positive().max(MAX_PROOF_BYTES),
  draft_id: z.string().uuid(),
});

// Mirrors app/schemas/rental.py
export const MIN_ADVANCE_DAYS = 14;
export const MAX_DURATION_DAYS = 14;

/** yyyy-mm-dd in local time (avoids the UTC off-by-one of toISOString()). */
export function toDateInputValue(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** The earliest selectable start date, as a yyyy-mm-dd string. */
export function minStartDateValue(now: Date = new Date()): string {
  const d = new Date(now);
  d.setDate(d.getDate() + MIN_ADVANCE_DAYS);
  return toDateInputValue(d);
}

export const rentalProofSchema = z.object({
  kind: proofKindSchema,
  object_key: z.string().min(1, 'Upload failed'),
  content_type: z.enum(ALLOWED_CONTENT_TYPES),
  size: z.number().int().positive(),
});

export const rentalCreateSchema = z
  .object({
    vehicle_id: z.string().uuid('Select a vehicle'),
    start_date: z.string().min(1, 'Start date is required'),
    end_date: z.string().min(1, 'End date is required'),
    contact_name: z.string().min(1, 'Contact name is required').max(255, 'Too long'),
    contact_phone: z.string().min(5, 'Phone number is required').max(20, 'Too long'),
    contact_email: z.string().email('Invalid email address'),
    aadhaar_file: z.custom<File | null>((v) => v === null || v instanceof File, 'Required'),
    licence_file: z.custom<File | null>((v) => v === null || v instanceof File, 'Required'),
  })
  .superRefine((data, ctx) => {
    const minStart = minStartDateValue();
    if (data.start_date && data.start_date < minStart) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['start_date'],
        message: `Start date must be at least ${MIN_ADVANCE_DAYS} days from today`,
      });
    }
    if (data.start_date && data.end_date && data.end_date <= data.start_date) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_date'],
        message: 'End date must be after start date',
      });
    }
    if (data.start_date && data.end_date && data.end_date > data.start_date) {
      const days = Math.round(
        (Date.parse(data.end_date) - Date.parse(data.start_date)) / 86_400_000
      );
      if (days > MAX_DURATION_DAYS) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['end_date'],
          message: `Rental duration cannot exceed ${MAX_DURATION_DAYS} days`,
        });
      }
    }
    for (const [field, kind] of [
      ['aadhaar_file', 'aadhaar'],
      ['licence_file', 'licence'],
    ] as const) {
      const file = data[field];
      if (!file) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: [field], message: `${kind} proof is required` });
      } else {
        if (file.size > MAX_PROOF_BYTES) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: [field],
            message: `${kind} file must be ${MAX_PROOF_BYTES / 1024 / 1024}MB or smaller`,
          });
        }
        if (!(ALLOWED_CONTENT_TYPES as readonly string[]).includes(file.type)) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: [field],
            message: `${kind} must be a JPEG, PNG, WebP or PDF`,
          });
        }
      }
    }
  });

export const rejectSchema = z.object({
  reason: z.string().min(1, 'Reason is required').max(1000, 'Reason is too long'),
});

export type RegisterInput = z.infer<typeof registerSchema>;
export type LoginInput = z.infer<typeof loginSchema>;
export type VehicleCreateInput = z.infer<typeof vehicleCreateSchema>;
export type VehicleStatusInput = z.infer<typeof vehicleStatusSchema>;
export type RentalCreateInput = z.infer<typeof rentalCreateSchema>;
export type RentalProof = z.infer<typeof rentalProofSchema>;
export type UploadUrlInput = z.infer<typeof uploadUrlRequestSchema>;
export type RejectInput = z.infer<typeof rejectSchema>;