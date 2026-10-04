export interface User {
  id: string;
  name: string;
  email: string;
  role: 'customer' | 'staff';
  created_at: string;
}

export type VehicleType = 'car' | 'suv' | 'van' | 'truck' | 'bike';
export type VehicleStatus = 'available' | 'maintenance' | 'retired';

export interface Vehicle {
  id: string;
  type: VehicleType;
  make: string;
  model: string;
  year: number;
  registration_no: string;
  seats: number;
  price_per_day: number;
  status: VehicleStatus;
  image_url: string | null;
  created_at: string;
  updated_at: string;
}

export type RentalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'active'
  | 'completed'
  | 'cancelled';

export interface RentalRequest {
  id: string;
  customer_id: string;
  vehicle_id: string;
  start_date: string;
  end_date: string;
  status: RentalStatus;
  contact_name: string;
  contact_phone: string;
  contact_email: string;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface RentalProof {
  id: string;
  kind: 'aadhaar' | 'licence';
  content_type: string;
  size: number;
}

export interface RentalAuditEvent {
  action: string;
  from_status: string;
  to_status: string;
  reason: string | null;
  created_at: string;
}

export interface RentalVehicle {
  id: string;
  make: string;
  model: string;
  year: number;
  registration_no: string;
  price_per_day: number;
}

export interface RentalDetail extends RentalRequest {
  vehicle: RentalVehicle | null;
  proofs: RentalProof[];
  audit_events: RentalAuditEvent[];
}

export interface RentalListResponse {
  items: RentalRequest[];
  total: number;
  page: number;
  page_size: number;
}

export interface Token {
  access_token: string;
  token_type: string;
}