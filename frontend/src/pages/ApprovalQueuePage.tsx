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

export default function ApprovalQueuePage() {
  const [rentals, setRentals] = useState<RentalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState<string | null>(null);

  useEffect(() => { loadPending(); }, []);

  const loadPending = async () => {
    try {
      const res = await rentalApi.pending();
      setRentals(res.data.items);
    } catch {} finally { setLoading(false); }
  };

  const handleAction = async (id: string, action: 'approve' | 'reject' | 'activate' | 'complete', reason?: string) => {
    try {
      setActionId(id);
      if (action === 'approve') await rentalApi.approve(id);
      else if (action === 'reject') await rentalApi.reject(id, reason || '');
      else if (action === 'activate') await rentalApi.activate(id);
      else if (action === 'complete') await rentalApi.complete(id);
      toast.success(`Request ${action}d`);
      loadPending();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally { setActionId(null); }
  };

  const handleReject = (id: string) => {
    const reason = prompt('Enter rejection reason:');
    if (reason) handleAction(id, 'reject', reason);
  };

  if (loading) return <div className="max-w-6xl mx-auto p-6">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Approval Queue</h1>
      {rentals.length === 0 ? (
        <p className="text-gray-500 text-center py-12">No pending requests.</p>
      ) : (
        <div className="space-y-4">
          {rentals.map((r) => (
            <div key={r.id} className="border rounded-lg p-4">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[r.status]}`}>
                      {r.status.toUpperCase()}
                    </span>
                  </div>
                  <p className="font-medium">{r.contact_name} — {r.contact_phone}</p>
                  <p className="text-sm text-gray-600">{r.start_date} to {r.end_date}</p>
                  <p className="text-sm text-gray-500">Submitted: {new Date(r.created_at).toLocaleDateString()}</p>
                </div>
                <div className="flex gap-2">
                  <Link to={`/rentals/${r.id}`} className="text-blue-600 hover:underline text-sm">View</Link>
                  {r.status === 'pending' && (
                    <>
                      <button
                        onClick={() => handleAction(r.id, 'approve')}
                        disabled={actionId === r.id}
                        className="bg-green-600 text-white px-3 py-1 rounded text-sm hover:bg-green-700 disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleReject(r.id)}
                        disabled={actionId === r.id}
                        className="bg-red-600 text-white px-3 py-1 rounded text-sm hover:bg-red-700 disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </>
                  )}
                  {r.status === 'approved' && (
                    <button
                      onClick={() => handleAction(r.id, 'activate')}
                      disabled={actionId === r.id}
                      className="bg-blue-600 text-white px-3 py-1 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
                    >
                      Activate
                    </button>
                  )}
                  {r.status === 'active' && (
                    <button
                      onClick={() => handleAction(r.id, 'complete')}
                      disabled={actionId === r.id}
                      className="bg-gray-600 text-white px-3 py-1 rounded text-sm hover:bg-gray-700 disabled:opacity-50"
                    >
                      Complete
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
