from geopy.distance import geodesic


def compute_distances_km(user_lat: float, user_lon: float, lats: list[float], lons: list[float]) -> list[float]:
    out = []
    origin = (user_lat, user_lon)
    for a, b in zip(lats, lons):
        out.append(geodesic(origin, (a, b)).km)
    return out
