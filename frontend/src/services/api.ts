import axios from 'axios';
import type {
  User,
  Vehicle,
  RentalRequest,
  RentalDetail,
  RentalListResponse,
  RentalStatus,
  Token,
} from '../types';
import type {
  LoginInput,
  RegisterInput,
  RejectInput,
  UploadUrlInput,
  VehicleCreateInput,
} from '../schemas';
import type { RentalCreateBody, UploadUrlResponse } from './errors';

const API_URL = import.meta.env.VITE_API_URL ?? '/api/v1';

const TOKEN_KEY = 'vr.token';
const USER_KEY = 'vr.user';

const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // 401 means the token is gone or expired; drop it and let the router redirect.
    if (err.response?.status === 401 && localStorage.getItem(TOKEN_KEY)) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

export const authApi = {
  register: (data: RegisterInput) => api.post<User>('/auth/register', data),
  login: (data: LoginInput) => api.post<Token>('/auth/login', data),
  me: () => api.get<User>('/auth/me'),
};

export interface VehicleFilters {
  type?: string;
  status?: string;
  search?: string;
  available_from?: string;
  available_to?: string;
  page?: number;
  page_size?: number;
}

export const vehicleApi = {
  list: (params?: VehicleFilters) => api.get<Vehicle[]>('/vehicles', { params }),
  get: (id: string) => api.get<Vehicle>(`/vehicles/${id}`),
  create: (data: VehicleCreateInput) => api.post<Vehicle>('/vehicles', data),
  update: (id: string, data: Partial<VehicleCreateInput>) =>
    api.put<Vehicle>(`/vehicles/${id}`, data),
  updateStatus: (id: string, status: string) =>
    api.patch<Vehicle>(`/vehicles/${id}/status`, { status }),
};

export const rentalApi = {
  create: (data: RentalCreateBody) => api.post<RentalRequest>('/rentals', data),
  myRentals: (page = 1) => api.get<RentalListResponse>('/rentals/me', { params: { page } }),
  get: (id: string) => api.get<RentalDetail>(`/rentals/${id}`),
  cancel: (id: string, reason?: string) =>
    api.post<RentalRequest>(`/rentals/${id}/cancel`, reason ? { reason } : undefined),
  /** Staff queue. Defaults to `pending`; `approved`/`active` are needed to advance the lifecycle. */
  staffQueue: (status: RentalStatus = 'pending', page = 1) =>
    api.get<RentalListResponse>('/rentals', { params: { status, page } }),
  approve: (id: string) => api.post<RentalDetail>(`/rentals/${id}/approve`),
  reject: (id: string, reason: string) =>
    api.post<RentalDetail>(`/rentals/${id}/reject`, { reason } satisfies RejectInput),
  activate: (id: string) => api.post<RentalDetail>(`/rentals/${id}/activate`),
  complete: (id: string) => api.post<RentalDetail>(`/rentals/${id}/complete`),
  getProofUrls: (id: string) =>
    api.get<Array<{ kind: string; url: string }>>(`/rentals/${id}/proofs`),
  getUploadUrl: (data: UploadUrlInput) => api.post<UploadUrlResponse>('/rentals/upload-url', data),
};

/**
 * Upload a proof file straight to object storage using a presigned PUT, then
 * return the metadata the rental-create call needs (SPEC §3.4).
 */
export async function uploadProof(
  kind: 'aadhaar' | 'licence',
  file: File,
  draftId: string
): Promise<{ object_key: string }> {
  const { data } = await rentalApi.getUploadUrl({
    kind,
    filename: file.name,
    content_type: file.type as UploadUrlInput['content_type'],
    size: file.size,
    draft_id: draftId,
  });

  const put = await fetch(data.upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': file.type },
    body: file,
  });
  if (!put.ok) {
    throw new Error(`Failed to upload ${kind} (HTTP ${put.status}).`);
  }

  return { object_key: data.object_key };
}

export default api;