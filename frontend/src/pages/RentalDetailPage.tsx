import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { rentalApi } from '../services/api';
import { extractErrorMessage } from '../services/errors';
import type { RentalDetail } from '../types';
import type { RentalStatus } from '../types';
import toast from 'react-hot-toast';

const STATUS_STYLES: Record<RentalStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  active: 'bg-blue-100 text-blue-800',
  completed: 'bg-gray-100 text-gray-800',
  cancelled: 'bg-orange-100 text-orange-800',
};

interface ProofLink {
  kind: string;
  url: string;
}

export default function RentalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rental, setRental] = useState<RentalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [proofLinks, setProofLinks] = useState<ProofLink[]>([]);
  const [proofsLoading, setProofsLoading] = useState(false);

  const loadProofs = useCallback(async (rentalId: string) => {
    setProofsLoading(true);
    try {
      const res = await rentalApi.getProofUrls(rentalId);
      setProofLinks(res.data);
    } catch {
      // Proof access is owner/staff-scoped; silently unavailable is acceptable.
      setProofLinks([]);
    } finally {
      setProofsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    rentalApi
      .get(id)
      .then((res) => {
        if (cancelled) return;
        setRental(res.data);
        void loadProofs(id);
      })
      .catch((err) => {
        if (!cancelled) toast.error(extractErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, loadProofs]);

  if (loading) return <div className="max-w-4xl mx-auto p-6">Loading…</div>;
  if (!rental) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <p className="text-gray-600">Request not found.</p>
        <button onClick={() => navigate(-1)} className="text-blue-600 hover:underline mt-2">
          &larr; Back
        </button>
      </div>
    );
  }

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' });

  return (
    <div className="max-w-4xl mx-auto p-6">
      <button onClick={() => navigate(-1)} className="text-blue-600 hover:underline mb-4">
        &larr; Back
      </button>

      <div className="bg-white rounded-lg shadow-md p-6">
        <span
          className={`inline-block px-3 py-1 rounded-full text-sm font-medium ${STATUS_STYLES[rental.status]}`}
        >
          {rental.status.toUpperCase()}
        </span>

        {rental.vehicle && (
          <h1 className="text-2xl font-bold mt-3">
            {rental.vehicle.make} {rental.vehicle.model}{' '}
            <span className="text-gray-500 font-normal">({rental.vehicle.year})</span>
          </h1>
        )}

        <dl className="grid sm:grid-cols-2 gap-4 mt-6">
          <div>
            <dt className="text-sm text-gray-500">Rental window</dt>
            <dd className="font-medium">
              {formatDate(rental.start_date)} → {formatDate(rental.end_date)}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Requested</dt>
            <dd className="font-medium">{formatDate(rental.created_at)}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Customer</dt>
            <dd className="font-medium">{rental.contact_name}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Phone</dt>
            <dd className="font-medium">{rental.contact_phone}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-sm text-gray-500">Email</dt>
            <dd className="font-medium">{rental.contact_email}</dd>
          </div>
        </dl>

        {rental.rejection_reason && (
          <div className="mt-6 bg-red-50 border border-red-200 p-3 rounded">
            <p className="text-sm text-red-800">
              <strong>Rejection reason:</strong> {rental.rejection_reason}
            </p>
          </div>
        )}

        <section className="mt-6 border-t pt-4">
          <h2 className="font-semibold mb-2">Identity proofs</h2>
          {proofsLoading ? (
            <p className="text-sm text-gray-500">Preparing secure links…</p>
          ) : proofLinks.length === 0 ? (
            <p className="text-sm text-gray-500">No proofs available for this request.</p>
          ) : (
            <div className="grid sm:grid-cols-2 gap-4">
              {proofLinks.map((link) => (
                <figure key={link.kind} className="border rounded-lg p-3">
                  <figcaption className="text-sm font-medium capitalize mb-2">
                    {link.kind === 'aadhaar' ? 'Aadhaar card' : 'Driving licence'}
                  </figcaption>
                  {link.url.endsWith('.pdf') || link.url.includes('pdf') ? (
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:underline text-sm"
                    >
                      Open PDF
                    </a>
                  ) : (
                    <img
                      src={link.url}
                      alt={`${link.kind} proof`}
                      className="max-h-56 w-full object-contain rounded"
                    />
                  )}
                </figure>
              ))}
            </div>
          )}
          <p className="text-xs text-gray-500 mt-2">
            Links are short-lived and issued only to the request owner and verifying staff.
          </p>
        </section>

        {rental.audit_events.length > 0 && (
          <section className="mt-6 border-t pt-4">
            <h2 className="font-semibold mb-2">Audit trail</h2>
            <ol className="space-y-2">
              {rental.audit_events.map((event, i) => (
                <li key={i} className="text-sm text-gray-700">
                  <span className="font-medium capitalize">{event.action}</span>{' '}
                  <span className="text-gray-500">
                    {event.from_status} → {event.to_status}
                  </span>
                  {event.reason && <span className="text-red-700"> — {event.reason}</span>}
                  <span className="text-gray-400 ml-2">
                    {new Date(event.created_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
    </div>
  );
}