import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { vehicleApi } from '../services/api';
import type { Vehicle } from '../types';

const TYPE_LABELS: Record<string, string> = {
  car: 'Car', suv: 'SUV', van: 'Van', truck: 'Truck', bike: 'Bike',
};

export default function CatalogPage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');

  useEffect(() => {
    loadVehicles();
  }, [typeFilter]);

  const loadVehicles = async () => {
    try {
      setLoading(true);
      const params: any = { status: 'available' };
      if (typeFilter) params.type = typeFilter;
      if (search) params.search = search;
      const res = await vehicleApi.list(params);
      setVehicles(res.data);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    loadVehicles();
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Vehicle Catalog</h1>
      <form onSubmit={handleSearch} className="flex gap-4 mb-6">
        <input
          type="text"
          placeholder="Search make or model..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 border rounded-lg px-3 py-2"
        />
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="border rounded-lg px-3 py-2">
          <option value="">All Types</option>
          {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button type="submit" className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700">Search</button>
      </form>
      {loading ? (
        <p className="text-gray-500">Loading vehicles...</p>
      ) : vehicles.length === 0 ? (
        <p className="text-gray-500">No vehicles found.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {vehicles.map((v) => (
            <Link key={v.id} to={`/vehicles/${v.id}`} className="border rounded-lg p-4 hover:shadow-md transition">
              <div className="text-sm text-blue-600 font-medium">{TYPE_LABELS[v.type] || v.type}</div>
              <h3 className="text-xl font-semibold">{v.make} {v.model}</h3>
              <p className="text-gray-600">Year: {v.year}</p>
              <p className="text-gray-600">Seats: {v.seats}</p>
              <p className="text-lg font-bold text-green-700 mt-2">₹{v.price_per_day}/day</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
