import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { rentalApi } from '../services/api';
import type { RentalRequest } from '../types';
import toast from 'react-hot-toast';
import { extractErrorMessage } from '../services/errors';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  active: 'bg-blue-100 text-blue-800',
  completed: 'bg-gray-100 text-gray-800',
  cancelled: 'bg-orange-100 text-orange-800',
};

export default function MyRentalsPage() {
  const [rentals, setRentals] = useState<RentalRequest[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadRentals(); }, []);

  const loadRentals = async () => {
    try {
      const res = await rentalApi.myRentals();
      setRentals(res.data.items);
    } catch {} finally { setLoading(false); }
  };

  const handleCancel = async (id: string) => {
    if (!confirm('Are you sure you want to cancel this request?')) return;
    try {
      await rentalApi.cancel(id);
      toast.success('Request cancelled');
      loadRentals();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    }
  };

  if (loading) return <div className="max-w-4xl mx-auto p-6">Loading...</div>;

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">My Rentals</h1>
      {rentals.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-500 mb-4">No rental requests yet.</p>
          <Link to="/" className="text-blue-600 hover:underline">Browse vehicles</Link>
        </div>
      ) : (
        <div className="space-y-4">
          {rentals.map((r) => (
            <div key={r.id} className="border rounded-lg p-4 flex justify-between items-start">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[r.status]}`}>
                    {r.status.toUpperCase()}
                  </span>
                </div>
                <p className="text-sm text-gray-600">
                  {r.start_date} to {r.end_date}
                </p>
                <p className="text-sm text-gray-500">Requested: {new Date(r.created_at).toLocaleDateString()}</p>
                {r.rejection_reason && (
                  <p className="text-sm text-red-600 mt-1">Reason: {r.rejection_reason}</p>
                )}
              </div>
              <div className="flex gap-2">
                <Link to={`/rentals/${r.id}`} className="text-blue-600 hover:underline text-sm">Details</Link>
                {r.status === 'pending' && (
                  <button onClick={() => handleCancel(r.id)} className="text-red-600 hover:underline text-sm">Cancel</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
