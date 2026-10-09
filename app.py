
import streamlit as st
import firebase_admin
from firebase_admin import firestore
import pandas as pd
from pathlib import Path

# ---------------- PAGE SETTINGS ----------------
st.set_page_config(
    page_title="SmartBus Crowd",
    page_icon="🚌",
    layout="centered"
)

# ---------------- FIREBASE CONNECTION ----------------
@st.cache_resource
def connect_firebase():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            options={"projectId": "smartbuscrowd"}
        )
    return firestore.client()


try:
    db = connect_firebase()
except Exception as e:
    st.error("Firebase connection failed.")
    st.code(str(e))
    st.stop()


# ---------------- LOAD LOCATIONS ----------------
@st.cache_data
def load_locations():
    csv_path = Path(__file__).parent / "locations.csv"

    if not csv_path.exists():
        raise FileNotFoundError(
            "locations.csv must be in the same folder as app.py"
        )

    df = pd.read_csv(csv_path, dtype=str).fillna("")
    df.columns = df.columns.str.strip().str.lower()

    required = {"location", "state", "district"}

    if not required.issubset(df.columns):
        raise ValueError(
            "CSV must contain location,state,district columns."
        )

    for column in required:
        df[column] = df[column].str.strip()

    df = df[
        (df["location"] != "") &
        (df["state"].str.lower() == "andhra pradesh")
    ].copy()

    df = df.drop_duplicates(
        subset=["location", "district", "state"]
    )

    df["label"] = (
        df["location"] + " — " +
        df["district"] + ", " + df["state"]
    )

    return df.sort_values("label").reset_index(drop=True)


try:
    locations_df = load_locations()
except Exception as e:
    st.error("Could not load locations.csv.")
    st.code(str(e))
    st.stop()


# ---------------- APP HEADER ----------------
st.title("🚌 SmartBus Crowd")
st.write(
    "Search Andhra Pradesh locations and check "
    "reported passenger crowd at your destination."
)

st.metric("Locations loaded", f"{len(locations_df):,}")

st.divider()


# ---------------- JOURNEY PLANNER ----------------
st.subheader("📍 Plan Your Journey")

location_options = locations_df["label"].tolist()

# Clear the destination only when it becomes the same as source
def update_source():
    if (
        st.session_state.get("source_location")
        == st.session_state.get("destination_location")
    ):
        st.session_state.destination_location = None


source = st.selectbox(
    "Starting location",
    options=location_options,
    index=None,
    placeholder="Type village, town or city name...",
    key="source_location",
    on_change=update_source
)

destination_options = [
    place for place in location_options
    if place != source
]

# Preserve destination when source changes to another location
if (
    st.session_state.get("destination_location") is not None
    and st.session_state.destination_location not in destination_options
):
    st.session_state.destination_location = None

destination = st.selectbox(
    "Destination",
    options=destination_options,
    index=None,
    placeholder="Type destination name...",
    key="destination_location"
)

if source and destination:
    st.success(f"Journey: {source} → {destination}")


# ---------------- CROWD INFORMATION ----------------
st.divider()
st.subheader("👥 Destination Crowd")


@st.fragment(run_every=5)
def show_crowd(location_name):
    try:
        # First try a document whose ID equals the location name
        doc = db.collection("bus_stops").document(
            location_name
        ).get()

        # Otherwise search by the stop_name field
        if not doc.exists:
            reports = (
                db.collection("bus_stops")
                .where("stop_name", "==", location_name)
                .limit(1)
                .stream()
            )
            doc = next(reports, None)

        if doc is None or not doc.exists:
            st.info(
                f"No crowd report is available for {location_name} yet."
            )
            st.caption(
                "This location is in the directory, but no matching "
                "crowd report was found in Firebase."
            )
            return

        data = doc.to_dict() or {}

        try:
            count = max(0, int(data.get("crowd_count", 0)))
        except (TypeError, ValueError):
            count = 0

        st.metric(
            f"Reported passengers at {location_name}",
            count
        )

        if count < 10:
            st.success("🟢 LOW CROWD")
        elif count < 25:
            st.warning("🟡 MEDIUM CROWD")
        else:
            st.error("🔴 HIGH CROWD")

        if data.get("updated_at"):
            st.caption(f"Last updated: {data['updated_at']}")

        st.caption("Crowd report refreshes every 5 seconds.")

    except Exception as e:
        st.error("Could not load crowd information.")
        st.code(str(e))


if destination:
    selected_row = locations_df[
        locations_df["label"] == destination
    ].iloc[0]

    show_crowd(selected_row["location"])
else:
    st.info("Select a destination to check its reported crowd.")


# ---------------- FOOTER ----------------
st.divider()
st.caption(
    "SmartBus Crowd | Passenger counts come from Firebase reports. "
    "This app does not automatically detect real passengers."
)