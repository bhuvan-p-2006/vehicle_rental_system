import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { vehicleApi } from '../services/api';
import { vehicleCreateSchema, vehicleStatusSchema, type VehicleCreateInput } from '../schemas';
import type { Vehicle } from '../types';
import toast from 'react-hot-toast';
import { extractErrorMessage } from '../services/errors';

const TYPE_LABELS: Record<string, string> = {
  car: 'Car', suv: 'SUV', van: 'Van', truck: 'Truck', bike: 'Bike',
};

export default function VehicleManagementPage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<VehicleCreateInput>({
    resolver: zodResolver(vehicleCreateSchema),
  });

  useEffect(() => { loadVehicles(); }, []);

  const loadVehicles = async () => {
    try {
      const res = await vehicleApi.list();
      setVehicles(res.data);
    } catch {} finally { setLoading(false); }
  };

  const onCreate = async (data: VehicleCreateInput) => {
    try {
      await vehicleApi.create(data);
      toast.success('Vehicle created');
      reset();
      setShowForm(false);
      loadVehicles();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  const handleStatus = async (id: string, status: string) => {
    // Mirror the server contract before sending (SPEC 3.6): the <select> value is
    // an untrusted string.
    const parsed = vehicleStatusSchema.safeParse({ status });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? 'Invalid status');
      return;
    }
    try {
      await vehicleApi.updateStatus(id, parsed.data.status);
      toast.success('Status updated');
      loadVehicles();
    } catch (err) { toast.error(extractErrorMessage(err)); }
  };

  if (loading) return <div className="max-w-6xl mx-auto p-6">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Vehicle Management</h1>
        <button onClick={() => setShowForm(!showForm)} className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
          {showForm ? 'Cancel' : '+ Add Vehicle'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit(onCreate)} className="bg-white border rounded-lg p-6 mb-6 space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Type</label>
              <select {...register('type')} className="w-full border rounded px-3 py-2">
                {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              {errors.type && <p className="text-red-500 text-sm">{errors.type.message}</p>}
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Make</label>
              <input {...register('make')} className="w-full border rounded px-3 py-2" />
              {errors.make && <p className="text-red-500 text-sm">{errors.make.message}</p>}
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Model</label>
              <input {...register('model')} className="w-full border rounded px-3 py-2" />
              {errors.model && <p className="text-red-500 text-sm">{errors.model.message}</p>}
            </div>
          </div>
          <div className="grid grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Year</label>
              <input {...register('year')} type="number" className="w-full border rounded px-3 py-2" />
              {errors.year && <p className="text-red-500 text-sm">{errors.year.message}</p>}
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Registration No</label>
              <input {...register('registration_no')} className="w-full border rounded px-3 py-2" />
              {errors.registration_no && <p className="text-red-500 text-sm">{errors.registration_no.message}</p>}
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Seats</label>
              <input {...register('seats')} type="number" className="w-full border rounded px-3 py-2" />
              {errors.seats && <p className="text-red-500 text-sm">{errors.seats.message}</p>}
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Price/Day (₹)</label>
              <input {...register('price_per_day')} type="number" step="0.01" className="w-full border rounded px-3 py-2" />
              {errors.price_per_day && <p className="text-red-500 text-sm">{errors.price_per_day.message}</p>}
            </div>
          </div>
          <button type="submit" disabled={isSubmitting} className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50">
            {isSubmitting ? 'Creating...' : 'Create Vehicle'}
          </button>
        </form>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {vehicles.map((v) => (
          <div key={v.id} className="border rounded-lg p-4">
            <div className="text-sm text-blue-600">{TYPE_LABELS[v.type]}</div>
            <h3 className="text-lg font-semibold">{v.make} {v.model}</h3>
            <p className="text-sm text-gray-600">Reg: {v.registration_no} | Seats: {v.seats}</p>
            <p className="text-green-700 font-bold">₹{v.price_per_day}/day</p>
            <div className="flex gap-2 mt-3">
              <select
                value={v.status}
                onChange={(e) => handleStatus(v.id, e.target.value)}
                className="border rounded px-2 py-1 text-sm"
              >
                <option value="available">Available</option>
                <option value="maintenance">Maintenance</option>
                <option value="retired">Retired</option>
              </select>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
