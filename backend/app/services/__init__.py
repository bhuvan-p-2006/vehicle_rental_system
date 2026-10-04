"""Service layer: business rules live here, not in routers (SPEC §3.6)."""

__all__ = ["AuthService", "RentalService", "StorageService", "VehicleService"]


def __getattr__(name: str) -> object:
    # Lazy re-exports keep `import app.services` cheap and avoid importing
    # MinIO/bcrypt when only the rental rules are needed.
    if name == "AuthService":
        from app.services.auth import AuthService

        return AuthService
    if name == "VehicleService":
        from app.services.vehicle import VehicleService

        return VehicleService
    if name == "RentalService":
        from app.services.rental import RentalService

        return RentalService
    if name == "StorageService":
        from app.services.storage import StorageService

        return StorageService
    raise AttributeError(name)
