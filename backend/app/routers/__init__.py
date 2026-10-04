from app.routers.auth import router as auth_router
from app.routers.rentals import router as rentals_router
from app.routers.vehicles import router as vehicles_router

__all__ = ["auth_router", "rentals_router", "vehicles_router"]
