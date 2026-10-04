import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import toast from 'react-hot-toast';
import { rentalApi, uploadProof, vehicleApi } from '../services/api';
import { extractErrorMessage } from '../services/errors';
import {
  MAX_PROOF_BYTES,
  minStartDateValue,
  rentalCreateSchema,
  type RentalCreateInput,
} from '../schemas';
import { useAuth } from '../hooks/useAuth';
import type { Vehicle } from '../types';

const TYPE_LABELS: Record<string, string> = {
  car: 'Car',
  suv: 'SUV',
  van: 'Van',
  truck: 'Truck',
  bike: 'Bike',
};

const ACCEPT = '.jpg,.jpeg,.png,.webp,.pdf';

export default function VehicleDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<RentalCreateInput>({
    resolver: zodResolver(rentalCreateSchema),
    mode: 'onBlur',
    defaultValues: {
      vehicle_id: id ?? '',
      aadhaar_file: null,
      licence_file: null,
    },
  });

  const startDate = watch('start_date');
  const aadhaarFile = watch('aadhaar_file');
  const licenceFile = watch('licence_file');

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    vehicleApi
      .get(id)
      .then((res) => {
        if (!cancelled) setVehicle(res.data);
      })
      .catch(() => {
        if (!cancelled) setVehicle(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  /** Map the date input to a sensible end date as the user picks a start. */
  const onStartDateChange = (value: string) => {
    if (value) {
      const end = new Date(value);
      end.setDate(end.getDate() + 3);
      reset((prev) => ({ ...prev, start_date: value, end_date: prev.end_date || '' }));
    }
  };

  const onSubmit = async (data: RentalCreateInput) => {
    if (!id) return;
    // Both files are validated by Zod before we reach the network.
    if (!data.aadhaar_file || !data.licence_file) return;

    const draftId = crypto.randomUUID();

    try {
      setUploading('Uploading your Aadhaar…');
      const aadhaar = await uploadProof('aadhaar', data.aadhaar_file, draftId);

      setUploading('Uploading your driving licence…');
      const licence = await uploadProof('licence', data.licence_file, draftId);

      setUploading('Submitting request…');
      await rentalApi.create({
        vehicle_id: id,
        start_date: data.start_date,
        end_date: data.end_date,
        contact_name: data.contact_name,
        contact_phone: data.contact_phone,
        contact_email: data.contact_email,
        proofs: [
          {
            kind: 'aadhaar',
            object_key: aadhaar.object_key,
            content_type: data.aadhaar_file.type,
            size: data.aadhaar_file.size,
          },
          {
            kind: 'licence',
            object_key: licence.object_key,
            content_type: data.licence_file.type,
            size: data.licence_file.size,
          },
        ],
      });

      toast.success('Rental request submitted for review');
      navigate('/my-rentals');
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setUploading(null);
    }
  };

  if (loading) return <div className="max-w-4xl mx-auto p-6">Loading…</div>;
  if (!vehicle) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <p className="text-gray-600">Vehicle not found.</p>
        <button onClick={() => navigate('/')} className="text-blue-600 hover:underline mt-2">
          &larr; Back to catalog
        </button>
      </div>
    );
  }

  const requestable = user?.role === 'customer' && vehicle.status === 'available';

  return (
    <div className="max-w-4xl mx-auto p-6">
      <button onClick={() => navigate(-1)} className="text-blue-600 hover:underline mb-4">
        &larr; Back
      </button>

      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="text-sm text-blue-600 font-medium">{TYPE_LABELS[vehicle.type]}</div>
        <h1 className="text-3xl font-bold">
          {vehicle.make} {vehicle.model}
        </h1>
        <p className="text-gray-600 mt-2">
          Year {vehicle.year} · {vehicle.seats} seats · {vehicle.registration_no}
        </p>
        <p className="text-2xl font-bold text-green-700 mt-2">₹{vehicle.price_per_day}/day</p>

        {!requestable ? (
          <p className="mt-6 text-sm text-gray-500 border-t pt-4">
            {user?.role === 'staff'
              ? 'Staff accounts cannot submit rental requests.'
              : vehicle.status !== 'available'
                ? 'This vehicle is not currently open for booking.'
                : 'Log in as a customer to request this vehicle.'}
          </p>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="mt-6 border-t pt-6 space-y-4">
            <h2 className="text-xl font-semibold">Request this vehicle</h2>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="start_date" className="block text-sm font-medium mb-1">
                  Start date
                </label>
                <input
                  id="start_date"
                  type="date"
                  min={minStartDateValue()}
                  {...register('start_date', { onChange: (e) => onStartDateChange(e.target.value) })}
                  className="w-full border rounded-lg px-3 py-2"
                />
                {errors.start_date && (
                  <p className="text-red-600 text-sm mt-1">{errors.start_date.message}</p>
                )}
                <p className="text-xs text-gray-500 mt-1">At least 14 days from today.</p>
              </div>
              <div>
                <label htmlFor="end_date" className="block text-sm font-medium mb-1">
                  End date
                </label>
                <input
                  id="end_date"
                  type="date"
                  min={startDate || minStartDateValue()}
                  {...register('end_date')}
                  className="w-full border rounded-lg px-3 py-2"
                />
                {errors.end_date && (
                  <p className="text-red-600 text-sm mt-1">{errors.end_date.message}</p>
                )}
                <p className="text-xs text-gray-500 mt-1">Up to 14 days.</p>
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="contact_name" className="block text-sm font-medium mb-1">
                  Contact name
                </label>
                <input id="contact_name" {...register('contact_name')} className="w-full border rounded-lg px-3 py-2" />
                {errors.contact_name && (
                  <p className="text-red-600 text-sm mt-1">{errors.contact_name.message}</p>
                )}
              </div>
              <div>
                <label htmlFor="contact_phone" className="block text-sm font-medium mb-1">
                  Phone
                </label>
                <input id="contact_phone" {...register('contact_phone')} className="w-full border rounded-lg px-3 py-2" />
                {errors.contact_phone && (
                  <p className="text-red-600 text-sm mt-1">{errors.contact_phone.message}</p>
                )}
              </div>
            </div>

            <div>
              <label htmlFor="contact_email" className="block text-sm font-medium mb-1">
                Email
              </label>
              <input id="contact_email" type="email" {...register('contact_email')} className="w-full border rounded-lg px-3 py-2" />
              {errors.contact_email && (
                <p className="text-red-600 text-sm mt-1">{errors.contact_email.message}</p>
              )}
            </div>

            <fieldset className="border-t pt-4">
              <legend className="text-sm font-semibold">
                Identity proofs <span className="text-red-600">*</span>
              </legend>
              <p className="text-xs text-gray-500 mb-3">
                JPEG, PNG, WebP or PDF up to {MAX_PROOF_BYTES / 1024 / 1024}MB. Reviewed by staff
                before your request is approved.
              </p>

              {(
                [
                  ['aadhaar_file', 'Aadhaar card', aadhaarFile],
                  ['licence_file', 'Driving licence', licenceFile],
                ] as const
              ).map(([field, label, file]) => (
                <div key={field} className="mb-3">
                  <label htmlFor={field} className="block text-sm font-medium mb-1">
                    {label}
                  </label>
                  <input
                    id={field}
                    type="file"
                    accept={ACCEPT}
                    className="w-full text-sm"
                    onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      setValue(field, f, { shouldValidate: true });
                    }}
                  />
                  {file && <p className="text-xs text-green-700 mt-1">Selected: {file.name}</p>}
                  {errors[field] && <p className="text-red-600 text-sm mt-1">{errors[field].message}</p>}
                </div>
              ))}
            </fieldset>

            <button
              type="submit"
              disabled={isSubmitting || uploading !== null}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {uploading ?? (isSubmitting ? 'Submitting…' : 'Submit request')}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}