from geopy.distance import geodesic


def calculate_distances(df, user_lat, user_lon):

    df["Distância (km)"] = [
        geodesic((user_lat, user_lon), (lat, lon)).km
        for lat, lon in zip(df["Latitudine"], df["Longitudine"])
    ]

    return df.sort_values(by="Distância (km)", ascending=True)
