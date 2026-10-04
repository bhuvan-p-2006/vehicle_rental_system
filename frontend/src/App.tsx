import { BrowserRouter, Navigate, Route, Routes, Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './hooks/useAuth';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import CatalogPage from './pages/CatalogPage';
import VehicleDetailPage from './pages/VehicleDetailPage';
import MyRentalsPage from './pages/MyRentalsPage';
import RentalDetailPage from './pages/RentalDetailPage';
import ApprovalQueuePage from './pages/ApprovalQueuePage';
import VehicleManagementPage from './pages/VehicleManagementPage';

/**
 * Client-side route guard. The server enforces RBAC regardless (SPEC §2) — this
 * only avoids rendering screens the user cannot use.
 */
function RequireRole({
  role,
  children,
}: {
  role: 'customer' | 'staff';
  children: ReactNode;
}) {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-6">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function Navbar() {
  const { user, isCustomer, isStaff, logout } = useAuth();

  return (
    <nav className="bg-white border-b shadow-sm">
      <div className="max-w-6xl mx-auto px-4 py-3 flex justify-between items-center flex-wrap gap-3">
        <Link to="/" className="text-xl font-bold text-blue-600">
          VehicleRental
        </Link>
        <div className="flex gap-4 items-center flex-wrap text-sm">
          <Link to="/" className="text-gray-700 hover:text-blue-600">
            Catalog
          </Link>
          {isCustomer && (
            <Link to="/my-rentals" className="text-gray-700 hover:text-blue-600">
              My Rentals
            </Link>
          )}
          {isStaff && (
            <>
              <Link to="/approvals" className="text-gray-700 hover:text-blue-600">
                Approvals
              </Link>
              <Link to="/vehicles/manage" className="text-gray-700 hover:text-blue-600">
                Vehicles
              </Link>
            </>
          )}
          {user ? (
            <div className="flex items-center gap-3">
              <span className="text-gray-500">
                {user.name} · {user.role}
              </span>
              <button onClick={logout} className="text-red-600 hover:underline">
                Logout
              </button>
            </div>
          ) : (
            <div className="flex gap-3 items-center">
              <Link to="/login" className="text-gray-700 hover:text-blue-600">
                Login
              </Link>
              <Link
                to="/register"
                className="bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700"
              >
                Register
              </Link>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}

function AppRoutes() {
  const { loading } = useAuth();
  if (loading) {
    return <div className="flex justify-center items-center min-h-screen">Loading…</div>;
  }

  return (
    <>
      <Navbar />
      <main className="min-h-screen bg-gray-50">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/" element={<CatalogPage />} />
          <Route path="/vehicles/:id" element={<VehicleDetailPage />} />

          <Route
            path="/my-rentals"
            element={
              <RequireRole role="customer">
                <MyRentalsPage />
              </RequireRole>
            }
          />
          <Route
            path="/approvals"
            element={
              <RequireRole role="staff">
                <ApprovalQueuePage />
              </RequireRole>
            }
          />
          <Route
            path="/vehicles/manage"
            element={
              <RequireRole role="staff">
                <VehicleManagementPage />
              </RequireRole>
            }
          />
          {/* Owner or staff — the API re-checks ownership. */}
          <Route path="/rentals/:id" element={<RentalDetailPage />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
        <Toaster position="top-right" />
      </AuthProvider>
    </BrowserRouter>
  );
}