import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { rentalApi } from '../services/api';
import { extractErrorMessage } from '../services/errors';
import type { RentalRequest, RentalStatus } from '../types';
import toast from 'react-hot-toast';

const STATUS_STYLES: Record<RentalStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  active: 'bg-blue-100 text-blue-800',
  completed: 'bg-gray-100 text-gray-800',
  cancelled: 'bg-orange-100 text-orange-800',
};

/**
 * Staff work queues.
 *
 * Each bucket is reachable: approving a request moves it out of `pending`, so the
 * `approved` and `active` tabs are what make activation and completion possible.
 * Without them an approved rental would never be picked up again and the customer
 * would stay blocked by the one-outstanding-rental rule.
 */
const TABS: Array<{ status: RentalStatus; label: string }> = [
  { status: 'pending', label: 'Pending' },
  { status: 'approved', label: 'Approved' },
  { status: 'active', label: 'Active' },
  { status: 'completed', label: 'Completed' },
  { status: 'rejected', label: 'Rejected' },
];

interface ModalProps {
  title: string;
  hint: string;
  value: string;
  placeholder: string;
  confirmLabel: string;
  onChange: (value: string) => void;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
}

/** Reason-input dialog shared by reject and cancel. */
function Modal({
  title,
  hint,
  value,
  placeholder,
  confirmLabel,
  onChange,
  onClose,
  onConfirm,
}: ModalProps) {
  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-lg shadow-lg p-6 w-full max-w-md">
        <h2 className="text-lg font-semibold mb-2">{title}</h2>
        <p className="text-sm text-gray-600 mb-3">{hint}</p>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          placeholder={placeholder}
          className="w-full border rounded-lg px-3 py-2"
        />
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded border text-gray-700 hover:bg-gray-50"
          >
            Close
          </button>
          <button
            onClick={() => void onConfirm()}
            className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ApprovalQueuePage() {
  const [tab, setTab] = useState<RentalStatus>('pending');
  const [counts, setCounts] = useState<Partial<Record<RentalStatus, number>>>({});
  const [rentals, setRentals] = useState<RentalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<{ id: string; reason: string } | null>(null);
  const [cancelling, setCancelling] = useState<{ id: string; reason: string } | null>(null);

  const loadTab = useCallback(async (status: RentalStatus) => {
    setLoading(true);
    try {
      const res = await rentalApi.staffQueue(status);
      setRentals(res.data.items);
    } catch (err) {
      toast.error(extractErrorMessage(err));
      setRentals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Tab totals, so staff can see where the work sits without visiting each tab.
  const loadCounts = useCallback(async () => {
    await Promise.all(
      TABS.map(async ({ status }) => {
        try {
          const res = await rentalApi.staffQueue(status);
          setCounts((prev) => ({ ...prev, [status]: res.data.total }));
        } catch {
          /* a failed count should not break the page */
        }
      })
    );
  }, []);

  const refresh = useCallback(async () => {
    await Promise.all([loadTab(tab), loadCounts()]);
  }, [loadTab, loadCounts, tab]);

  useEffect(() => {
    void loadTab(tab);
    void loadCounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const run = async (id: string, action: () => Promise<unknown>, label: string) => {
    try {
      setBusyId(id);
      await action();
      toast.success(label);
      await refresh();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Rental Queue</h1>

      <div className="flex flex-wrap gap-2 border-b border-gray-200 mb-6">
        {TABS.map(({ status, label }) => (
          <button
            key={status}
            onClick={() => setTab(status)}
            className={`px-4 py-2 -mb-px border-b-2 text-sm font-medium ${
              tab === status
                ? 'border-blue-600 text-blue-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
            {counts[status] !== undefined && (
              <span className="ml-2 rounded-full bg-gray-200 px-2 py-0.5 text-xs">
                {counts[status]}
              </span>
            )}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-gray-500">Loading…</p>
      ) : rentals.length === 0 ? (
        <p className="text-gray-500 py-12 text-center">Nothing in “{tab}”.</p>
      ) : (
        <div className="space-y-4">
          {rentals.map((r) => (
            <div key={r.id} className="border rounded-lg p-4 bg-white">
              <div className="flex justify-between items-start gap-4 flex-wrap">
                <div>
                  <span
                    className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${STATUS_STYLES[r.status]}`}
                  >
                    {r.status.toUpperCase()}
                  </span>
                  <p className="mt-2 font-medium">{r.contact_name}</p>
                  <p className="text-sm text-gray-600">
                    {r.contact_phone} · {r.contact_email}
                  </p>
                  <p className="text-sm text-gray-600">
                    {r.start_date} → {r.end_date}
                  </p>
                  <p className="text-xs text-gray-500">
                    Submitted {new Date(r.created_at).toLocaleString()}
                  </p>
                  {r.rejection_reason && (
                    <p className="text-sm text-red-600 mt-1">Reason: {r.rejection_reason}</p>
                  )}
                </div>

                <div className="flex gap-2 flex-wrap">
                  <Link
                    to={`/rentals/${r.id}`}
                    className="text-blue-600 hover:underline text-sm px-2 py-1"
                  >
                    View &amp; proofs
                  </Link>

                  {r.status === 'pending' && (
                    <>
                      <button
                        onClick={() =>
                          run(r.id, () => rentalApi.approve(r.id), 'Request approved')
                        }
                        disabled={busyId === r.id}
                        className="bg-green-600 text-white px-3 py-1 rounded text-sm hover:bg-green-700 disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => setRejecting({ id: r.id, reason: '' })}
                        disabled={busyId === r.id}
                        className="bg-red-600 text-white px-3 py-1 rounded text-sm hover:bg-red-700 disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </>
                  )}

                  {r.status === 'approved' && (
                    <button
                      onClick={() =>
                        run(r.id, () => rentalApi.activate(r.id), 'Marked as active')
                      }
                      disabled={busyId === r.id}
                      className="bg-blue-600 text-white px-3 py-1 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
                    >
                      Activate
                    </button>
                  )}

                  {r.status === 'active' && (
                    <button
                      onClick={() =>
                        run(r.id, () => rentalApi.complete(r.id), 'Marked as completed')
                      }
                      disabled={busyId === r.id}
                      className="bg-gray-700 text-white px-3 py-1 rounded text-sm hover:bg-gray-800 disabled:opacity-50"
                    >
                      Complete
                    </button>
                  )}

                  {(r.status === 'pending' ||
                    r.status === 'approved' ||
                    r.status === 'active') && (
                    <button
                      onClick={() => setCancelling({ id: r.id, reason: '' })}
                      disabled={busyId === r.id}
                      className="border border-red-300 text-red-700 px-3 py-1 rounded text-sm hover:bg-red-50 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {cancelling && (
        <Modal
          title="Cancel this rental"
          hint="Use this when the customer drops out. The vehicle is released and the customer is freed by the one-vehicle rule."
          value={cancelling.reason}
          placeholder="e.g. Customer withdrew — vehicle released back to the fleet"
          onChange={(reason) => setCancelling({ ...cancelling, reason })}
          onClose={() => setCancelling(null)}
          onConfirm={async () => {
            const { id, reason } = cancelling;
            setCancelling(null);
            await run(
              id,
              () => rentalApi.cancel(id, reason.trim() || undefined),
              'Rental cancelled'
            );
          }}
          confirmLabel="Cancel rental"
        />
      )}

      {rejecting && (
        <Modal
          title="Reject this request"
          hint="The customer sees this reason, so make it specific."
          value={rejecting.reason}
          placeholder="e.g. Driving licence photo is unreadable"
          onChange={(reason) => setRejecting({ ...rejecting, reason })}
          onClose={() => setRejecting(null)}
          onConfirm={async () => {
            const { id, reason } = rejecting;
            setRejecting(null);
            await run(id, () => rentalApi.reject(id, reason), 'Request rejected');
          }}
          confirmLabel="Reject request"
        />
      )}
    </div>
  );
}